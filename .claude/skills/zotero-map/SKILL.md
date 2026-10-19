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
app.py        the local app (setup page, map, change count, update button) over the two below
build.py      pull → resolve identity → fetch references → build edges → classify → out/graph.json
render.py     out/graph.json → out/map.html   (both view modes, one page)
force.py      the clustering layout — imported by render.py, not run directly
templates/    the page itself: map.html, map.css, map.js and the cluster.* trio
aliases.json  identity fixes; the only hand-maintained data
cache/        openalex/ and s2/ per-DOI responses, zotero/ the recorded library pull
out/          generated; both files are disposable and gitignored
```

## Setup

Needed once, before the first run. Everything here works the same on macOS, Windows
and Linux.

- **Python 3.9 or newer.** Standard library only — no pip, no virtualenv, no curl.
  On Windows the interpreter is usually `py` (or `python`) where this skill says
  `python3`; check which one answers before running anything.
- **A Zotero Web API key** at `~/.config/zotero-api.conf` (`%USERPROFILE%\.config\`
  on Windows), as a curl config file holding one line:
  `header = "Zotero-API-Key: <key>"`. Outside the repo, and mode `600` on macOS and
  Linux. If it is missing, ask the person to run `python3 app.py` (Windows:
  `py app.py`) and link it on the setup page, or to create the file in *their own*
  terminal — never through you and not with the `!` prefix, either of which puts the
  key in the transcript.
- **A contact address** (optional, recommended) that joins the OpenAlex and Semantic
  Scholar *polite pool*, which is faster and throttled less. Set on the app's setup
  page, or as `ZOTERO_MAP_MAILTO` for terminal runs. Unset is supported; `build.py`
  warns once and uses the common pool.
- **macOS with python.org Python:** if a build stops saying Python could not verify
  an HTTPS certificate, the person needs to run *Install Certificates.command* in
  *Applications → Python 3.x* once. It is not a network problem; retrying won't help.

Nothing reads `zotero.sqlite`. The library is reached over the Web API, so the local
Zotero install is never touched.

## Pointing it at a different library

The tooling makes no assumption about what a library is *about*: the roles come from
the citation graph, the threshold is a percentile of that library's own in-degree, and
the bands and cluster names come from whatever tag values it carries. A few things in
the repo were nonetheless set for the library it was developed against, and need
checking the first time it is used on another:

- **`aliases.json` is per-library data.** It is keyed by Zotero item keys, which only
  mean something in the library they came from. Starting on a new library, empty the
  four sections (keep the `_comment` keys) and build up its own fixes. Entries naming
  items the library does not hold are skipped with a warning, never applied.
- **The year range is fixed at 1960-2030.** Older sources are clamped to the left edge.
  For a library of older work, change the range in `render.py` and the colour bins in
  `force.py` together - see "Timeline" and "Colour by year" in references/views.md.
- **The tag vocabulary is the library's own.** Only the three facet *prefixes* are fixed
  (see below); every value under them is built from that library's items with the
  `zotero-tag` skill. An untagged library still maps, as one band with no vocabulary
  links.
- **Personal libraries only.** `build.py` reads `users/<id>`; a Zotero group library
  (`groups/<id>`) is not supported.
- **The numbers in references/views.md** describe the development library. Expect
  different ones; re-measure rather than tune towards them.

## The routine

For a person, double-clicking `MapTheGap_Mac.command` (macOS), `MapTheGap_Windows.bat` (Windows)
or `MapTheGap_Linux.sh` (Linux) is the whole routine. Each one finds Python and runs
`app.py`, which links the key, shows how many
items changed since the map was built, and rebuilds on a button. It runs exactly the
two commands below (`build.py --progress` writes JSON progress to stderr for it, and
leaves stdout unchanged). From Claude Code, run them directly:

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
- **Every vocabulary link pulls the same: `VOC_STR`, half a citation.** Not the stored
  Jaccard, whose values all sit in [0.5, 1.0] and so give the springs no spread, and no
  longer inverse-frequency weights, which said the finer thing (a rare shared tag
  means more than a near-universal one) at the cost of a 5:1 spread the layout made
  little of. The layout therefore makes exactly one claim about the weak links. The
  same weight feeds the graph Louvain reads, so changing it changes the communities,
  not only the picture. Note 1 in `force.py` has the measurements.
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
