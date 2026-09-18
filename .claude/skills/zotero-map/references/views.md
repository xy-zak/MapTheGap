# The two views, and the decisions inside them

One page, a mode switch in the header, and the mode in the URL — `map.html#timeline`
and `map.html#clustering` each open in the view they name, so a link means the view it
was read in.

| | **timeline** | **clustering** |
|---|---|---|
| x, y | publication year; facet swimlane | output of a force simulation |
| answers | when did this enter the field, and via which facet | what are the strands, and what holds them together |
| citations | drawn, bowed | drawn straight, centre to centre |
| vocabulary | drawn dashed | drawn dashed, thinner and fainter |
| direction | free from the x-axis: edges point left | colour on selection: red cites, green cited-by |
| controls | band-by facet, expand/collapse | re-settle, colour by role or year |

Search, the role filters, the growth scrubber and the detail panel are shared and
survive a mode switch, including the current selection.

## Timeline: the year scale and the bands

X is a **fixed decade scale**, not data-derived: the earlier span takes 40% of the
width and the recent span the remaining 60%, so crowded recent years get double the
room and the ratio stays put as sources are added rather than shifting under the
reader. `frac()` in `render.py` is the single definition — `force.build()` is handed
that same function for its seed rather than restating it, because two copies
desynchronise the moment the decade break moves.

Bands come from the tags, not from Zotero collections. Each source sits in the band of
its **rarest** tag in the banding facet — rarest across the whole library, so the most
distinctive of an item's tags wins and bands stay usefully sized. Items with no tag in
that facet collect in a final `(unclassified)` band.

Lanes are collision avoidance only: **y carries no data** within a band.

`role:` and any single dominant facet are excluded from banding on purpose. A facet
where one value holds a large share of the library puts most of it in one band, which
is not a layout.

Rejected alternative: agglomerative clustering on Jaccard over all facets. It produced
comparable groups, but membership shifts as sources are added and a band could only be
named by a heuristic. A band that **is** a tag needs no naming.

## Clustering: position is an output

Citations are strong springs, shared vocabulary is a weak one, every node repels every
other, and the arrangement that survives is the library's own structure. Two rules keep
it honest, both load-bearing:

- **Vocabulary is physics but faint ink.** See the invariant in SKILL.md. A tight
  cluster with no solid lines in it is the most informative shape on the page.
- **A node with no link of either kind is not simulated.** Gravity alone would drift it
  to the middle and it would read as belonging there, so it goes to a labelled gutter
  where the page says outright that its position means nothing.

The simulation uses **no RNG**, is seeded deterministically, and iterates pre-sorted
lists, so it must land bit-identically on every run.

### The force constants, and the one operating point

There is **one fixed arrangement**. The map had a spread switcher — compact / balanced
/ distinct, three measured positions on a path through the vocabulary rest length, the
spring-to-repulsion balance and the seed banding — and it is gone. `balanced` is simply
what the layout is now, and its values are plain constants in `force.py`.

| constant | value | what it is |
|---|---|---|
| `CIT_STR` | 1.0 | citation spring — the strong pull |
| `VOC_STR` | 0.5 | vocabulary spring — **flat**, half a citation, whatever tags are shared |
| `CIT_LEN` | 48 (+ both radii) | citation rest length |
| `VOC_LEN` | 100 | vocabulary rest length — 2.1x the citation one |
| `BALANCE` | 0.0369 | spring-to-repulsion ratio |
| `SEED_BAND` | 0.48 | how much of the community-banded seed survives |

Measured at these settings: **separation 1.83x, zero node overlaps, 66% canvas fill.**

Four things underneath that are easy to get wrong:

- **The balance is a ratio, never an absolute strength.** Springs scale by `BALANCE`,
  repulsion by `1/BALANCE`. An earlier control scaled strength alone and did nothing at
  all, because the canvas fit undid it. Both spring types scale by the same `BALANCE`;
  the ratio between a citation and a shared word is the layout's whole claim.
- **A rest length is a target, not a ceiling.** Past `VOC_LEN` a spring pulls its pair
  together; *inside* it the spring pushes them apart. `VOC_LEN` was 497 — 10.4x the
  citation length, about 329 canvas px — and at that length **87 of 148 vocabulary
  springs were compressed and actively repelling**. The visible symptom was a source
  sitting well outside its own hull with four dashed lines running into that hull: the
  springs were satisfied, because a third of a canvas apart was what they asked for.
  At 100 it is 3 of 148. If the dashed links ever look inert again, measure how many
  are compressed before touching `VOC_STR`.
- **`VOC_STR` only means something once the rest length is right.** At `VOC_LEN` 100,
  sweeping it 0.149 / 0.25 / 0.5 / 0.75 / 1.0 gives 1.68x / 1.71x / 1.83x / 1.94x /
  1.97x. The same sweep at 497 gave 1.55x -> 1.52x and looked inert, because a stronger
  compressed spring just pushes harder. Measure the two constants together.
- **A node's total spring budget is normalised to about one link.** The shared
  `spring()` helper biases by `1/min(deg)`, which stops a hub being placed by its degree
  — but it also means four vocabulary links pull about as hard as one. A low-degree
  source with no citations is held very loosely and may settle outside its own outline.
  That is weak evidence shown honestly; "it has four dashed lines" is not grounds to
  expect it to sit tight.
- **But it does move the communities.** The union graph Louvain reads is weighted the
  same way the springs are, so `VOC_STR` changes which clusters exist. Going from the
  old inverse-frequency weights (0.035-0.280) to a flat 0.5 took 8 communities to 7 —
  a two-item group was absorbed. Expect hull changes from a weight change, not layout
  changes.
- A **speed clamp** (`V_MAX`) is load-bearing. Without it a spring-dominated setting
  diverges outright — millions of pixels across — which the canvas fit then quietly
  rescales into a plausible-looking but meaningless picture.

**The numbers are a promise about what the picture looks like, and the physics is
emergent, so re-measure if the library grows substantially.** Port `simStep` and
`fitAndCollide` and run them at the shipped constants; that is how these figures were
obtained. Separation does not vary smoothly with any knob, so nudging a constant by a
step is not meaningful tuning. **Whether one named source lands inside its own hull is
not a tuning target** — it flips on local-minimum noise. The aggregate to watch is how
many sources sit outside their own community outline: 11 of 86 at `VOC_LEN` 497, 9 of
86 at 100. Record what you measure beside the constants, as the comments do.

### The seed, and the circularity in it

`seed` ships **one** y per node: a blend, at `SEED_BAND`, of a golden-ratio sweep over
the node index carrying no community information and the node's own Louvain community,
banded. The blend used to happen in the browser so the switcher could move it; with one
operating point it is done in `force.py` and a single value is shipped.

This matters because the hulls are only an independent check if the layout never sees
the community labels — and the banded component hands them over at t=0, so the
arrangement keeps a memory of the bands it started from and the hulls partly validate a
structure they helped supply.

Isolating just this knob at the shipped settings: 0.00 -> 1.56x, 0.24 -> 1.65x,
**0.48 -> 1.83x**, 0.75 -> 2.16x, 1.00 -> 2.15x, zero overlaps throughout. So the
honest reading is that **the layout does not depend on the banded seed to find its
clusters** — it finds them at 1.56x from a seed carrying no community information at
all. The banding buys 0.27 of separation and is kept for legibility, not to manufacture
the structure. It sits at 0.48 rather than 1.00 because past ~0.75 the seed starts
dictating the answer outright.

(An earlier note here credited 1.12x to banding-off. That came from the old `compact`
preset, which also dropped the balance to 0.002 and stretched the vocabulary springs to
1600 — three changes at once, credited to one of them. Isolate a knob before quoting it.)

### Hull labels

A label is a **tag value with its facet prefix dropped**: `approach: polycentricity`
becomes `POLYCENTRICITY`. That is worth knowing before reading a hull name, because a
bare value can look like it came from nowhere.

The tag is the most **distinctive** one its members share, scored
`(share within cluster) x log(N / library frequency)` — not the commonest, which would
name nearly every hull `cross-cutting` (49 of 94 items). For a small cluster whose
members carry identical tags the share term is 1.0 for every candidate, so the label is
simply the rarest tag they share.

**Candidates are restricted to the forming facets** — `subject:`, `question:`,
`approach:` — which is `AFFINITY` in `build.py`, recorded in `graph.json` as
`"affinity"` and read from there by `force.py` so the two cannot drift. Anything else
is ineligible, `role:` included.

That restriction is new, and it fixed real nonsense. Labelling previously accepted any
facet, so `evidence:` could win: a two-member cluster was called `popular / secondary`
(from `evidence: popular / secondary`, 6 of 94 — the rarest tag its members shared) and
an 18-member one was called `benchmark / experiments`. Neither facet builds vocabulary
edges or is read by Louvain, so both names described something the layout had never
used — the second actively misleading, since those 18 sources were grouped by shared
remote-sensing and self-supervised-learning vocabulary, not by being benchmark papers.
They are `game theory` and `self-supervised learning` now. **If a label ever reads like
it belongs to a different question than the cluster, check which facet it came from
first.**

A community carrying no forming tag at all is held together by citations alone and has
no vocabulary to be named after; it comes out `unlabelled` rather than borrowing a
facet that took no part. None exist on the current library.

Hulls are faint and unlabelled until a source is **selected**, at which point every
cluster whose area covers it turns solid and names itself in a boxed label, pushed
outward from the centre onto clear canvas and joined to its outline by a leader line.
Sitting the label just above the hull put it on top of the very nodes the reader was
looking at.

Every community with at least `HULL_MIN` members gets an outline. That threshold lives
in `force.py` and is shipped in the payload, so the hull count and the "*n* clusters"
readout cannot drift apart. It is **2**: it was 3 on the argument that a ring drawn
around a pair states nothing, but an unringed pair was indistinguishable from two
sources the maths never grouped, and a pair that Louvain made its own community is a
claim worth seeing. On this library that draws 7 hulls rather than 5.

A two-member community has no polygon — the convex hull of two points is a line
segment with no area, and three collinear members collapse the same way. `ringHull()`
handles that by hulling points sampled on each member's **circle** instead of their
centres, which yields a real capsule around the pair that is guaranteed to contain the
node fills. It is reached only when the plain hull has degenerated, so no outline that
already existed is affected. Raising `HULL_MIN` back to 3 would leave that path
unreachable; delete it if you do.

Each hull covers its community's **core** — members within 1.6× the median distance
from its centroid — and its label says how many of the members that is, so a label
ending `[18/22]` means the outline covers 18 of that community's 22 members and four
sit outside it. A convex hull over every member is dragged into a huge
lozenge by the two or three that sit far out, and those lozenges cover each other and
read as one shapeless overlap. The core trim only applies from 3 members up; below
that every member defines the shape.

Coverage is a **point-in-polygon test against the drawn outlines**, not community
membership: hulls genuinely overlap where communities interleave, so a source at a
junction shows every strand it sits in. Its own community is always named too, even
when it is an outlier excluded from that hull's core and therefore outside the outline.

Multiple labels are spread apart in screen space, so the nudging matches the overlap
the reader actually sees. Every cluster naming itself at once competed with the nodes
beneath them; one, on demand, answers the question a reader actually has.

Expect the communities **not** to match the Zotero collections. That is the point.

### Colour by year

Ten **fixed** bins, decades at the old end and five-year bands at the recent end.
Fixed rather than stretched over the library's own earliest and latest year, so the
scale means the same thing on every rebuild and adding one very old source cannot
silently recolour everything else. Empty bins still appear in the key so it reads as a
scale.

**The recent end is finer on purpose.** Most libraries of this kind are heavily
weighted to the last fifteen years, so whole decades there lump most of the library
into two colours. Five-year bands split that usefully; the sparse old decades are
compressed to pay for it. Re-check the distribution if the library's shape changes.

Red for the oldest bin, green for the newest. Red-to-green is the least
colourblind-safe pair there is, so the ramp carries its order in **lightness** as well
as hue, checked under simulated deuteranopia *and* protanopia: monotonic under both, so
old-to-new still reads dim-to-bright for a reader who cannot separate the hues. The
lightness budget is spent where the sources are.

Two things to keep in mind if the ramp is ever re-stepped:

- **Lightness first, hue second.** An attempt that chased raw colour distance put two
  recent bins within 0.01 of the same lightness. It measured well in full colour and
  collapsed completely under deuteranopia. Re-run the monotonicity check under both.
- Adjacent colour distance among the recent bins is near the practical ceiling for
  several steps inside the green half of a red-to-green ramp. It reads as a gradient,
  not as ten separable categories; exact years live in the key and the detail panel.
  Extending the top end into teal was tried and bought nothing.

A source with no year recorded gets neutral grey rather than being folded into the
oldest bin, which would assert a date the library does not have.

## Exporting a figure

`[↓] svg` in the header saves the graph **as it stands** — current mode, filters,
replay cutoff, collapsed bands, and the selected source with its coloured links and
named hulls. It clones the live DOM, so there is no second copy of the geometry that
could drift from what is on screen. `[⧉] copy` puts the same text on the clipboard,
which is the route that still works inside a sandboxed frame where a download is
refused silently.

Two deliberate differences from the page, and only two. **No background** — the
near-black comes from `body` and `.scroller`, never from the `<svg>`, so the export
omits both and inherits whatever it is dropped onto. And the **neutral scale is
inverted**, so what the page draws in white it draws in black.

**Every semantic colour is left exactly as it is.** The role palette, the year ramp and
the red/green direction pair were each measured, and a figure whose colours disagree
with the map it was read off is worse than a dark figure. Only neutrals move, and they
move in `EXP_INK` in `templates/map.js` and nowhere else.

The consequence worth knowing: the year ramp was tuned for contrast against the *dark*
panel, so on a light background its newest bins are washed out. Colour-by-year exports
read poorly on white. Do not fix that by re-stepping the ramp — it is checked under
deuteranopia and protanopia. Give the export its own darkened copy if it ever matters.

Anything not currently drawn is **removed** rather than carried as `display:none`, so a
filtered export is small and holds no ghosts. The class rules ship inside the file as a
`<style>` block with values already resolved; `force.EXPORT_CSS`
(`templates/cluster.export.css`) carries the hull and gutter half of it, mirroring
`force.CSS`. The font is named, not embedded, so a reader without it gets their
monospace.
