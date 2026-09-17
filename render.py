#!/usr/bin/env python3
"""Render out/graph.json as out/map.html (a self-contained artifact page).

One continuous timeline. X is publication year on a fixed decade scale, so every
edge points backwards in time. Sections stack vertically in the same coordinate
space and the canvas grows to fit them, so a source belonging to two collections —
or an edge crossing between them — needs no change to the layout.
"""

import json, os, math

import force   # the clustering layout lives there; see its module docstring

HERE = os.path.dirname(os.path.abspath(__file__))
G = json.load(open(os.path.join(HERE, "out", "graph.json")))

# ---- time axis -------------------------------------------------------------
# Fixed decade scale, not data-derived: 1960-2000 takes 40% of the width and
# 2000-2030 the remaining 60%. So each early decade is 10% and each recent decade
# 20% — the crowded years get double the room, and the ratio stays put as sources
# are added rather than shifting under the reader.
YSTART, YBREAK, YEND = 1960, 2000, 2030
BREAK_FRAC = 0.40

W, PAD_L, PAD_R = 1180, 62, 30
SPAN = W - PAD_L - PAD_R


def frac(year):
    y = min(max(year or YSTART, YSTART), YEND)
    if y <= YBREAK:
        return BREAK_FRAC * (y - YSTART) / (YBREAK - YSTART)
    return BREAK_FRAC + (1 - BREAK_FRAC) * (y - YBREAK) / (YEND - YBREAK)


def xs(year):
    return PAD_L + frac(year) * SPAN


# ---- bands -----------------------------------------------------------------
# Zotero folders have no bearing on this map. Bands come from the tags: each source
# sits in the band of its RAREST tag in the banding facet - rarest across the
# library, so the most distinctive of an item's tags wins and bands stay usefully
# sized. Items carrying no tag in that facet collect in a final band.
#
# Three facets can band the map and the reader switches between them, so all three
# layouts are computed here and the choice is a client-side swap. evidence: and
# role: are deliberately excluded: evidence: would put 43% of the library in a
# single "conceptual" band, and role: is already carried by node colour.
#
# Rejected alternative: agglomerative clustering on Jaccard over all three facets.
# It produced comparable groups but the membership shifts as sources are added, and
# a band could only be named by a heuristic. A band that IS a tag needs no naming.
BAND_FIELDS = ("question:", "approach:", "subject:")
DEFAULT_BAND = "question"
NO_BAND = "(unclassified)"

nodes = {n["key"]: n for n in G["nodes"]}


def radius(n):
    return 4.2 + 3.4 * math.log10((n.get("cited_by") or 0) + 1)


# ---- vertical layout -------------------------------------------------------
# Lanes are collision avoidance only: y carries no data. Every lane is exactly
# LANE_H tall in every section, so a section's height is simply however many lanes
# the packer needed. No stretching, no per-section height rule.
#
# Only band membership and lane assignment depend on the facet. x and r do not, and
# y is derived in the browser because collapsing a band moves every band below it.
LANE_H, TOP, LABEL_H, GAP = 30, 44, 26, 22


def build_bands(field):
    freq = {}
    for n in nodes.values():
        for t in n["tags"]:
            if t.startswith(field):
                freq[t] = freq.get(t, 0) + 1
    where = {}
    for n in nodes.values():
        ts = [t for t in n["tags"] if t.startswith(field)]
        where[n["key"]] = (min(ts, key=lambda t: (freq[t], t)).split(": ", 1)[1]
                           if ts else NO_BAND)
    grouped = {}
    for n in nodes.values():
        grouped.setdefault(where[n["key"]], []).append(n)
    # biggest first, alphabetical tie-break; the catch-all always sits last
    order = sorted([s for s in grouped if s != NO_BAND],
                   key=lambda s: (-len(grouped[s]), s))
    if NO_BAND in grouped:
        order.append(NO_BAND)
    secs, assign = [], {}
    for name in order:
        members = sorted(grouped[name],
                         key=lambda n: (n["year"] or 0, -(n.get("cited_by") or 0)))
        lanes = []                               # rightmost x used in each lane
        for n in members:
            r, x = radius(n), xs(n["year"])
            for i, last in enumerate(lanes):
                if x - r - last >= 11:
                    lanes[i] = x + r
                    assign[n["key"]] = [name, i]
                    break
            else:
                lanes.append(x + r)
                assign[n["key"]] = [name, len(lanes) - 1]
        secs.append({"name": name, "count": len(members),
                     "lanes": max(1, len(lanes)), "lane_px": LANE_H,
                     "note": ("no %s tag" % field) if name == NO_BAND
                             else "%s %s" % (field, name)})
    return {"sections": secs, "assign": assign}


bands = {f.rstrip(":"): build_bands(f) for f in BAND_FIELDS}

for n in nodes.values():
    n["x"] = round(xs(n["year"]), 1)
    n["r"] = round(radius(n), 1)
    n["section"], n["lane"] = bands[DEFAULT_BAND]["assign"][n["key"]]

# initial canvas height, for the default banding with every band collapsed-to-open
# as the browser first draws it; relayout() recomputes it on every change
H = TOP + 10
for _s in bands[DEFAULT_BAND]["sections"]:
    H += LABEL_H + _s["lanes"] * LANE_H + GAP

# replay order: position 1 is the first source ever added. Sequential rank, not real
# time - the gaps between additions carry no meaning here.
for i, n in enumerate(sorted(nodes.values(), key=lambda n: (n.get("date_added") or "", n["key"])), 1):
    n["rank"] = i

payload = {
    "meta": {k: G[k] for k in ("generated", "threshold", "counts")},
    "bands": bands, "band_default": DEFAULT_BAND,
    "w": W, "h": H, "axis_top": TOP - 22,
    "layout": {"lane_h": LANE_H, "top": TOP, "label_h": LABEL_H, "gap": GAP, "collapsed_h": 10},
    "ticks": [{"year": y, "x": round(xs(y), 1), "major": y % 20 == 0}
              for y in range(YSTART, YEND + 1, 10)],
    "breakx": round(xs(YBREAK), 1),
    "nodes": [{k: n[k] for k in ("key", "title", "creators", "year", "date", "role", "role_source",
                                 "evidence", "cited_by", "in_degree", "out_degree", "tags",
                                 "collections", "abstract", "itemType", "doi", "unresolved",
                                 "x", "r", "section", "lane", "rank", "date_added")} for n in nodes.values()],
    "edges": G["edges"],
    "tag_edges": G.get("tag_edges", []),
    "tag_min": G.get("tag_min"),
    # Everything the clustering mode needs. Recomputed here on every render, like
    # every other derived value on this page — nothing is written back.
    "force": force.build(G, nodes, radius),
}

TPL = """<title>Commons Citation Map</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>
/* Omarchy "Last Horizon" — single-theme by intent: this is meant to read as a terminal. */
:root{
  --bg:#0c0b0c; --panel:#121011; --fg:#FAFCFB; --dim:#cfd3cd; --dimmer:#584e51;
  --line:#2b2529; --accent:#b59790; --cursor:#e2dddc;
  --found:#87a9b0; --add:#b19be2; --contra:#c38b7b; --sat:#6B5E73;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--mono);font-size:13px;line-height:1.6;margin:0;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1240px;margin:0 auto;padding-inline:16px;padding-block:26px 40px}
.bar{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;
  border:1px solid var(--line);border-bottom-width:2px;padding:9px 12px}
.bar .t{color:var(--accent);font-weight:700;letter-spacing:.16em;font-size:12.5px}
.bar .m{color:var(--dimmer);font-size:11.5px;letter-spacing:.06em}
.legend{border:1px solid var(--line);border-bottom:0;padding:11px 13px;display:grid;gap:9px}
.lrow{display:grid;grid-template-columns:44px 1fr;gap:13px;align-items:start}
.lrow .k{padding-top:3px;line-height:0}
.lrow .t{color:var(--dimmer);font-size:11.5px;line-height:1.6}
.lrow b{color:var(--dim);font-weight:500;letter-spacing:.07em;text-transform:uppercase;font-size:10.5px;margin-right:7px}
.lrow .ci{font-style:normal;font-weight:500}
#thr{color:var(--dimmer)}
.qbar{display:flex;align-items:center;gap:10px;border:1px solid var(--line);border-bottom:0;padding:0 12px}
.qbar .p{color:var(--accent);font-weight:700;font-size:13px}
.q{flex:1;min-width:0;appearance:none;background:transparent;border:0;color:var(--fg);
  font-family:var(--mono);font-size:12.5px;letter-spacing:.05em;padding:10px 0;outline:none}
.q::placeholder{color:var(--dimmer)}
.q:focus{caret-color:var(--accent)}
.qbar:focus-within{border-color:var(--accent)}
.qc{appearance:none;background:transparent;border:0;color:var(--dimmer);font-family:var(--mono);
  font-size:11px;cursor:pointer;padding:4px 0;letter-spacing:.06em}
.qc:hover{color:var(--contra)}
.filters{display:flex;flex-wrap:wrap;gap:0;border:1px solid var(--line);margin-bottom:4px}
.fl{appearance:none;background:transparent;border:0;border-right:1px solid var(--line);
  font-family:var(--mono);font-size:12px;letter-spacing:.09em;color:var(--dimmer);
  padding:8px 13px;cursor:pointer;display:flex;align-items:center;gap:8px;text-transform:uppercase}
.fl:last-child{border-right:0}
.fl .box{color:inherit}
.fl .n{color:var(--dimmer);font-size:11px}
.fl[aria-pressed="true"]{color:var(--c);background:color-mix(in srgb,var(--c) 11%,transparent)}
.fl[aria-pressed="true"] .n{color:var(--c);opacity:.8}
.fl:hover{background:color-mix(in srgb,var(--c) 18%,transparent);color:var(--c)}
.fl:focus-visible{outline:1px solid var(--accent);outline-offset:-2px}
.hint{color:var(--dimmer);font-size:11px;letter-spacing:.05em;margin:8px 2px 10px}
.scrub{display:flex;align-items:center;gap:12px;border:1px solid var(--line);border-bottom:0;padding-right:12px}
.sc{flex:1;min-width:0;appearance:none;background:transparent;height:20px;cursor:pointer;margin:0}
.sc::-webkit-slider-runnable-track{height:3px;background:var(--line)}
.sc::-webkit-slider-thumb{appearance:none;width:9px;height:15px;background:var(--accent);margin-top:-6px;border:0;border-radius:0}
.sc::-moz-range-track{height:3px;background:var(--line)}
.sc::-moz-range-thumb{width:9px;height:15px;background:var(--accent);border:0;border-radius:0}
.sc:focus-visible{outline:1px solid var(--accent);outline-offset:2px}
/* Every element in this row is a fixed width, so the slider track can never resize
   while it is being dragged. A content-sized readout made the thumb jump. */
.scn{flex:0 0 300px;width:300px;color:var(--dimmer);font-size:11px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
#play{flex:0 0 104px;width:104px;text-align:left}
.bandctl{display:flex;align-items:center;gap:0;border:1px solid var(--line);border-bottom:0;flex-wrap:wrap}
.bc.bf[aria-pressed="true"]{color:var(--accent);background:color-mix(in srgb,var(--accent) 13%,transparent)}
.bc{appearance:none;background:transparent;border:0;border-right:1px solid var(--line);
  font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;color:var(--dimmer);
  padding:7px 13px;cursor:pointer;text-transform:uppercase}
.bc:hover{color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,transparent)}
.bc:focus-visible{outline:1px solid var(--accent);outline-offset:-2px}
.bcn{margin-left:auto;padding-right:12px;color:var(--dimmer);font-size:11px;letter-spacing:.06em}
.scroller{overflow-x:auto;border:1px solid var(--line);background:var(--panel)}
svg{display:block}
.node{cursor:pointer}
.node:focus-visible{outline:none}
.node:focus-visible circle{stroke:var(--cursor);stroke-width:3}
.hidden{display:none}
.seclbl{font-family:var(--mono);font-size:11px;letter-spacing:.17em;fill:var(--accent);font-weight:700;cursor:pointer}
.seclbl:hover{fill:var(--fg)}
.sechit{cursor:pointer;fill:transparent}
.secnote{font-family:var(--mono);font-size:10.5px;fill:var(--dimmer);letter-spacing:.04em}
.tick{font-family:var(--mono);font-size:10px;fill:var(--dimmer)}
.tick.major{fill:var(--dim)}
.panel{background:var(--panel);border:1px solid var(--line);border-top:0;padding:16px 18px;min-height:164px}
.panel h2{font-size:14px;font-weight:700;margin:0 0 6px;line-height:1.35;color:var(--fg);letter-spacing:.01em}
.panel .cite{color:var(--dimmer);font-size:11.5px;margin:0 0 11px;line-height:1.65}
.panel p.ab{font-size:12.5px;max-width:96ch;margin:0 0 13px;color:var(--dim)}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:11px}
.chip{font-size:10px;letter-spacing:.05em;padding:1px 6px;border:1px solid var(--line);color:var(--dimmer)}
.chip.role{border-color:currentColor;font-weight:500}
.links{display:grid;grid-template-columns:1fr 1fr;gap:14px;font-size:11.5px}
.links3{grid-template-columns:1fr 1fr 1fr}
.links h3{font-size:10px;letter-spacing:.13em;color:var(--accent);margin:0 0 6px;font-weight:500}
.links li{margin-bottom:2px;cursor:pointer;color:var(--dimmer)}
.links li:before{content:"› ";color:var(--line)}
.links li:hover{color:var(--fg)}
.links li:hover:before{color:var(--accent)}
.links ul{list-style:none;margin:0;padding:0}
.ph{color:var(--dimmer);font-size:12px}
.ph .bl{background:var(--cursor);color:var(--bg)}
.status{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;
  background:var(--accent);color:var(--bg);font-size:11.5px;letter-spacing:.07em;padding:5px 12px;font-weight:500}
@media(max-width:640px){.scn{flex-basis:130px;width:130px}#play{flex-basis:92px;width:92px}
.links,.links3{grid-template-columns:1fr}.fl{flex:1 1 auto;justify-content:center}
.modesw{margin-left:0}.expg{margin-left:0}}
.expg{display:flex;gap:0;margin-left:11px}
/* Export is an ACTION, not a view. It must never wear the mode switch's selected
   look, so it is a separate class from .msw — sharing that one also handed these
   buttons force.py's setMode binding, which fired with an undefined mode — and it
   carries no aria-pressed at all. The hover is the page's bright neutral rather
   than the warm accent, so "do something" stays visibly apart from "you are
   looking at this", and :active gives the click somewhere to land without
   anything staying lit afterwards. */
/* The -1px margin collapses each pair of borders into one shared edge, which is
   what keeps the group reading as a single control. It also means the NEXT button's
   left border is painted over this one's right border — so a lit button lost its
   right edge until it was raised above its neighbour. position+z-index on the lit
   states only, so the resting group still shares its edges. */
.exb{appearance:none;background:transparent;border:1px solid var(--line);
  font-family:var(--mono);font-size:11px;letter-spacing:.1em;color:var(--dimmer);
  padding:3px 10px;cursor:pointer;text-transform:uppercase;margin-left:-1px;
  position:relative}
.exb:hover{color:var(--cursor);border-color:var(--cursor);z-index:1;
  background:color-mix(in srgb,var(--cursor) 12%,transparent)}
.exb:active{color:var(--bg);background:var(--cursor);border-color:var(--cursor);z-index:1}
.exb:focus-visible{outline:1px solid var(--cursor);outline-offset:2px;z-index:1}
__FCSS__
</style>
<div class="wrap">
<div class="bar"><span class="t">ZOTERO :: CITATION MAP</span>
  <span class="modesw" id="modesw">
    <button class="msw" data-m="timeline" aria-pressed="true">timeline</button>
    <button class="msw" data-m="cluster" aria-pressed="false">clustering</button>
  </span>
  <span class="expg">
    <button class="exb" id="expsvg" title="save the graph exactly as it stands \u2014 same view, same filters, same selection \u2014 as an SVG with no background and dark ink">[\u2193] svg</button>
    <button class="exb" id="expcopy" title="copy that same SVG to the clipboard instead of downloading it">[\u29c9] copy</button>
  </span>
  <span class="m">__GEN__</span></div>
<div class="legend">
  <div class="lrow"><span class="k"><svg width="40" height="9"><line x1="0" y1="4.5" x2="40" y2="4.5" stroke="#b0a3a0" stroke-width="1.6"/></svg></span><span class="t"><b>citation</b> this source's reference list contains that one \u2014 directed, so it always points back in time. Read from published reference lists via OpenAlex, with Semantic Scholar covering preprints.</span></div>
  <div class="lrow tl"><span class="k"><svg width="40" height="9"><line x1="0" y1="4.5" x2="40" y2="4.5" stroke="#6B5E73" stroke-width="1.6" stroke-dasharray="2 3"/></svg></span><span class="t"><b>shared vocabulary</b> tag overlap of 0.50 or better \u2014 shared tags divided by all tags across both \u2014 on subject, question and approach. Drawn only where no citation exists, since a citation says strictly more.</span></div>
  <div class="lrow cl"><span class="k"><svg width="40" height="14"><circle cx="8" cy="7" r="3" fill="none" stroke="#6B5E73" stroke-width="1.2"/><circle cx="31" cy="7" r="3" fill="none" stroke="#6B5E73" stroke-width="1.2"/><path d="M12 7 Q19.5 7 27 7" stroke="#6B5E73" stroke-width="1.2" stroke-dasharray="1.5 2.5" fill="none" opacity=".6"/></svg></span><span class="t"><b>position</b> an output of the links, not the year: citations pull hard, vocabulary weakly, every source repels every other. Only who sits <i>beside</i> whom means anything \u2014 distance between far-apart groups does not. Vocabulary is drawn thin and faint, so a group joined only by dashes shares language but cites nothing. <b>spread</b> (compact \u00b7 balanced \u00b7 distinct) sets how hard the clusters are pulled apart; compact also drops the layout's head start, placing every source by its links alone.</span></div>
  <div class="lrow cl"><span class="k"><svg width="40" height="14"><path d="M3 10 Q3 3 12 3 Q28 2 35 5 Q39 9 30 11 Q14 13 3 10 Z" fill="#b59790" fill-opacity=".07" stroke="#b59790" stroke-opacity=".45" stroke-width="1" stroke-dasharray="4 3"/></svg></span><span class="t"><b>cluster hulls</b> communities found on the links alone, independently of the layout, each named by its most distinctive tag. <b>Select a source</b> and every hull covering it turns solid and names itself \u2014 one sitting where two strands overlap names both. They are the cross-check: a hull that comes out long and tangled means the maths and the physics disagree, so do not believe that grouping.</span></div>
  <div class="lrow"><span class="k"><svg width="40" height="14"><circle cx="9" cy="7" r="3.4" fill="#87a9b0" fill-opacity=".75" stroke="#87a9b0"/><circle cx="26" cy="7" r="6.4" fill="#87a9b0" fill-opacity=".75" stroke="#87a9b0"/></svg></span><span class="t"><b>circles</b> <span id="szw">size is the global citation count</span>, colour is <span id="cbw">the role</span> <span id="thr"></span></span></div>
  <div class="lrow"><span class="k"><svg width="40" height="15"><line x1="0" y1="3" x2="40" y2="3" stroke="#e6604f" stroke-width="1.9"/><line x1="0" y1="8" x2="40" y2="8" stroke="#6fdc8c" stroke-width="1.9"/><line x1="0" y1="13" x2="40" y2="13" stroke="#FAFCFB" stroke-width="1.9" stroke-dasharray="2 3"/></svg></span><span class="t"><b>on selecting a source</b> <i class="ci" style="color:#e6604f">red</i> what it cites &middot; <i class="ci" style="color:#6fdc8c">green</i> what cites it &middot; <i class="ci" style="color:#FAFCFB">white</i> shared vocabulary</span></div>
</div>
<div class="qbar">
  <span class="p">/</span>
  <input id="q" class="q" type="text" autocomplete="off" spellcheck="false"
         placeholder="filter by title, author, year, tag, doi or abstract…">
  <button id="qc" class="qc" hidden>[clear]</button>
</div>
<div class="filters" id="filters"></div>
<div class="scrub">
  <button id="play" class="bc" style="border-left:0">[▶] play</button>
  <input id="scrub" class="sc" type="range" min="1" step="1" value="1" aria-label="Replay library growth">
  <span class="scn" id="scn"></span>
</div>
<div class="bandctl tl" id="bandfacet"></div>
<div class="bandctl tl">
  <button id="expall" class="bc">[+] expand all</button>
  <button id="colall" class="bc">[−] collapse all</button>
  <button id="sizesw" class="bc">size: citations</button>
  <span class="bcn" id="bcn"></span>
</div>
<div class="bandctl cl">
  <button id="resettle" class="bc">[\u21bb] re-settle</button>
  <button id="cby" class="bc">colour: role</button>
  <span class="bcn" id="ccn"></span>
</div>
<div class="bandctl cl" id="spreadctl"></div>
<div class="bandctl cl" id="ykey" style="display:none">
  <span class="bcn" id="ykeyb" style="margin-left:0;flex:1;padding:7px 12px 7px 13px"></span>
</div>
<div class="scroller"><svg id="svg" role="img" aria-label="Citation timeline across the library"></svg></div>
<div class="panel" id="panel"><p class="ph"><span class="bl">&nbsp;</span> select a node &mdash; abstract, tags and citation links appear here</p></div>
<div class="status" id="status"></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const ROLES=['foundational','additional','contrarian','satellite'];
const RC={foundational:'var(--found)',additional:'var(--add)',contrarian:'var(--contra)',satellite:'var(--sat)'};
const HL={out:'#e6604f',inc:'#6fdc8c',voc:'#FAFCFB'};   /* none of these is a role colour */
const RAW={foundational:'#87a9b0',additional:'#b19be2',contrarian:'#c38b7b',satellite:'#6B5E73'};
const byKey={};D.nodes.forEach(n=>byKey[n.key]=n);
const on=Object.fromEntries(ROLES.map(r=>[r,true]));
let q='';
/* one predicate drives nodes and both edge layers, so a hidden endpoint can never
   leave a dangling line */
const hay={};
D.nodes.forEach(n=>{hay[n.key]=[n.title,n.creators.join(' '),n.year,n.date,n.doi||'',
  n.itemType,n.tags.join(' '),n.abstract].join(' \u00b7 ').toLowerCase();});
const match=n=>!q||hay[n.key].includes(q);
let tmax=D.nodes.length;                 /* replay cutoff: show ranks 1..tmax */
const vis=n=>on[n.role]&&match(n)&&n.rank<=tmax;
const NS='http://www.w3.org/2000/svg';
const el=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const svg=document.getElementById('svg');
svg.setAttribute('viewBox',`0 0 ${D.w} ${D.h}`);
svg.setAttribute('width',D.w);svg.setAttribute('height',D.h);

const L=D.layout;
const gB=el('g',{});svg.appendChild(gB);          /* band grounds + labels */
const gG=el('g',{});svg.appendChild(gG);          /* decade gridlines */

/* Which facet bands the map. Each facet keeps its own collapsed state, so switching
   away and back does not throw away what the reader opened. Only gB is rebuilt —
   the node, edge and vocabulary layers are facet-independent and are never touched,
   which is what keeps a selection and a filter alive across a switch. */
let BAND=D.band_default, SEC=[], secOf={}, collapsed={};
const collapsedBy={};
Object.keys(D.bands).forEach(f=>{
  collapsedBy[f]={};
  D.bands[f].sections.forEach(s=>collapsedBy[f][s.name]=true);  /* overview, not detail */
});
function buildBands(){
  SEC=D.bands[BAND].sections;
  collapsed=collapsedBy[BAND];
  secOf={};SEC.forEach(s=>secOf[s.name]=s);
  while(gB.firstChild)gB.removeChild(gB.firstChild);
  SEC.forEach((s,i)=>{
    s._bg=el('rect',{x:0,width:D.w,fill:'#161314',opacity:i%2===0?.75:0});
    s._lbl=el('text',{x:6,class:'seclbl'});
    s._note=el('text',{x:6,class:'secnote'});
    s._hit=el('rect',{x:0,width:D.w,height:22,class:'sechit',fill:'transparent'});
    s._hit.addEventListener('click',()=>{collapsed[s.name]=!collapsed[s.name];relayout();});
    s._lbl.addEventListener('click',()=>{collapsed[s.name]=!collapsed[s.name];relayout();});
    gB.appendChild(s._bg);gB.appendChild(s._lbl);gB.appendChild(s._note);gB.appendChild(s._hit);
  });
  const A=D.bands[BAND].assign;
  D.nodes.forEach(n=>{const a=A[n.key];n.section=a[0];n.lane=a[1];});
}
D.ticks.forEach(t=>{
  const brk=Math.abs(t.x-D.breakx)<0.5;
  t._line=el('line',{x1:t.x,y1:D.axis_top+4,x2:t.x,stroke:brk?'#584e51':'#2b2529',
    'stroke-width':brk?1.6:1,opacity:brk?.9:.85});
  gG.appendChild(t._line);
  const l=el('text',{x:t.x,y:D.axis_top-4,class:'tick'+(t.major?' major':''),'text-anchor':'middle'});
  l.textContent=t.year;gG.appendChild(l);
});

/* vocabulary layer sits beneath citations: dashed so it never reads as "A cited B" */
const gT=el('g',{});svg.appendChild(gT);
D.tag_edges.forEach(e=>{
  const s=byKey[e.a],t=byKey[e.b];if(!s||!t)return;
  const p=el('path',{fill:'none',stroke:'#6B5E73','stroke-width':0.8,'stroke-dasharray':'2 3',opacity:.55});
  p.dataset.a=e.a;p.dataset.b=e.b;p.dataset.shared=e.shared.join(' | ');
  gT.appendChild(p);
});

const gE=el('g',{});svg.appendChild(gE);
D.edges.forEach(e=>{
  const s=byKey[e.source],t=byKey[e.target];if(!s||!t)return;
  const p=el('path',{fill:'none',stroke:'#b0a3a0','stroke-width':0.8,opacity:.8});
  p.dataset.s=e.source;p.dataset.t=e.target;gE.appendChild(p);
});

const gN=el('g',{});svg.appendChild(gN);
D.nodes.forEach(n=>{
  const g=el('g',{class:'node',tabindex:0,role:'button'});
  g.dataset.k=n.key;g.dataset.role=n.role;
  n._c=el('circle',{cx:n.x,r:n.r,fill:RAW[n.role],'fill-opacity':.75,
    stroke:RAW[n.role],'stroke-width':1});
  /* collapsed form: a thin horizontal bar, width still carrying citation count */
  const bw=Math.max(3,n.r*1.8);
  n._b=el('rect',{x:n.x-bw/2,width:bw,height:6,fill:RAW[n.role],'fill-opacity':.85});
  const ttl=el('title',{});ttl.textContent=`${n.creators[0]||'?'} ${n.year||''} — ${n.title}`;
  g.appendChild(n._c);g.appendChild(n._b);g.appendChild(ttl);
  g.addEventListener('click',()=>sel(n.key));
  g.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();sel(n.key);}});
  gN.appendChild(g);
});

/* ---- circle size ----
   Size normally carries the global citation count, which is what makes the famous
   works findable at a glance \u2014 and also what makes a book nobody has indexed look
   trivial. Uniform drops it: every source becomes the same dot, so position and
   colour are all that is left to read. Both views share the switch and the state.

   This is a DRAWING change only. No position moves and the simulation is not
   re-run, so the layout stays the one that was settled and measured; the physics
   keeps using its own radii either way.

   10 is the median radius the map already draws, and it is measured to be safe
   rather than guessed: the closest pair of nodes is 21.7px apart in the timeline
   (the same to within 0.1px across all three banding facets) and 38.6px in
   clustering, so a uniform 10 introduces no overlap in any view. Anything above
   ~10.8 starts colliding in the timeline, which is the binding constraint. */
let UNIFORM=false;
const URAD=10;
const rad=n=>UNIFORM?URAD:n.r;
const barW=n=>Math.max(3,rad(n)*1.8);
function applySizes(){
  D.nodes.forEach(n=>{
    n._c.setAttribute('r',rad(n));
    const w=barW(n);
    n._b.setAttribute('width',w);
    if(n._x!=null)n._b.setAttribute('x',n._x-w/2);
  });
  /* the legend has to agree with what the circles are actually showing */
  const sz=document.getElementById('szw');
  if(sz)sz.textContent=UNIFORM?'are all one size':'size is the global citation count';
}
/* The switch belongs to both views, so rather than a row of its own it lives in
   whichever mode's control row is showing — beside expand/collapse in the timeline,
   beside colour in clustering. Moved, not duplicated: one element, one state, and
   no pair of labels that can drift apart. It goes BEFORE the row's note, which is
   pushed right by margin-left:auto and would otherwise end up mid-row. */
function placeSize(){
  const note=document.getElementById(MODE==='cluster'?'ccn':'bcn');
  const b=document.getElementById('sizesw');
  if(note&&b&&note.parentNode)note.parentNode.insertBefore(b,note);
}
document.getElementById('sizesw').addEventListener('click',e=>{
  UNIFORM=!UNIFORM;
  e.currentTarget.textContent='size: '+(UNIFORM?'uniform':'citations');
  applySizes();
});

/* vertical layout lives here, not in the payload, because collapsing a band moves
   every band below it */
function relayout(){
  if(MODE==='cluster')return;          /* clustering owns the geometry there */
  let y=L.top;
  SEC.forEach(s=>{
    const open=!collapsed[s.name];
    const h=open?s.lanes*L.lane_h:L.collapsed_h;
    const top=y+L.label_h;
    s._top=top;s._h=h;s._open=open;
    s._bg.setAttribute('y',top-6);s._bg.setAttribute('height',h+12);
    s._lbl.setAttribute('y',y+16);
    s._lbl.textContent=(open?'\u25be ':'\u25b8 ')+s.name;
    s._note.setAttribute('y',y+16);
    s._note.setAttribute('x',6+(s.name.length+2)*8.4+12);
    s._note.textContent=(open?'':s.count+' sources collapsed \u00b7 click to expand');
    s._hit.setAttribute('y',y+2);
    y=top+h+L.gap;
  });
  const shut=SEC.filter(s=>collapsed[s.name]).length;
  const bcn=document.getElementById('bcn');
  if(bcn)bcn.textContent=shut===0?'all '+SEC.length+' sections open'
        :(shut===SEC.length?'all '+SEC.length+' sections collapsed':(SEC.length-shut)+' of '+SEC.length+' open');
  const H=y+10;
  svg.setAttribute('viewBox',`0 0 ${D.w} ${H}`);svg.setAttribute('height',H);
  D.ticks.forEach(t=>t._line.setAttribute('y2',H-6));
  D.nodes.forEach(n=>{
    const s=secOf[n.section];
    /* _x is the position the link layers read. Here it is the year scale; in
       clustering mode the simulation overwrites it, which is the whole of the
       difference between the two views. */
    n._x=n.x;
    n._y = s._open ? s._top+(n.lane+0.5)*L.lane_h : s._top+L.collapsed_h/2;
    n._c.setAttribute('cx',n._x);
    n._c.setAttribute('cy',n._y);n._c.setAttribute('display',s._open?'':'none');
    n._b.setAttribute('x',n._x-barW(n)/2);
    n._b.setAttribute('y',n._y-3);n._b.setAttribute('display',s._open?'none':'');
  });
  paths();
}

/* Both modes draw the same two link layers from the same DOM paths, so only the
   geometry is per-mode. The timeline bows its edges to separate ones that would
   otherwise overlap along a lane; clustering draws straight, trimmed to the
   circle edge so an arrowhead has somewhere to sit. */
function paths(){
  const tl=MODE!=='cluster';
  [[gE,'s','t'],[gT,'a','b']].forEach(([layer,ka,kb])=>{
    layer.querySelectorAll('path').forEach(p=>{
      const a=byKey[p.dataset[ka]],b=byKey[p.dataset[kb]];
      if(!a||!b)return;
      if(tl){
        const dy=Math.abs(a._y-b._y),dx=Math.abs(a._x-b._x);
        const mx=(a._x+b._x)/2,my=(a._y+b._y)/2-(dy>60?0:Math.min(40,dx*0.16+12));
        p.setAttribute('d',`M${a._x},${a._y} Q${mx},${my} ${b._x},${b._y}`);
      }else{
        /* centre to centre: the nodes are painted after the links and cover the
           ends, so a trimmed line only added a gap without adding information */
        p.setAttribute('d','M'+a._x.toFixed(1)+','+a._y.toFixed(1)
          +' L'+b._x.toFixed(1)+','+b._y.toFixed(1));
      }
    });
  });
}

/* ---- role visibility toggles ---- */
const counts={};ROLES.forEach(r=>counts[r]=D.nodes.filter(n=>n.role===r).length);
const F=document.getElementById('filters');
ROLES.forEach(r=>{
  const b=document.createElement('button');
  b.className='fl';b.id='fl-'+r;b.style.setProperty('--c',RAW[r]);
  b.setAttribute('aria-pressed','true');
  b.innerHTML=`<span class="box">[x]</span>${r}<span class="n">${counts[r]}</span>`;
  b.addEventListener('click',()=>{on[r]=!on[r];
    b.setAttribute('aria-pressed',on[r]?'true':'false');
    b.querySelector('.box').textContent=on[r]?'[x]':'[ ]';
    apply();});
  F.appendChild(b);
});
/* ---- banding facet ---- */
const BF=document.getElementById('bandfacet');
Object.keys(D.bands).forEach(f=>{
  const b=document.createElement('button');
  b.className='bc bf';b.dataset.f=f;
  b.textContent=f+' ['+D.bands[f].sections.length+']';
  b.setAttribute('aria-pressed',f===BAND?'true':'false');
  b.addEventListener('click',()=>{
    if(BAND===f)return;
    BAND=f;
    BF.querySelectorAll('.bf').forEach(x=>x.setAttribute('aria-pressed',x.dataset.f===f?'true':'false'));
    buildBands();relayout();apply();
  });
  BF.appendChild(b);
});

document.getElementById('thr').textContent=`\u00b7 foundational = cited \u2265 ${D.meta.threshold.foundational_in_degree}\u00d7 within this library`;

function apply(){
  let vn=0;                       /* counter, NOT the vis() predicate */
  gN.querySelectorAll('.node').forEach(g=>{
    const show=vis(byKey[g.dataset.k]);
    g.classList.toggle('hidden',!show);
    if(show)vn++;
  });
  let ve=0;
  gE.querySelectorAll('path').forEach(p=>{
    const show=vis(byKey[p.dataset.s])&&vis(byKey[p.dataset.t]);
    p.classList.toggle('hidden',!show);
    if(show)ve++;
  });
  let vt=0,vd=0;
  gT.querySelectorAll('path').forEach(p=>{
    const live=vis(byKey[p.dataset.a])&&vis(byKey[p.dataset.b]);
    if(live)vt++;
    p.classList.toggle('hidden',!live);
    if(live)vd++;
  });
  if(MODE==='cluster')hulls();
  document.getElementById('status').innerHTML=
    (MODE==='cluster'
      ? `<span>SHOWING ${vn}/${D.nodes.length} SOURCES &nbsp;·&nbsp; ${ve}/${D.edges.length} CITATIONS &nbsp;\u00b7&nbsp; ${vd}/${D.tag_edges.length} VOCABULARY DRAWN</span>`
      : `<span>SHOWING ${vn}/${D.nodes.length} SOURCES &nbsp;·&nbsp; ${ve}/${D.edges.length} CITATIONS &nbsp;\u00b7&nbsp; ${vt}/${D.tag_edges.length} VOCABULARY</span>`)+
    `<span>${tmax<D.nodes.length?'REPLAY '+tmax+'/'+D.nodes.length:(q?'FILTER: /'+q.toUpperCase():(ROLES.filter(r=>!on[r]).length?'HIDDEN: '+ROLES.filter(r=>!on[r]).join(', ').toUpperCase():'ALL VISIBLE'))}</span>`;
}

/* The selection lives in one variable so that clearing it is a no-op when nothing
   is selected, and so the placeholder is restored from the same string the page
   ships with rather than a second copy of it. */
const PLACEHOLDER='<p class="ph"><span class="bl">&nbsp;</span> select a node &mdash; abstract, tags and citation links appear here</p>';
let selected=null;

function deselect(){
  if(!selected)return;
  selected=null;
  gE.querySelectorAll('path').forEach(p=>{
    p.setAttribute('opacity',.8);p.setAttribute('stroke-width',0.8);p.setAttribute('stroke','#b0a3a0');
  });
  styleVoc();
  document.getElementById('panel').innerHTML=PLACEHOLDER;
  apply();
}

/* Walk up to the svg looking for a class, rather than Element.closest, because the
   ancestor chain here is SVG and the node itself is the <g> while the click target
   is the circle or bar inside it. */
function within(el,cls){
  for(let e=el;e&&e!==svg;e=e.parentNode) if(e.classList&&e.classList.contains(cls))return true;
  return false;
}

/* Clicking the canvas anywhere that is not a node clears the selection. Band labels
   and their hit strips are excluded: collapsing a band should not throw away what
   the reader had selected. */
svg.addEventListener('click',ev=>{
  const t=ev.target;
  if(within(t,'node')||within(t,'seclbl')||within(t,'sechit'))return;
  deselect();
});

function sel(key){
  const n=byKey[key];if(!n)return;
  selected=key;
  apply();                     /* may need to surface this node's vocabulary */
  gE.querySelectorAll('path').forEach(p=>{
    const hot=p.dataset.s===key||p.dataset.t===key;
    p.setAttribute('opacity',hot?1:.12);
    p.setAttribute('stroke-width',hot?1.9:0.8);
    /* Direction is carried by colour alone — red for what this cites, green for
       what cites it — in both modes. Arrowheads on top of that were redundant. */
    p.setAttribute('stroke',hot?(p.dataset.s===key?HL.out:HL.inc):'#b0a3a0');
  });
  gT.querySelectorAll('path').forEach(p=>{
    const hot=p.dataset.a===key||p.dataset.b===key;
    p.setAttribute('opacity',hot?.95:.1);
    p.setAttribute('stroke',hot?HL.voc:'#6B5E73');
    p.setAttribute('stroke-width',hot?1.9:0.8);
  });
  const kin=D.tag_edges.filter(e=>e.a===key||e.b===key)
    .map(e=>({m:byKey[e.a===key?e.b:e.a],j:e.j,sh:e.shared})).filter(z=>z.m&&vis(z.m));
  const out=D.edges.filter(e=>e.source===key).map(e=>byKey[e.target]).filter(m=>m&&vis(m));
  const inn=D.edges.filter(e=>e.target===key).map(e=>byKey[e.source]).filter(m=>m&&vis(m));
  const lab=m=>`${m.creators[0]||'?'} ${m.year||''}  ${m.title.slice(0,46)}`;
  document.getElementById('panel').innerHTML=`
   <h2>${esc(n.title)}</h2>
   <p class="cite">${esc(n.creators.join(', '))||'—'} · ${esc(n.date||'n.d.')} · ${n.itemType}${n.doi?' · '+esc(n.doi):''}<br>
     ${n.cited_by==null?'citations unknown':n.cited_by+' global citations'} · cited ${n.in_degree}× here · cites ${n.out_degree} here</p>
   <div class="chips">
     <span class="chip role" style="color:${RAW[n.role]}">role: ${n.role}${n.role_source==='judged'?' *judged':''}</span>
     ${n.tags.map(t=>`<span class="chip">${esc(t)}</span>`).join('')}
   </div>
   ${n.unresolved?`<p class="cite" style="color:${RAW.contrarian}">unresolved: ${esc(n.unresolved)}</p>`:''}
   <p class="ab">${n.abstract?esc(n.abstract):'no abstract recorded'}</p>
   <div class="links links3">
     <div><h3>SHARED VOCABULARY [${kin.length}]</h3><ul>${kin.sort((x,y)=>y.j-x.j).map(z=>`<li data-k="${z.m.key}" title="${esc(z.sh.join(' | '))}">${esc(lab(z.m))}</li>`).join('')||'<li style="cursor:default">&mdash;</li>'}</ul></div>
     <div><h3>CITES, IN LIBRARY [${out.length}]</h3><ul>${out.map(m=>`<li data-k="${m.key}">${esc(lab(m))}</li>`).join('')||'<li style="cursor:default">—</li>'}</ul></div>
     <div><h3>CITED BY, IN LIBRARY [${inn.length}]</h3><ul>${inn.map(m=>`<li data-k="${m.key}">${esc(lab(m))}</li>`).join('')||'<li style="cursor:default">—</li>'}</ul></div>
   </div>`;
  document.getElementById('panel').querySelectorAll('li[data-k]').forEach(li=>li.addEventListener('click',()=>sel(li.dataset.k)));
}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
const QI=document.getElementById('q'),QC=document.getElementById('qc');
QI.addEventListener('input',()=>{q=QI.value.trim().toLowerCase();QC.hidden=!q;apply();});
QI.addEventListener('keydown',e=>{if(e.key==='Escape'){QI.value='';q='';QC.hidden=true;apply();}});
QC.addEventListener('click',()=>{QI.value='';q='';QC.hidden=true;apply();QI.focus();});
/* Escape clears the selection, except while the search box has focus, where it
   already clears the query instead. */
document.addEventListener('keydown',ev=>{
  if(ev.key==='Escape'&&ev.target!==QI)deselect();
});
q=QI.value.trim().toLowerCase();QC.hidden=!q;   /* value survives a republish */
document.getElementById('expall').addEventListener('click',()=>{SEC.forEach(s=>collapsed[s.name]=false);relayout();});
document.getElementById('colall').addEventListener('click',()=>{SEC.forEach(s=>collapsed[s.name]=true);relayout();});
const SC=document.getElementById('scrub'),SCN=document.getElementById('scn'),PLAY=document.getElementById('play');
const byRank={};D.nodes.forEach(n=>byRank[n.rank]=n);
SC.max=D.nodes.length;
function scrubTo(v,fromInput){
  tmax=Math.max(1,Math.min(D.nodes.length,v));
  if(!fromInput)SC.value=tmax;
  const n=byRank[tmax];
  SCN.textContent=String(tmax).padStart(String(D.nodes.length).length,'0')+'/'+D.nodes.length+(n?'  \u00b7  '+(n.date_added||'').slice(0,10)+'  '+(n.creators[0]||'?')+' '+(n.year||''):'');
  apply();
}
SC.addEventListener('input',()=>scrubTo(Number(SC.value),true));
let timer=null;
function stop(){clearInterval(timer);timer=null;PLAY.innerHTML='[\u25b6] play';}
PLAY.addEventListener('click',()=>{
  if(timer){stop();return;}
  if(tmax>=D.nodes.length)scrubTo(1);
  PLAY.innerHTML='[\u25a0] stop';
  timer=setInterval(()=>{
    if(tmax>=D.nodes.length){stop();return;}
    scrubTo(tmax+1);
  },180);
});
SC.value=D.nodes.length;
__FJS__

/* ======================== export the graph as an SVG ========================
   What comes out is the drawing as it stands: the current mode, the current
   filters, the replay cutoff, which bands are collapsed, and the selected
   source with its red/green/black links and its named hulls. The clone is taken
   from the live DOM, so there is no second copy of the geometry to drift.

   Two deliberate differences from the page, and only two:

     - NO BACKGROUND. The page's near-black comes from body and .scroller, never
       from the svg, so the export simply omits both and inherits whatever it is
       dropped onto.
     - The NEUTRAL scale is inverted, so what the page draws in white it draws in
       black: the text, the rules, the band stripes, the plain citation grey and
       the white a selected source's vocabulary links turn.

   Every SEMANTIC colour is left exactly as it is. The role palette, the year
   ramp and the red/green direction pair were each measured, and a figure whose
   colours disagree with the map it was read off is worse than a dark figure.
   Only the neutrals move; if one ever needs to, it moves in EXP_INK below and
   nowhere else. */
const EXP_INK={
  '#fafcfb':'#000000',   /* --fg      selected vocabulary link: the white -> black */
  '#cfd3cd':'#2f2c2b',   /* --dim     decade ticks */
  '#584e51':'#6f6764',   /* --dimmer  minor ticks, band notes, the era-break rule */
  '#2b2529':'#d7d2cf',   /* --line    decade gridlines, gutter rule */
  '#161314':'#ebe8e6',   /* alternating band ground */
  '#121011':'#ffffff',   /* --panel   hull label box */
  '#b59790':'#8a655c',   /* --accent  hulls, band + hull labels, leader lines */
  '#b0a3a0':'#6b5f5c'    /* unselected citation links */
};
/* The page styles these by class from its stylesheet, which a standalone file
   does not get, so the export carries its own copy with the values already
   resolved. Same rules, light neutrals. */
const EXP_CSS=`
text{font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.seclbl{font-size:11px;letter-spacing:.17em;fill:#8a655c;font-weight:700}
.secnote{font-size:10.5px;fill:#6f6764;letter-spacing:.04em}
.tick{font-size:10px;fill:#6f6764}
.tick.major{fill:#2f2c2b}
__FXCSS__`;

/* A figure gets a key, because there is no legend above it and no panel beside it.
   It states what the CIRCLES are actually coloured by \u2014 role normally, the year ramp
   when colour-by-year is on, since a role key over year-coloured circles would simply
   be wrong \u2014 and it lists only the values present in the drawing, so a filtered-out
   role has nothing to explain.

   Built in the live svg so every label can be MEASURED with getBBox rather than
   guessed from glyph widths, exactly as the hull labels are; it is cloned with the
   rest and then taken back out. Font is set by attribute, not class, so the width
   measured here is the width the export renders. Nothing repaints in between. */
const KEYH=32;
function buildKey(){
  const g=el('g',{id:'exkey'});
  svg.appendChild(g);
  const yr=(COLOR==='year'&&MODE==='cluster');
  let items;
  if(yr){
    const used=new Set(D.nodes.filter(vis).map(n=>yearBin(n.year)));
    items=FR.year_bins.map((b,i)=>({c:FR.year_ramp[i],t:b.label,i:i})).filter(z=>used.has(z.i));
    if(used.has(-1))items.push({c:'#6B5E73',t:'no year'});
  }else{
    items=ROLES.filter(r=>D.nodes.some(n=>n.role===r&&vis(n))).map(r=>({c:RAW[r],t:r}));
  }
  let x=6;
  items.forEach(it=>{
    g.appendChild(el('circle',{cx:x+6,cy:16,r:6,fill:it.c,'fill-opacity':.75,stroke:it.c}));
    const t=el('text',{x:x+19,y:16,fill:'#2f2c2b','font-size':'10.5px','font-weight':'700',
      'letter-spacing':'.14em','dominant-baseline':'middle',
      'font-family':'"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'});
    t.textContent=it.t.toUpperCase();
    g.appendChild(t);
    x+=19+t.getBBox().width+22;
  });
  return g;
}

function exportSVG(){
  /* every cluster names itself in a figure; put the page back the way it was after */
  const wasAll=LABEL_ALL;
  LABEL_ALL=true;hulls();
  const key=buildKey();
  const c=svg.cloneNode(true);
  key.remove();
  LABEL_ALL=wasAll;hulls();
  c.setAttribute('xmlns',NS);
  c.setAttribute('xmlns:xlink','http://www.w3.org/1999/xlink');
  c.setAttribute('version','1.1');
  /* Whatever the page is not drawing right now is DROPPED rather than carried as
     display:none, so the file is the picture and nothing behind it: the other
     mode's furniture, the filtered-out sources, the collapsed bars, and the
     invisible strips that only exist to catch a click. */
  c.querySelectorAll('.hidden,[display="none"],.sechit').forEach(e=>e.remove());
  c.querySelectorAll('*').forEach(e=>{
    ['fill','stroke'].forEach(a=>{
      if(!e.hasAttribute(a))return;
      const v=EXP_INK[e.getAttribute(a).trim().toLowerCase()];
      if(v)e.setAttribute(a,v);
    });
    /* the page clears display by setting it empty, which is not a legal SVG
       value; outside a browser it is a renderer's guess, so remove it */
    if(e.getAttribute('display')==='')e.removeAttribute('display');
    [...e.attributes].forEach(a=>{
      if(a.name.startsWith('data-')||a.name==='tabindex')e.removeAttribute(a.name);
    });
  });
  /* A saved figure cannot be clicked, so the band notes drop the instruction and
     keep the fact. The root's id goes too: two exported maps inlined into one
     document would otherwise collide. */
  c.querySelectorAll('.secnote').forEach(e=>{
    e.textContent=e.textContent.replace(/\\s*\\u00b7\\s*click to expand$/,'');
  });
  c.removeAttribute('id');
  c.setAttribute('aria-label',MODE==='cluster'
    ? 'Citation clusters across the library'
    : 'Citation timeline across the library');
  /* The key sits above the drawing rather than on it, so everything else shifts
     down by its height and the viewBox grows to match. */
  const kc=c.querySelector('#exkey');
  const body=el('g',{transform:'translate(0,'+KEYH+')'});
  [...c.childNodes].forEach(n=>{if(n!==kc)body.appendChild(n);});
  c.appendChild(body);c.appendChild(kc);
  kc.removeAttribute('id');
  const vb=c.getAttribute('viewBox').split(/[\\s,]+/).map(Number);
  c.setAttribute('viewBox','0 0 '+vb[2]+' '+(vb[3]+KEYH));
  c.setAttribute('height',vb[3]+KEYH);
  const st=document.createElementNS(NS,'style');
  st.textContent=EXP_CSS;
  c.insertBefore(st,c.firstChild);
  const d=el('desc',{});
  d.textContent='Zotero citation map — '+MODE+' view, '
    +c.querySelectorAll('.node').length+' sources, exported '+new Date().toISOString().slice(0,16).replace('T',' ');
  c.insertBefore(d,st);
  return '<?xml version="1.0" encoding="UTF-8"?>\\n'
    +new XMLSerializer().serializeToString(c)+'\\n';
}

function expName(){
  const d=new Date(),p=n=>String(n).padStart(2,'0');
  return 'citation-map-'+(MODE==='cluster'?'clustering':'timeline')+'-'
    +d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+'-'+p(d.getHours())+p(d.getMinutes())+'.svg';
}
document.getElementById('expsvg').addEventListener('click',()=>{
  const s=exportSVG(),name=expName();
  try{
    const u=URL.createObjectURL(new Blob([s],{type:'image/svg+xml;charset=utf-8'}));
    const a=document.createElement('a');a.href=u;a.download=name;
    document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(u),4000);
  }catch(err){}
});
/* A sandboxed frame can refuse a download silently, with no error to catch, so
   the clipboard is a second route rather than a fallback. Neither reports back:
   the button's own :active flash is the whole of the feedback, and a line of
   filename-and-size beside it was noise the reader had to keep re-reading past. */
document.getElementById('expcopy').addEventListener('click',async()=>{
  const s=exportSVG();
  try{await navigator.clipboard.writeText(s);}
  catch(err){
    const ta=document.createElement('textarea');
    ta.value=s;ta.style.cssText='position:fixed;left:-9999px;top:0';
    document.body.appendChild(ta);ta.select();
    try{document.execCommand('copy');}catch(e2){}
    ta.remove();
  }
});

/* the year key is a sequential legend, built from the same ramp the nodes use */
(()=>{const yk=document.getElementById('ykeyb');if(!yk)return;
  yk.innerHTML=FR.year_bins.map((b,i)=>'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:11px">'
    +'<span style="width:11px;height:11px;background:'+FR.year_ramp[i]+';display:inline-block"></span>'
    +b.label+'</span>').join('');})();

document.body.dataset.mode='timeline';
buildBands();
relayout();
applySizes();
placeSize();
styleVoc();
paint();
scrubTo(D.nodes.length);
if(/cluster/i.test(location.hash||''))setMode('cluster');
</script>
"""

out = (TPL.replace("__GEN__", G["generated"])
          .replace("__FCSS__", force.CSS)
          .replace("__FJS__", force.JS)
          .replace("__FXCSS__", force.EXPORT_CSS)
          .replace("__DATA__", json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")))
p = os.path.join(HERE, "out", "map.html")
open(p, "w").write(out)
print("wrote %s (%.0f KB) — %d nodes, %d edges, canvas %dx%d" % (
    p, len(out) / 1024, len(payload["nodes"]), len(payload["edges"]), W, H))
for f in bands:
    secs = bands[f]["sections"]
    print("   band by %-9s %2d rows, %3d lanes  %s"
          % (f, len(secs), sum(s["lanes"] for s in secs),
             " ".join("%s(%d)" % (s["name"][:18], s["count"]) for s in secs)))
