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
| controls | band-by facet, expand/collapse | spread switcher, re-settle, colour by role or year |

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

### The spread switcher

Three buttons — **compact / balanced / distinct** — and **no numbers on the page**. The
reader never wanted the number; it was a proxy for "how hard are the clusters pulled
apart", and the words say that directly.

Each is a fixed position on a path through three quantities. The positions live in
`SPREAD_PRESETS` in `force.py`; `pathOf()` in `templates/cluster.js` derives the rest:

| button | path position `u` | seed banding | vocabulary rest length | balance |
|---|---|---|---|---|
| compact | 0.00 | 0.00 | 1600 | 0.002 |
| **balanced** (default) | 0.24 | 0.48 | 497 | 0.037 |
| distinct | 0.74 | 1.00 | 119 | 0.673 |

Positions are found by **search, not formula**: separation does not vary smoothly along
the path, because the simulation settles into slightly different local minima. A preset
is whichever sampled position lands nearest the target, so nudging one by a step or two
is not meaningful tuning — re-search if a target changes.

**The labels are a promise about what the picture looks like, and the physics is
emergent, so re-measure if the library grows substantially.** Import `simStep` and
`fitAndCollide` from `templates/cluster.js` and run them in node at each position;
that is how the shipped numbers were obtained. Record what you measure beside the
positions in `force.py`, as the current comments do, so the next change can be checked
rather than guessed.

Three things underneath that are easy to get wrong:

- **The balance is a ratio, never an absolute strength.** Springs scale by `ATTR`,
  repulsion by `1/ATTR`. An earlier control scaled strength alone and did nothing at
  all, because the canvas fit undid it.
- **On the springs alone, more attraction means LESS separation.** The vocabulary
  springs are long and reach between clusters, so the more the springs win, the more
  they haul separate strands into one mass. `distinct` sits at a *higher* `ATTR` than
  `compact` only because compact also fades out the seed banding.
- A **speed clamp** (`V_MAX`) is what keeps the range usable. Without it the
  spring-dominated end diverges outright — millions of pixels across — which the canvas
  fit then quietly rescales into a plausible-looking but meaningless picture.

### The seed, and what `compact` does about it

`seed` ships **two** y components per node: a golden-ratio sweep over the node index
carrying no community information, and the node's Louvain community, banded. The
spread switcher blends them.

This matters because the hulls are only an independent check if the layout never sees
the community labels — and the banded component hands them over at t=0, so the
arrangement keeps a memory of the bands it started from and the hulls partly validate a
structure they helped supply. The banded seed is also what puts a floor under
separation: no amount of spring or repulsion tuning gets below it.

So `compact` fades the banding out entirely and `balanced` halves it, which is the only
way a merged view is reachable at all. The honest consequence, which the legend states:
**at the merged end the layout places every source by its links alone; at the separated
end it is partly showing an arrangement the seed handed it.** The default sits at the
banded end because it reads better — a deliberate trade of a modest circularity for
legibility. Do not silently "fix" the default; the blind seed is one click away.

### Hull labels

Hulls are faint and unlabelled until a source is **selected**, at which point every
cluster whose area covers it turns solid and names itself in a boxed label, pushed
outward from the centre onto clear canvas and joined to its outline by a leader line.
Sitting the label just above the hull put it on top of the very nodes the reader was
looking at.

Each hull covers its community's **core** — members within 1.6× the median distance
from its centroid — and its label says how many of the members that is, so a label
ending `[18/22]` means the outline covers 18 of that community's 22 members and four
sit outside it. A convex hull over every member is dragged into a huge
lozenge by the two or three that sit far out, and those lozenges cover each other and
read as one shapeless overlap.

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
