---
name: zotero-map
description: >
  Build or refresh a citation map of a Zotero library — a graph of the real reference
  links between its own sources, classifying each as foundational, additional,
  contrarian or satellite. Use when asked to map sources, show how a literature
  connects, find which works are foundational or contrarian, refresh the map after
  adding papers, or re-publish the citation timeline. Triggers: citation map, source
  map, "which papers are foundational", "how do my sources relate", refresh the map,
  role tags. Depth: references/views.md (the two views and their physics),
  references/data-quality.md (identity resolution and judging), references/verifying.md
  (what to check before believing a build).
---

# Building the citation map

This skill ships with the MapTheGap repo and describes the tooling in it. Paths below
are relative to the repo root.

```
build.py      pull → resolve identity → fetch references → build edges → classify → out/graph.json
render.py     out/graph.json → out/map.html   (both view modes, one page)
force.py      the clustering layout — imported by render.py, not run directly
templates/    the page itself: map.html, map.css, map.js and the cluster.* trio
aliases.json  identity fixes; the only hand-maintained data
cache/        openalex/ and s2/ per-DOI responses, zotero/ the recorded library pull
out/          generated; both files are disposable and gitignored
```

## Setup

Needed once, before the first run:

- **Python 3 and curl.** Standard library only — no pip, no virtualenv.
- **A Zotero Web API key** at `~/.config/zotero-api.conf`, as a curl config file
  holding one line: `header = "Zotero-API-Key: <key>"`. Keep it mode `600` and
  outside the repo. If it is missing, ask the person to create it in *their own*
  terminal — not through you and not with the `!` prefix, either of which puts the
  key in the transcript.
- **`ZOTERO_MAP_MAILTO`** (optional, recommended) — a contact address that joins the
  OpenAlex and Semantic Scholar *polite pool*, which is faster and throttled less.
  Unset is supported; `build.py` warns once and uses the common pool.

Nothing reads `zotero.sqlite`. The library is reached over the Web API, so the local
Zotero install is never touched.

## The routine

```bash
python3 build.py        # add --no-fetch to make no network calls at all
python3 render.py
```

Then publish `out/map.html`. If a map already exists for this library, **pass the
existing URL** so it updates in place rather than creating a second one.

`--no-fetch` is genuinely offline: it reads the recorded library pull from
`cache/zotero/` and the cached API responses, and makes no requests. It needs one
ordinary run first to record them, and it will say so if there is nothing recorded.

First run on new items is slow. Semantic Scholar is the fallback for anything
OpenAlex has not indexed, and unauthenticated it allows roughly one request per five
seconds. Everything successful is cached, so later runs are fast. Start it and do
something else rather than watching it.

## The one rule that keeps this maintainable

**Computed values are never stored.** Degree, year and citation counts are recomputed
every run, so they cannot drift from the library. Only two things persist:

- `role: contrarian` tags in Zotero — judged, and **sticky**: `build.py` lets a stored
  contrarian value beat its own rules.
- `aliases.json` — identity fixes the APIs get wrong.

Everything else is disposable. If the graph looks wrong, fix the inputs and rebuild;
**never hand-patch `graph.json`.**

## The tags the map reads

The map is only as good as the library's tag vocabulary, and it reads specific
prefixes. A library with none still produces a citation graph, but every banding
facet collapses into one `(unclassified)` band and no vocabulary edges form at all.
See the `zotero-tag` skill for establishing and maintaining a vocabulary. It also
records the live one at `.claude/skills/zotero-tag/references/vocabulary.md`, which
is the quickest way to see what a library actually carries; `python3 vocab.py`
regenerates it.

| facet | read for | where |
|---|---|---|
| `subject:` `question:` `approach:` | the three banding facets, and the vocabulary edges | `BAND_FIELDS` in `render.py`, `AFFINITY` in `build.py` |
| any other prefixed facet, e.g. `evidence:` | **cluster labels only** — it can name a community | `is_facet` in `force.py` |
| `role:` | read as a judged input, excluded everywhere else | `build.py`; excluded by `is_facet` |

`role:` is excluded from the layout deliberately: it is a computed property of the
graph, so letting it weight the springs or name a cluster would feed the layout its
own output.

## Classification

| role | rule |
|---|---|
| `foundational` | in-degree ≥ `max(3, 80th percentile of non-zero in-degree)` |
| `contrarian` | judged only — never computed |
| `additional` | any citation link, below the foundational threshold |
| `satellite` | no citation link to anything else in the library |

Percentile-based so it stays meaningful as the library grows, and the threshold is
printed on the map and recorded in `graph.json` under `threshold.basis`.

The 80th rather than a higher cut because the in-degree distribution is typically
very flat in the middle — a run of percentiles returns the same integer — so the exact
cut lands arbitrarily on whichever value the tail sits on. The choice is between two
stable shelves, not fine tuning. `PCTILE` lives in `classify()` in `build.py`, beside
the comment that justifies it.

After a rebuild, **write back changed `role:` tags** — and report the diff before
writing, rather than silently reclassifying someone's library.

## Contrarian is judged, and must stay that way

A reference list records *that* one work cited another, never whether it agreed.
Polarity cannot be derived from the graph.

A keyword pass over abstracts does not work: "however" fires on the motivation
sentence of nearly every paper ever written. Read the abstracts, propose candidates
**with the verbatim quote that justifies each**, and let the person approve
individually. See references/data-quality.md for the two failure modes that produce
most false positives.

## Invariants — do not quietly change these

Each one was arrived at by measurement and each is load-bearing. The detail is in
references/views.md.

- **Vocabulary is physics, not ink of equal weight.** Tag overlap pulls nodes
  together in the clustering layout, but is drawn thin and faint against solid
  citation lines. Two collections can share zero citations while tag overlap alone
  collapses the graph into a single component, so a group joined only by faint dashes
  shares language and cites nothing. That contrast is the only thing stopping the view
  from asserting an intellectual link for which there is no citation evidence.
- **Vocabulary springs are inverse-frequency, not the stored Jaccard.** Jaccard values
  in `graph.json` all sit in [0.5, 1.0] — as a spring constant that is no spread — and
  a shared near-universal tag counts the same as a shared rare one. Summing
  `log(N/freq)` over the shared tags instead gives a defensible range.
- **Hulls are an independent cross-check, not decoration.** They outline Louvain
  communities computed on the weighted union graph with no knowledge of the geometry,
  so a hull that comes out long and tangled means the maths and the physics disagree
  and that grouping should not be believed. For the same reason there is deliberately
  **no between-community repulsion**: adding it would let the layout see the community
  labels and the check would be worthless.
- **Do not define the cluster areas by a tag facet.** Facet *is* the y-axis of the
  timeline, which is the view built for that question. Measured against the shipped
  layout, every facet produces more areas, more total area and far more overlap per
  node, because the layout places nodes by their links so a facet value scatters
  across it, and items carry more than one tag per facet.
- **No arrowheads.** Direction is carried by colour on selection — red for what the
  source cites, green for what cites it. An arrowhead on top of that is redundant ink.
- **The export buttons are `.exb`, never `.msw`.** `templates/cluster.js` binds every
  `.msw` to the mode switch, so sharing the class hands the export buttons
  `setMode(undefined)`: both views' control rows appear at once and the pressed styling
  moves onto the export buttons. Export is an action, not a view.

## What the map must keep saying

State these on the page. They are easy to forget and they change how it should be read.

- A missing edge means missing index data, **not** absence of influence.
- Disconnected collections may be genuinely disconnected. That is a finding, not a
  rendering fault.
- Books, recordings and blog posts drift to satellite regardless of real importance.
- `satellite` therefore over-counts, and must never be read as "unimportant".
