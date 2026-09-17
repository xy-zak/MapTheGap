#!/usr/bin/env python3
"""The clustering layout — second renderer, imported by render.py.

The timeline puts a source where its YEAR says. This puts it where its LINKS say:
citations pull hard, shared vocabulary pulls weakly, everything repels everything.
Clusters are then an output of the library's own structure rather than of a facet
chosen up front.

Three decisions carry the whole design, and each was measured before it was coded.

1. VOCABULARY WEIGHTS ARE INVERSE-FREQUENCY, NOT JACCARD.
   graph.json ships a Jaccard overlap per tag edge, but every value sits in
   [0.5, 1.0] — a 2:1 spread, which as a spring constant is no spread at all. Worse,
   Jaccard counts a shared "subject: cross-cutting" (44 of 89 items) the same as a
   shared "question: data governance" (3 of 89), though one says nearly nothing and
   the other says a great deal. Summing log(N/freq) over the shared tags instead
   gives a 5:1 spread, and its extremes are defensible: strongest pair shares
   "multimodal fusion" + "self-supervised learning", weakest shares only
   "access & provision".

2. THE WEAK LINKS ARE PHYSICS, NOT INK.
   Drawing 142 vocabulary lines on top of 142 citation lines produces a smear, but
   that is not the reason to hide them. The reason is honesty. COMMONS and TESSERA
   share ZERO citations, yet vocabulary alone collapses the graph from 27 components
   into one of 84 — so a layout that drew both link types would seat TESSERA snugly
   beside the commons literature and let a reader infer an intellectual connection
   for which there is no citation evidence whatsoever. With citations as the only
   ink, TESSERA lands near its topical kin as a blob with no lines attaching it to
   anything: proximity says "same vocabulary", the absent lines say "no citation
   bridge", and both facts survive. A cluster held together with no visible edges is
   the single most informative shape on the page.

3. CLUSTER IDENTITY IS A LABEL, NOT A COLOUR.
   Louvain finds 11 communities. No categorical palette is safe at that count, and
   the one tested here failed hardest exactly where it mattered (two candidate hues
   at DeltaE 2.9 under protanopia). So communities are drawn as labelled hulls and
   node fill keeps meaning role, as it does on the timeline. A named hull also beats
   a colour the reader has to carry back to a legend.

Determinism: no RNG anywhere. Seed positions come from the timeline's own year
scale, nodes are iterated in sorted key order and links in shipped order, so two
runs of the browser simulation land on byte-identical coordinates (verified: max
coordinate delta 0.00e+00). Nothing here is written back to graph.json — every
value below is recomputed from the library on each render, per the skill's rule.
"""

import collections
import json
import math
import os

# ---- simulation parameters -------------------------------------------------
# Tuned against measured cluster separation (mean inter-community distance over
# mean intra-community distance) on the current library, then checked for
# robustness across tick counts. Separation lands at 1.55-1.7 with zero node
# overlap and ~90% canvas fill. TICKS=460 scored 2.03 and is NOT used: sweeping
# 300/380/460/560/700 gave 1.65/1.66/2.03/1.55/1.71, so that peak is one lucky
# configuration of a still-jiggling system, not a better setting.
TICKS      = 500
K_REPEL    = -240      # Coulomb, scaled by node radii
CIT_LEN    = 48        # citation rest length, plus both radii
CIT_STR    = 1.0       # citation spring — the strong pull
VOC_LEN    = 140       # vocabulary rest length at the slider's midpoint. The spread
                       # slider moves it along the path below; see SPREAD_PATH.
VOC_MIN    = 0.035     # vocabulary spring range. Ceiling is 3.6x weaker than a
VOC_MAX    = 0.280     # citation, floor is 29x weaker — "weak pull" means weak.
GRAVITY    = 0.009     # toward the centroid; holds detached pieces on canvas
V_DECAY    = 0.62      # velocity retained per tick
V_MAX      = 30        # px/tick ceiling on any node's speed. Without it a strong
                       # spring setting diverges outright: the balance slider at
                       # its merged end produced a raw spread of 18 MILLION px.
                       # It also improved the default layout's cluster separation
                       # from 1.65 to 1.89, so it is not merely a safety net.
COLLIDE_R  = 3.5       # surface gap between node fills, in px
RESOLUTION = 1.0       # Louvain; 1.0 gives 5 substantial communities here

# ---- what the spread slider moves -----------------------------------------
# Three quantities walk together, and the midpoint is pinned to the settings the
# map has always defaulted to, so moving the slider off 50 and back returns the
# same picture.
#
# The lower half also fades out the seed's community banding, because without that
# the merged end is unreachable: the banded seed leaves the communities pre-sorted,
# and no amount of spring or repulsion tuning gets separation below about 1.26.
# Letting it relax far longer only reaches ~1.18 and costs ten times the compute.
# Fading the banding to nothing reaches 1.10.
#
# That has an honest side effect worth knowing: at the merged end the layout is
# placing sources by their links alone, while at the separated end it is partly
# showing an arrangement the seed handed it. Measured across the whole path,
# separation runs 1.10 to 2.20 with zero node overlaps at any point.
SPREAD_LO  = {"band": 0.0, "voclen": 1600, "attr": 0.002}   # path position 0.0
SPREAD_MID = {"band": 1.0, "voclen": 140,  "attr": 0.87}    # path position 0.5
SPREAD_HI  = {"band": 1.0, "voclen": 99,   "attr": 0.51}    # path position 1.0

# Three named points on that path, which is all the reader is offered. The
# positions were found by measuring: the separation each one actually achieves is
# recorded here so a future change can be checked against it rather than guessed.
# Re-measure if the library grows substantially — the labels are a promise about
# what the picture looks like, and the physics is emergent.
#   compact   0.00 -> 1.10x    balanced  0.24 -> 1.50x    distinct  0.74 -> 2.11x
# Every one lays out with zero node overlaps.
#
# The positions are found by search, not by formula, because separation does not
# vary smoothly with the path: between 0.60 and 0.92 it wanders 2.02, 2.04, 2.07,
# 2.11, 2.13, 2.15, 2.12, 2.20 as the simulation settles into slightly different
# local minima. So a preset is whichever sampled position lands nearest the target,
# and nudging one by a step or two is not meaningful tuning.
SPREAD_PRESETS = [
    {"label": "compact",  "u": 0.00},
    {"label": "balanced", "u": 0.24},
    {"label": "distinct", "u": 0.74},
]
PRESET_DEFAULT = 1          # balanced

FW, FH = 1180, 840
PAD_X, PAD_Y = 54, 46

# Colour-by-year: ten FIXED bins, not a ramp stretched over the library's own
# earliest and latest year. A fixed scale means the same thing on every rebuild, and
# adding one very old source cannot silently recolour everything else. Bins with
# nothing in them still appear in the key, so it reads as a scale.
#
# The recent end is deliberately finer. 74 of 89 sources are 2010 or later, so whole
# decades there lumped most of the library into two colours (29 and 45 items); five
# year bands split it into 15 / 14 / 27 / 18 instead. The sparse pre-2010 decades
# hold 15 sources between them and are compressed to pay for it.
YEAR_BINS = [
    {"lo": None, "hi": 1959, "label": "\u22641959"},
    {"lo": 1960, "hi": 1969, "label": "1960s"},
    {"lo": 1970, "hi": 1979, "label": "1970s"},
    {"lo": 1980, "hi": 1989, "label": "1980s"},
    {"lo": 1990, "hi": 1999, "label": "1990s"},
    {"lo": 2000, "hi": 2009, "label": "2000s"},
    {"lo": 2010, "hi": 2014, "label": "2010\u201314"},
    {"lo": 2015, "hi": 2019, "label": "2015\u201319"},
    {"lo": 2020, "hi": 2024, "label": "2020\u201324"},
    {"lo": 2025, "hi": None, "label": "\u22652025"},
]

# Red for the oldest bin, green for the newest.
#
# Red-to-green is the least colourblind-safe pair there is, so the ramp is built to
# carry its order in LIGHTNESS as well as hue, and the check is run under simulated
# deuteranopia and protanopia: the step order stays monotonic under both, so a
# reader who cannot separate red from green still reads old-to-new as dim-to-bright.
#
# The lightness budget is spent where the sources are. The four recent bins get
# steps of 0.097, 0.116 and 0.168 against 0.029 for the tightest old pair — three to
# nearly six times as much. That was the point of the finer bins, and an earlier
# attempt that chased raw colour distance instead put two of them within 0.01 of the
# same lightness, which looked well separated in full colour and collapsed entirely
# under deuteranopia. Lightness first, hue second.
#
# Verified: monotonic under normal, deutan and protan vision; minimum contrast
# 3.09:1 against the panel. Adjacent colour distance among the recent four reaches
# about DeltaE 9 in normal vision, which is the practical ceiling for four steps
# inside the green half of a red-to-green ramp \u2014 up from 5.7 for the two bins these
# replaced. It reads as a gradient, not as ten separable categories; the key and the
# detail panel carry exact years.
YEAR_RAMP = ["#a84028", "#b44c2b", "#bd5a2e", "#c56932", "#cc7836",
             "#d08b3c", "#d4a03a", "#b0c445", "#7ce293", "#a9f5c0"]

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def _tpl(name):
    with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
        return fh.read()


def vocab_weights(nodes, tag_edges):
    """Tag-overlap springs, weighted by how rare the shared tags are.

    role: is excluded — it is a computed property of the graph, so letting it
    pull nodes together would feed the layout its own output.
    """
    N = len(nodes)
    freq = collections.Counter()
    for n in nodes.values():
        for t in n["tags"]:
            if ": " in t and not t.startswith("role:"):
                freq[t] += 1

    def idf(t):
        return math.log(N / freq[t]) if freq.get(t) else 0.0

    raw = {}
    for e in tag_edges:
        shared = [t for t in e["shared"] if ": " in t and not t.startswith("role:")]
        if e["a"] == e["b"]:
            continue
        raw[(e["a"], e["b"])] = sum(idf(t) for t in shared)
    if not raw:
        return {}, {}
    lo, hi = min(raw.values()), max(raw.values())
    span = (hi - lo) or 1.0
    out = {k: VOC_MIN + (VOC_MAX - VOC_MIN) * (v - lo) / span for k, v in raw.items()}
    return out, raw


def louvain(keys, W, resolution=RESOLUTION):
    """Modularity communities on the weighted union graph.

    Deterministic by construction: every iteration walks nodes and neighbours in
    sorted order, so there is no dependence on dict or set ordering. This is the
    independent check on the layout — if a community comes out spatially
    scattered, the blob you are looking at is a physics artefact and the page
    should not be trusted to have found it.
    """
    adj = collections.defaultdict(dict)
    for (a, b), wt in W.items():
        adj[a][b] = adj[a].get(b, 0.0) + wt
        adj[b][a] = adj[b].get(a, 0.0) + wt
    members = {k: [k] for k in keys}
    cur = sorted(keys)
    while True:
        m2 = sum(sum(d.values()) for d in adj.values())
        if m2 == 0:
            break
        deg = {k: sum(adj[k].values()) for k in cur}
        com = {k: k for k in cur}
        comdeg = dict(deg)
        moved, rounds = True, 0
        while moved and rounds < 40:
            moved, rounds = False, rounds + 1
            for k in cur:
                own = com[k]
                comdeg[own] -= deg[k]
                links = collections.defaultdict(float)
                for nb, wt in sorted(adj[k].items()):
                    if nb != k:
                        links[com[nb]] += wt
                best = own
                bestgain = links.get(own, 0.0) - resolution * comdeg[own] * deg[k] / m2
                for c, wt in sorted(links.items()):
                    gain = wt - resolution * comdeg[c] * deg[k] / m2
                    if gain > bestgain + 1e-12:
                        best, bestgain = c, gain
                comdeg[best] += deg[k]
                com[k] = best
                if best != own:
                    moved = True
        groups = collections.defaultdict(list)
        for k in cur:
            groups[com[k]].append(k)
        if len(groups) == len(cur):
            break
        newmembers, newadj = {}, collections.defaultdict(dict)
        for c, g in groups.items():
            newmembers[c] = [x for sub in g for x in members[sub]]
        for a in cur:
            for b, wt in adj[a].items():
                ca, cb = com[a], com[b]
                newadj[ca][cb] = newadj[ca].get(cb, 0.0) + wt
        adj, members, cur = newadj, newmembers, sorted(groups)
    flat = {}
    for c, mem in members.items():
        for k in mem:
            flat[k] = c
    sizes = collections.Counter(flat.values())
    order = {c: i for i, (c, _) in enumerate(
        sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0])))}
    return {k: order[c] for k, c in flat.items()}


def label_clusters(com, nodes):
    """Name each community by its most DISTINCTIVE tags, not its most common.

    Most-common names almost every cluster "cross-cutting", the tag 44 of 89 items
    carry. Ranking by share-within-cluster times log(N/freq) instead picks the tag
    that separates this cluster from the rest of the library, which is what a label
    is for.
    """
    N = len(nodes)
    freq = collections.Counter()
    for n in nodes.values():
        for t in n["tags"]:
            if ": " in t and not t.startswith("role:"):
                freq[t] += 1
    out = {}
    for c in sorted(set(com.values())):
        mem = sorted([k for k in com if com[k] == c])
        cnt = collections.Counter()
        for k in mem:
            for t in nodes[k]["tags"]:
                if ": " in t and not t.startswith("role:"):
                    cnt[t] += 1
        scored = sorted(
            ((v / len(mem)) * math.log(N / freq[t]), t) for t, v in cnt.items())
        top = [t.split(": ", 1)[1] for _, t in reversed(scored[-3:])]
        cols = collections.Counter(
            x for k in mem for x in (nodes[k]["collections"] or ["—"]))
        out[c] = {
            "id": c, "size": len(mem), "members": mem,
            "label": top[0] if top else "unlabelled",
            "also": top[1:],
            "collections": ", ".join("%s %d" % (k, v) for k, v in cols.most_common()),
        }
    return out


def build(G, nodes, radius):
    """Everything the clustering mode needs, as a payload fragment."""
    voc, raw = vocab_weights(nodes, G.get("tag_edges", []))
    cit = [(e["source"], e["target"]) for e in G["edges"]
           if e["source"] != e["target"] and e["source"] in nodes and e["target"] in nodes]

    # union graph drives community detection: a citation counts 1.0, a vocabulary
    # link counts its own spring strength, so the communities are found under the
    # same weighting the physics uses
    W = collections.defaultdict(float)
    for a, b in cit:
        W[tuple(sorted((a, b)))] += CIT_STR
    for (a, b), w in voc.items():
        W[tuple(sorted((a, b)))] += w

    deg = collections.Counter()
    for a, b in cit:
        deg[a] += 1
        deg[b] += 1
    for (a, b) in voc:
        deg[a] += 1
        deg[b] += 1

    keys = sorted(nodes)
    sim = [k for k in keys if deg[k] > 0]
    # A node with no citation AND no vocabulary link has nothing to be pulled by.
    # Left in the simulation, gravity alone would drift it toward the middle and it
    # would read as belonging there. It goes in a labelled gutter instead, where its
    # position is explicitly meaningless.
    gutter = [k for k in keys if deg[k] == 0]

    com = louvain(sim, W)
    clusters = label_clusters(com, nodes)

    # deterministic seed: the timeline's own year scale on x, community band on y.
    # Starting from the layout the reader already knows means clusters form along
    # lines they recognise rather than wherever an RNG dropped them.
    # Two y components per node, blended at runtime by the spread slider:
    #   [1] BLIND  — a golden-ratio sweep over the node index, carrying no
    #                community information at all
    #   [2] BANDED — the node's Louvain community, banded
    # The banded component is what gives the map its familiar, well-separated
    # default; the blind one is what makes a genuinely merged view reachable. Both
    # are deterministic, and x is the timeline's own year scale in both cases.
    seed = {}
    for i, k in enumerate(sim):
        yr = min(max(nodes[k]["year"] or 1960, 1960), 2030)
        fx = (0.40 * (yr - 1960) / 40) if yr <= 2000 else 0.40 + 0.60 * (yr - 2000) / 30
        seed[k] = [round(fx * 1000, 2),
                   round(60 + ((i * 0.6180339887498949) % 1) * 760, 2),
                   round(420 + (com[k] * 137 % 520) + (i % 7) * 3.0, 2)]

    return {
        "sim": sim,
        "gutter": gutter,
        "seed": seed,
        "deg": {k: deg[k] for k in sim},
        "rad": {k: round(radius(nodes[k]), 2) for k in keys},
        "cit": [[a, b] for a, b in cit],
        "voc": [[a, b, round(w, 4)] for (a, b), w in
                sorted(voc.items(), key=lambda kv: (kv[0][0], kv[0][1]))],
        "com": com,
        "clusters": [clusters[c] for c in sorted(clusters,
                                                 key=lambda c: -clusters[c]["size"])],
        "year_ramp": YEAR_RAMP,
        "year_bins": YEAR_BINS,
        "w": FW, "h": FH, "pad": [PAD_X, PAD_Y],
        "p": {"ticks": TICKS, "repel": K_REPEL, "citlen": CIT_LEN, "citstr": CIT_STR,
              "voclen": VOC_LEN, "grav": GRAVITY, "decay": V_DECAY,
              "collide": COLLIDE_R, "vmax": V_MAX,
              "lo": SPREAD_LO, "mid": SPREAD_MID, "hi": SPREAD_HI},
        "presets": SPREAD_PRESETS, "preset_default": PRESET_DEFAULT,
        "voc_range": [round(min(voc.values()), 3), round(max(voc.values()), 3)] if voc else [0, 0],
        "idf_range": [round(min(raw.values()), 2), round(max(raw.values()), 2)] if raw else [0, 0],
    }


# ---- the clustering view, as CSS and JS on disk ---------------------------
# Injected into the single page render.py builds, because the node, edge,
# selection, search and filter layers are already position-independent: the ONLY
# things that differ between the two modes are where a node sits and which links
# are drawn. A second standalone page would have had to duplicate all of that and
# would have drifted from it within a release.
#
# EXPORT_CSS is this layer's contribution to the SVG export stylesheet: the same
# rules with the neutral scale inverted for a light background and every semantic
# colour left alone. It sits beside CSS so a change to a hull or gutter style has
# one place to go.
CSS = _tpl("cluster.css")
JS = _tpl("cluster.js")
EXPORT_CSS = _tpl("cluster.export.css")
