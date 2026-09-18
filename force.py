#!/usr/bin/env python3
"""The clustering layout — second renderer, imported by render.py.

The timeline puts a source where its YEAR says. This puts it where its LINKS say:
citations pull hard, shared vocabulary pulls weakly, everything repels everything.
Clusters are then an output of the library's own structure rather than of a facet
chosen up front.

Three decisions carry the whole design, and each was measured before it was coded.

1. EVERY VOCABULARY LINK PULLS THE SAME: HALF A CITATION.
   A vocabulary link is worth VOC_STR, flat, whatever tags it shares. The layout
   therefore makes exactly one claim about the weak links — that a shared vocabulary
   is half the evidence of a citation — and none at all about which shared word
   counts for more.

   This replaced an inverse-frequency weighting, log(N/freq) summed over the shared
   tags, which spread the weights 5.2:1 and did say the finer thing: that sharing
   "question: data governance" (4 of 94 items) means more than sharing
   "subject: cross-cutting" (49 of 94). Giving that up was measured, not assumed.

   On the LAYOUT the change is modest but real. Sweeping the flat weight across
   0.149 (the old graded mean) / 0.25 / 0.5 / 0.75 / 1.0 gives separation
   1.68x / 1.71x / 1.83x / 1.94x / 1.97x, zero overlaps throughout. So the weight is
   worth about 0.3x of separation across its plausible range, and 0.5 sits mid-scale.

   An earlier version of this note claimed the weight was nearly inert, measured as
   1.55x -> 1.52x across the same sweep. That measurement was taken while VOC_LEN was
   497, where most vocabulary springs were compressed and pushing apart; a stronger
   spring simply pushed harder, so the sweep cancelled itself out. Fixing the rest
   length is what made this constant mean anything. Measure the two together.

   On the COMMUNITIES it costs something real, and this is the part to know. The
   union graph that Louvain reads is weighted the same way the springs are, so a
   vocabulary link went from 0.035-0.280 to a flat 0.5 there too. That found 7
   communities where the graded weights found 8: the two-item "power & equity" group
   was absorbed, and the five substantial clusters redistributed 22/17/17/14/14 ->
   20/19/18/16/13. Flat weights make shared vocabulary a stronger and more uniform
   argument for grouping, so marginal pairs now get merged rather than left out.

2. THE WEAK LINKS ARE PHYSICS, NOT INK.
   Drawing 148 vocabulary lines on top of 155 citation lines produces a smear, but
   that is not the reason to hide them. The reason is honesty. COMMONS and TESSERA
   share ZERO citations, yet vocabulary alone collapses the graph from 27 components
   into one of 88 — so a layout that drew both link types would seat TESSERA snugly
   beside the commons literature and let a reader infer an intellectual connection
   for which there is no citation evidence whatsoever. With citations as the only
   ink, TESSERA lands near its topical kin as a blob with no lines attaching it to
   anything: proximity says "same vocabulary", the absent lines say "no citation
   bridge", and both facts survive. A cluster held together with no visible edges is
   the single most informative shape on the page.

3. CLUSTER IDENTITY IS A LABEL, NOT A COLOUR.
   Louvain finds 7 communities, 5 of them substantial. No categorical palette is safe
   at that count, and the one tested here failed hardest exactly where it mattered
   (two candidate hues at DeltaE 2.9 under protanopia). So communities are drawn as labelled hulls and
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
# robustness across tick counts. At the shipped settings separation is 1.83x with
# zero node overlap and 66% canvas fill.
#
# The sweep 300/380/460/500/560/700 gives 1.71/1.77/1.82/1.83/1.85/1.90 — monotonic,
# no overlaps anywhere, and still creeping upward at 700, so the layout is settled
# rather than converged. 500 is the knee: past it each 200 ticks buys under 0.05x.
# An older version of this comment recorded 1.65/1.66/2.03/1.55/1.71 for the same
# sweep, which was noise from the era when most vocabulary springs were compressed;
# the non-monotonic 2.03 at 460 ticks does not reproduce.
TICKS      = 500
K_REPEL    = -240      # Coulomb, scaled by node radii. Divided by BALANCE at runtime.
CIT_LEN    = 48        # citation rest length, plus both radii
CIT_STR    = 1.0       # citation spring — the strong pull
VOC_STR    = 0.5       # vocabulary spring — flat, half a citation. See note 1 above.
VOC_LEN    = 100       # vocabulary rest length: the distance the spring WANTS, not a
                       # maximum. Above it the spring pulls together, below it the
                       # spring pushes apart. 2.1x CIT_LEN, so a vocabulary pair
                       # settles ~75 canvas px apart against ~36 px for a cited pair:
                       # near, but visibly less tight, which is the distinction the
                       # two link types are supposed to draw.
                       #
                       # This was 497 — 10.4x CIT_LEN, about 329 canvas px, a third of
                       # the width. At that length 87 of the 148 vocabulary springs
                       # (59%) sat SHORTER than rest and were actively pushing their
                       # endpoints apart, so the dashed lines mostly repelled. It is
                       # 3 of 148 (2%) now. The symptom was a source sitting well
                       # outside its own hull while four dashed lines ran from it to
                       # members of that hull; the springs were satisfied by that,
                       # because 329 px apart was what they were asking for.
GRAVITY    = 0.009     # toward the centroid; holds detached pieces on canvas
V_DECAY    = 0.62      # velocity retained per tick
V_MAX      = 30        # px/tick ceiling on any node's speed. Without it a strong
                       # spring setting diverges outright: the lowest balance the old
                       # spread control could reach produced a raw spread of 18
                       # MILLION px. Nothing on the page can reach that setting now,
                       # but the ceiling is not merely a safety net — it also
                       # improved the layout's separation from 1.65 to 1.89.
COLLIDE_R  = 3.5       # surface gap between node fills, in px
RESOLUTION = 1.0       # Louvain; 1.0 gives 7 communities, 5 of them substantial
HULL_MIN   = 3         # smallest community that gets a drawn outline: three sources
                       # make a cluster. A ring drawn around a pair states nothing,
                       # and on this library two of the seven communities Louvain
                       # finds are pairs, so five hulls are drawn.
                       #
                       # 2 was tried and is a defensible alternative: it makes every
                       # community Louvain found visible rather than only the big
                       # ones. The cost of 3 is precisely that — an un-outlined pair
                       # is indistinguishable on the page from two nodes the maths
                       # never grouped. The cost of 2 is a ring that asserts a
                       # grouping too small to read as one.
                       #
                       # This governs only what is OUTLINED. Community membership,
                       # the springs and the cluster labels are all untouched by it,
                       # so changing it cannot move a node: separation, mean settle
                       # speed and the overlap count are identical at either value.
                       #
                       # ringHull() in templates/cluster.js still has a reason to
                       # exist at 3. It covers two degeneracies, not one: a community
                       # of two, unreachable at this setting, AND three collinear
                       # members, which a size-3 community can still produce. Do not
                       # delete it on the strength of this constant.

# ---- the one operating point ----------------------------------------------
# The map had a spread switcher here — compact / balanced / distinct, three measured
# positions on a path that moved the vocabulary rest length, the spring-to-repulsion
# balance and the seed banding together. It is gone; `balanced` is now simply what
# the layout is, and these two constants are the values it stood for.
#
# BALANCE is a RATIO, not a strength: springs are multiplied by it and repulsion
# divided by it, which is the only form that survives the canvas fit afterwards.
# Both spring types are scaled by the same BALANCE, never one against the other —
# the ratio between a citation and a shared word is the whole claim the layout makes.
# At 0.0369 the effective constants are a 0.037 citation spring, a 0.018 vocabulary
# spring and -6497 repulsion, so this layout is repulsion-dominated by a wide margin.
#
# SEED_BAND is the honest awkwardness. The seed blends two deterministic components:
# a blind golden-ratio sweep over the node index, and the node's own Louvain
# community, banded. At 0.48 the layout keeps roughly half a memory of the community
# structure it started from, which means the hulls partly validate an arrangement
# they helped supply.
#
# Isolating just this knob at the settings above: 0.00 -> 1.56x, 0.24 -> 1.65x,
# 0.48 -> 1.83x, 0.75 -> 2.16x, 1.00 -> 2.15x, zero overlaps throughout. So the
# circularity buys 0.27 of separation over seeding blind, and the honest reading is
# that the layout does NOT depend on the banded seed to find its clusters — it finds
# them at 1.56x from a seed carrying no community information at all. The banding is
# kept for legibility, not to manufacture the structure, and 0.48 rather than 1.00
# because past ~0.75 the seed starts dictating the answer outright.
#
# (An earlier version of this comment claimed 1.12x for banding-off. That number came
# from the old `compact` preset, which also dropped the balance to 0.002 and stretched
# the vocabulary springs to 1600 — three changes at once, credited to one of them.)
#
# Measured at these settings: separation 1.83x, zero node overlaps, 66% canvas fill.
# Re-measure if the library grows substantially — the physics is emergent, and
# separation does not vary smoothly with any of these knobs, so nudging one by a step
# is not meaningful tuning. Whether one particular source lands inside its own hull
# is especially not a tuning target: that flips on local-minimum noise, and the honest
# aggregate to watch is how many sources sit outside their own community outline
# (11 of 86 at VOC_LEN 497, 9 of 86 at 100).
BALANCE    = 0.0369    # spring-to-repulsion ratio
SEED_BAND  = 0.48      # how much of the community-banded seed survives

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


# The facets that actually FORM a cluster. build.py makes a vocabulary edge only out
# of these, and Louvain reads nothing but those edges and the citations, so a facet
# outside this list has no hand in any grouping the map shows.
#
# It is therefore also the only list a cluster NAME may come from. It was not:
# labelling accepted any facet, and on this library that let `evidence:` name two of
# the seven hulls — including an 18-member one called "benchmark / experiments",
# which told the reader those sources were grouped for being benchmark papers when
# what grouped them was shared remote-sensing and self-supervised-learning
# vocabulary. A name that describes something the physics never saw is worse than a
# duller name that describes what it did.
#
# graph.json records the builder's own list as "affinity" and build() prefers it, so
# the two cannot drift; this is the fallback for a graph written before that field.
FORMING_FACETS = ("subject:", "question:", "approach:")


def is_facet(tag: str) -> bool:
    """A tag that carries meaning for the layout.

    role: is excluded wherever this is used — it is a computed property of the
    graph, so letting it weight the springs or name a cluster would feed the
    layout its own output.

    This is the WIDE test, and it answers "is this a facet tag at all". It is not
    the test for "may this name a cluster" — that is FORMING_FACETS above, which is
    narrower, and conflating the two is the bug described there.
    """
    return ": " in tag and not tag.startswith("role:")


def tag_freq(nodes: dict) -> collections.Counter:
    """How many items carry each facet tag.

    Shared by the springs and the cluster labels, which both need it and
    previously counted it separately.
    """
    freq = collections.Counter()
    for n in nodes.values():
        for t in n["tags"]:
            if is_facet(t):
                freq[t] += 1
    return freq


def vocab_pairs(nodes, tag_edges):
    """The pairs a vocabulary spring joins. Every one pulls with VOC_STR.

    build.py has already done the deciding: it emits a tag edge only where the two
    sources share at least half their subject/question/approach vocabulary AND no
    citation joins them, so there is nothing left here to grade. Which tags are
    shared no longer changes the force — see note 1 in the module docstring for what
    that gave up and what it was measured to cost.

    `nodes` is unused now and kept in the signature deliberately: it is what a
    frequency-aware weighting would need, and re-grading these springs is the most
    likely future change to this function.
    """
    del nodes
    return sorted({(e["a"], e["b"]) for e in tag_edges if e["a"] != e["b"]})


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


def label_clusters(com, nodes, forming=FORMING_FACETS):
    """Name each community by its most DISTINCTIVE tags, not its most common.

    Most-common names almost every cluster "cross-cutting", the tag 49 of 94 items
    carry. Ranking by share-within-cluster times log(N/freq) instead picks the tag
    that separates this cluster from the rest of the library, which is what a label
    is for.

    Candidates are restricted to `forming` — the facets that built the vocabulary
    edges. See FORMING_FACETS for why a wider choice produced names that described
    nothing the layout had used.

    A community carrying no forming tag at all cannot have made a vocabulary edge, so
    it is held together by citations alone and there is no vocabulary to name it
    after. Those come out "unlabelled" rather than borrowing a facet that took no
    part; none exist on the current library.
    """
    N = len(nodes)
    freq = tag_freq(nodes)
    out = {}
    for c in sorted(set(com.values())):
        mem = sorted([k for k in com if com[k] == c])
        cnt = collections.Counter()
        for k in mem:
            for t in nodes[k]["tags"]:
                if is_facet(t) and t.startswith(forming):
                    cnt[t] += 1
        scored = sorted(
            ((v / len(mem)) * math.log(N / freq[t]), t) for t, v in cnt.items())
        top = [t.split(": ", 1)[1] for _, t in reversed(scored[-1:])]
        out[c] = {
            "id": c, "size": len(mem), "members": mem,
            "label": top[0] if top else "unlabelled",
        }
    return out


def build(G, nodes, radius, frac):
    """Everything the clustering mode needs, as a payload fragment."""
    voc = vocab_pairs(nodes, G.get("tag_edges", []))
    cit = [(e["source"], e["target"]) for e in G["edges"]
           if e["source"] != e["target"] and e["source"] in nodes and e["target"] in nodes]

    # union graph drives community detection: a citation counts 1.0, a vocabulary
    # link counts its own spring strength, so the communities are found under the
    # same weighting the physics uses
    W = collections.defaultdict(float)
    for a, b in cit:
        W[tuple(sorted((a, b)))] += CIT_STR
    for a, b in voc:
        W[tuple(sorted((a, b)))] += VOC_STR

    deg = collections.Counter()
    for a, b in cit:
        deg[a] += 1
        deg[b] += 1
    for a, b in voc:
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
    # The skill requires two runs to land bit-identically, and names the failure it
    # guards against: "a nonzero delta means an RNG or an unsorted iteration has
    # crept in". louvain() is the one place that could reintroduce it, so the
    # property is asserted rather than trusted — recompute from a reversed node
    # order and require the same answer. 1.6ms on this library.
    assert louvain(sim[::-1], W) == com, (
        "louvain is order-dependent: an unsorted iteration has crept in")
    # The builder records which facets it made edges from; prefer that over the
    # fallback constant, so changing AFFINITY in build.py cannot leave the labels
    # naming clusters after facets that no longer form them.
    forming = tuple(G.get("affinity") or FORMING_FACETS)
    clusters = label_clusters(com, nodes, forming)

    # deterministic seed: the timeline's own year scale on x, community band on y.
    # Starting from the layout the reader already knows means clusters form along
    # lines they recognise rather than wherever an RNG dropped them.
    #
    # y blends two deterministic components at SEED_BAND:
    #   BLIND  — a golden-ratio sweep over the node index, carrying no community
    #            information at all
    #   BANDED — the node's Louvain community, banded
    # The spread switcher used to blend these in the browser and shipped both
    # components to do it. With one operating point there is one blend, so it is done
    # here and a single y is shipped — the browser no longer holds a knob nothing can
    # turn. See SEED_BAND above for why the banded half is kept at all.
    seed = {}
    for i, k in enumerate(sim):
        # `frac` is the timeline's own year scale, passed in rather than restated.
        # This was a second copy of that formula, with 1960/2000/2030 and the 0.40
        # decade break written out again, so moving the timeline's break would have
        # silently desynchronised the clustering seed from the view it seeds from.
        blind = 60 + ((i * 0.6180339887498949) % 1) * 760
        banded = 420 + (com[k] * 137 % 520) + (i % 7) * 3.0
        seed[k] = [round(frac(nodes[k]["year"]) * 1000, 2),
                   round(blind + SEED_BAND * (banded - blind), 2)]

    return {
        "sim": sim,
        "gutter": gutter,
        "seed": seed,
        "deg": {k: deg[k] for k in sim},
        "rad": {k: round(radius(nodes[k]), 2) for k in keys},
        "cit": [[a, b] for a, b in cit],
        "voc": [[a, b] for a, b in voc],
        "com": com,
        "clusters": [clusters[c] for c in sorted(clusters,
                                                 key=lambda c: -clusters[c]["size"])],
        "hullmin": HULL_MIN,
        "year_ramp": YEAR_RAMP,
        "year_bins": YEAR_BINS,
        "w": FW, "h": FH, "pad": [PAD_X, PAD_Y],
        "p": {"ticks": TICKS, "repel": K_REPEL, "citlen": CIT_LEN, "citstr": CIT_STR,
              "vocstr": VOC_STR, "voclen": VOC_LEN, "grav": GRAVITY, "decay": V_DECAY,
              "collide": COLLIDE_R, "vmax": V_MAX, "balance": BALANCE},
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
