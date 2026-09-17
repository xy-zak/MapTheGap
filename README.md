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
force.py      the clustering layout — imported by render.py, never run directly
aliases.json  identity fixes; the only hand-maintained data
cache/        per-DOI API responses — delete a file to force a refetch
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
- **A Zotero Web API key** at `~/.config/zotero-api.conf`, as a curl config file:

  ```
  header = "Zotero-API-Key: <your-key>"
  ```

  Keep it at mode `600` and **outside this repo**. Nothing here reads
  `zotero.sqlite` — the library is reached over the Web API, so your local Zotero
  install and its database are never touched.

Data sources for reference lists: [OpenAlex](https://openalex.org) and
[Semantic Scholar](https://www.semanticscholar.org), both contacted with a polite-pool
mailto. Responses are cached per DOI under `cache/`.

## Usage

```bash
cd ~/Work/GitHub/MapTheGap
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
