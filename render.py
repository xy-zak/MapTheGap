#!/usr/bin/env python3
"""Render out/graph.json as out/map.html (a self-contained artifact page).

One continuous timeline. X is publication year on a fixed decade scale, so every
edge points backwards in time. Sections stack vertically in the same coordinate
space and the canvas grows to fit them, so a source belonging to two collections —
or an edge crossing between them — needs no change to the layout.
"""

import json, os, math, re

import force   # the clustering layout lives there; see its module docstring

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")


def _tpl(name):
    with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
        return fh.read()


def load_template():
    r"""The page shell with its own stylesheet and script composed back in.

    Three files rather than one Python string literal, so the CSS is CSS on disk
    and the JS is JS on disk, where an editor, a formatter and a linter can all
    see them. It also removes a class of bug that was invisible before: an escape
    written for the browser had to survive Python's own unescaping first, so the
    click-to-expand regex below had to be spelled \\s inside the literal to mean
    \s in the page.

    Composition is deliberately a separate step from filling in data. The
    included files carry placeholders of their own - __FJS__ sits inside map.js -
    and the single fill pass below does not rescan what it has just inserted.
    """
    html = _tpl("map.html")
    for token, name in (("__CSS__", "map.css"), ("__JS__", "map.js")):
        html = html.replace(token, _tpl(name))
    return html


PLACEHOLDER = re.compile(r"__([A-Z]+)__")


def fill(template, values):
    """Substitute every __TOKEN__ in one pass, refusing anything unexpected.

    One pass rather than a chain of str.replace: chained replacement rescans the
    text it has already inserted, so a token appearing inside injected content
    would be substituted a second time. An unknown token and an unused value both
    raise, which turns a typo into a build-time error rather than a literal
    __TOKEN__ left sitting in the page.
    """
    seen = set()

    def one(m):
        key = m.group(1)
        if key not in values:
            raise KeyError("template refers to __%s__, which has no value" % key)
        seen.add(key)
        return values[key]

    out = PLACEHOLDER.sub(one, template)
    unused = sorted(set(values) - seen)
    if unused:
        raise KeyError("values the template never used: %s" % ", ".join(unused))
    return out

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
# The payload keys bands by facet name without the colon, so the default has to be
# one of those names. Asserted because the failure was otherwise a KeyError from
# inside a comprehension, nowhere near the two lines that disagreed.
assert DEFAULT_BAND in [f.rstrip(":") for f in BAND_FIELDS], (
    "DEFAULT_BAND %r is not one of BAND_FIELDS %r" % (DEFAULT_BAND, BAND_FIELDS))


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


def build_bands(nodes, field):
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


def main():
    with open(os.path.join(HERE, "out", "graph.json"), encoding="utf-8") as fh:
        G = json.load(fh)
    nodes = {n["key"]: n for n in G["nodes"]}
    bands = {f.rstrip(":"): build_bands(nodes, f) for f in BAND_FIELDS}

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
        "force": force.build(G, nodes, radius, frac),
    }


    out = fill(load_template(), {
        "GEN": G["generated"],
        "FCSS": force.CSS,
        "FJS": force.JS,
        "FXCSS": force.EXPORT_CSS,
        # <\/ so a title or abstract containing "</script>" cannot close the data block
        "DATA": json.dumps(payload, separators=(",", ":")).replace("</", "<\\/"),
    })
    p = os.path.join(HERE, "out", "map.html")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(out)
    print("wrote %s (%.0f KB) — %d nodes, %d edges, canvas %dx%d" % (
        p, len(out) / 1024, len(payload["nodes"]), len(payload["edges"]), W, H))
    for f in bands:
        secs = bands[f]["sections"]
        print("   band by %-9s %2d rows, %3d lanes  %s"
              % (f, len(secs), sum(s["lanes"] for s in secs),
                 " ".join("%s(%d)" % (s["name"][:18], s["count"]) for s in secs)))


if __name__ == "__main__":
    main()
