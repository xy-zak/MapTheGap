# MapTheGap

A citation map of a Zotero library — a graph of the *real* reference links between
your own sources, not a co-occurrence or keyword cloud. Every source is classified
as **foundational**, **additional**, **contrarian** or **satellite** by its position
in that graph.

The output is a single self-contained HTML page with two views of the same data.

## Pipeline

```
build.py      pull → resolve identity → fetch references → build edges → classify → out/graph.json
render.py     out/graph.json → out/map.html   (both view modes, one page)
vocab.py      the library's live tag vocabulary → the zotero-tag skill's reference
force.py      the clustering layout — imported by render.py, never run directly
templates/    the page itself: map.html + map.css + map.js, and cluster.css,
              cluster.js, cluster.export.css for the clustering layer. Real CSS
              and JS on disk rather than Python string literals.
aliases.json  identity fixes; the only hand-maintained data
cache/        openalex/ and s2/ per-DOI API responses, plus zotero/ — the recorded
              library pull. Delete a file to force a refetch.
```

Computed values (degree, year, citation counts) are recomputed every run and never
stored, so they cannot drift. Only *judged* facts persist: `role: contrarian` tags
in Zotero, and the identity fixes in `aliases.json`.

## The two views

| | **timeline** | **clustering** |
|---|---|---|
| x, y | publication year; facet swimlane | output of a force simulation |
| answers | when did this enter the field, and via which facet | what are my strands, and what holds them together |
| citations | drawn, bowed | drawn straight, centre to centre |
| vocabulary | drawn dashed | drawn dashed, thinner and fainter |

The mode lives in the URL — `map.html#timeline` and `map.html#clustering` each open
in the view they name, so a link means the view it was read in. Search, role filters,
the growth scrubber and the detail panel are shared and survive a mode switch,
including the current selection.

## Requirements

- **Python 3** — standard library only. No `pip install`, no virtualenv.
- **curl** — `build.py` shells out to it for the Zotero calls.
- **`ZOTERO_MAP_MAILTO`** *(optional, recommended)* — a contact address for the
  OpenAlex / Semantic Scholar **polite pool**, which is faster and throttled less
  aggressively than the common pool. Unset is supported: the address is simply
  omitted from the User-Agent and the OpenAlex query, and `build.py` prints a
  warning once per run. No address is hardcoded anywhere in this repo.

  ```bash
  export ZOTERO_MAP_MAILTO=you@example.com
  ```

- **A Zotero Web API key** at `~/.config/zotero-api.conf`, as a curl config file:

  ```
  header = "Zotero-API-Key: <your-key>"
  ```

  Keep it at mode `600` and **outside this repo**. Nothing here reads
  `zotero.sqlite` — the library is reached over the Web API, so your local Zotero
  install and its database are never touched.

Data sources for reference lists: [OpenAlex](https://openalex.org) and
[Semantic Scholar](https://www.semanticscholar.org). Responses are cached per DOI
under `cache/`, and the Zotero pull itself is recorded under `cache/zotero/` so that
`--no-fetch` can run with no network at all. One ordinary run is needed first to
record it. Semantic Scholar rate-limits hard and will return `429` for a few
DOIs on a cold run regardless of the mailto; those failures are deliberately *not*
cached, so simply re-running retries them.

## Skills for Claude Code

The repo ships two skills under `.claude/skills/`, so anyone who clones it gets them
without installing anything:

| skill | covers |
|---|---|
| `zotero-map` | this tooling — the routine, the classification rules, the layout decisions and what to verify before believing a build |
| `zotero-tag` | the prefixed tag vocabulary the map reads — the four facets, the language, a cap of 15 values per facet, and how to merge tags that have grown semantically close |
| `zotero-library` | filing, duplicates, orphaned attachments, missing files, and Zotero Web API mechanics |

The map reads `subject:`, `question:` and `approach:` tags for its three banding facets
and its vocabulary edges; any other prefixed facet can name a cluster; `role:` is the
map's own output and is excluded from the layout. A library with no prefixed tags still
produces a citation graph, but every banding facet collapses into one `(unclassified)`
band and no vocabulary edges form — which is what `zotero-tag` is there to fix.

`vocab.py` records the library's live vocabulary as
`.claude/skills/zotero-tag/references/vocabulary.md`: every facet value with its holder
count, each facet measured against the cap, single-holder values flagged, and merge
candidates proposed for anything over budget. It is generated, gitignored and
regenerable, so it cannot drift from the library:

```bash
python3 vocab.py             # refresh from the library
python3 vocab.py --no-fetch  # from the recorded pull, offline
```

## Usage

```bash
cd ~/Work/GitHub/MapTheGap
export ZOTERO_MAP_MAILTO=you@example.com   # optional; joins the API polite pool
python3 build.py          # add --no-fetch to work from cache only, no network
python3 render.py
xdg-open out/map.html
```

`out/` and `cache/` are gitignored — both are regenerable from the two commands above.

## Layout notes

There are **no arrowheads**. Direction is carried by colour on selection — red for
what the source cites, green for what cites it — and an arrowhead on top of that
was redundant ink.

The clustering layout weights shared vocabulary by *inverse frequency*, not Jaccard:
a shared `subject: cross-cutting` (47 of 94 items) says nearly nothing, while a
shared `question: data governance` (4 of 94) says a great deal, and Jaccard scores
them the same. See the module docstring in `force.py` for the three decisions that
carry that design and the measurements behind each.
