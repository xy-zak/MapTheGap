# Verify every build

Run these before believing a map, and report what they found rather than asserting
success.

## Determinism

**Two consecutive runs must produce byte-identical `graph.json`.**

```bash
python3 build.py --no-fetch && python3 -c "import hashlib; print(hashlib.sha256(open('out/graph.json','rb').read()).hexdigest())"
python3 build.py --no-fetch && python3 -c "import hashlib; print(hashlib.sha256(open('out/graph.json','rb').read()).hexdigest())"
```

Hashed in Python rather than with `sha256sum`, which macOS does not ship. Every output
file is written with LF line endings on every platform, so a Windows build hashes the
same as a Linux one.

This has caught a real bug: iterating Python sets gave unstable edge ordering under
hash randomisation. Sort before iterating, and sort the final edge list.

**The clustering simulation must land bit-identically too.** It uses no RNG and is
seeded from the timeline's own year scale. Load the page twice and compare the settled
coordinates; a nonzero delta means an RNG or an unsorted iteration has crept in.
`force.build()` also asserts that the Louvain communities are unchanged when the node
list is reversed, which catches the same class of bug at build time.

Two orderings are load-bearing and easy to break while tidying: `resolve_identity`
iterates the items in the order Zotero returned them, and `fetch_references` iterates
`nodes.items()` rather than `sorted(nodes)`. Both determine the order of the failure
lines in the build summary. The `roles:` line is `dict(Counter(...))`, which preserves
first-seen order — an aggregate that is secretly an ordering.

## The library was fully pulled

`build.py` paginates, but confirm the item count is plausible against what the person
believes they have. The Zotero API caps a page at 100; before pagination existed the
pull silently truncated and printed the smaller number as though nothing had happened.
`Total-Results` in the response headers is the authority.

## Edges against ground truth

Pick several edges and confirm the cited author actually appears in the citing paper's
`~/Zotero/storage/<key>/.zotero-ft-cache`. A year mismatch is usually a
date-normalisation artefact rather than a false edge; read the surrounding text before
assuming an error.

## Ranking sanity

The foundational set should be defensible to someone who knows the field. If it is not,
the threshold or the aliases are wrong — not the field.

## Artifact matches data

Node and edge counts on the page equal `graph.json`, and `simulated + unlinked` equals
the node count. The page derives its own totals from the arrays it was handed rather
than being told them, so a mismatch means a real inconsistency.

## Clustering is converged and separated

Mean node speed at the end of the settle should be ~0.001 px/tick or less, cluster
separation (mean inter-community distance over mean intra-community) comfortably above
1.5, and **zero node overlaps**.

Do not tune to a peak tick count. Sweeping tick counts produces a scatter in which one
value looks markedly better; that is one lucky local minimum of a converged system, not
a better setting. `force.py` records the sweep beside `TICKS` for this reason.

## Never drive the simulation off animation frames

It used to run ten ticks per `requestAnimationFrame`, so its 500 ticks needed 50 frames
merely to exist. Anything that throttles rAF — a background tab, or headless Chrome,
which grants about eleven frames — left the layout stranded part-cooled with `settled`
still false and no hulls at all.

All 500 ticks are a couple of million pair operations and take about a tenth of a
second, so they run **synchronously** and only the journey is animated, with progress
measured in milliseconds rather than frames. A timer finishes the transition if rAF
never does, so the layout cannot be stranded mid-interpolation with `settling` stuck
true — which would also block the next re-settle.

This burned two review passes: one judged pictures 100 ticks in rather than 500, and
the other read hull counts off a part-way interpolation. **When checking clustering
headless, wait for `settled && !settling` before trusting anything on screen.**

## Look at it

Two bugs here were invisible to every numeric check and obvious on screen: hulls gated
on the settle finishing, so a throttled tab got none; and translucent hull fills
compounding into muddy overlap. Render the page and open it.

Headless is enough for the structural checks, and worth scripting. Driving the page
over the Chrome DevTools Protocol and evaluating expressions against its own globals
covers: node and path counts against `graph.json`, `settled && !settling`, hull count
against communities of size ≥ 3, every node having finite coordinates, no `NaN` in any
path `d`, selection naming its covering hulls, search and the role filters moving the
status line, `exportSVG()` parsing as well-formed SVG, and the `#timeline` /
`#clustering` fragments opening in the view they name. Check the console is clean while
you are there.

A caveat that will waste time otherwise: navigating from `map.html` to
`map.html#clustering` in the same tab is a **same-document** change, so the page script
never re-runs and the fragment appears not to work. Use a fresh browser instance per
fragment test.
