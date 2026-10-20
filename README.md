# MapTheGap

A citation map of a Zotero library — a graph of the *real* reference links between
your own sources, not a co-occurrence or keyword cloud. Every source is classified
as **foundational**, **additional**, **contrarian** or **satellite** by its position
in that graph.

The output is a single self-contained HTML page with two views of the same data.

## Quick start

Double-click the launcher for your system, in the repo folder:

| | double-click | the first time |
|---|---|---|
| macOS | `MapTheGap_Mac.command` | If macOS says it can't verify the file, open *System Settings → Privacy & Security*, scroll down and press **Open Anyway**. |
| Windows | `MapTheGap_Windows.bat` | If Windows asks whether to run it, choose **Run** (or *More info → Run anyway*). |
| Linux | `MapTheGap_Linux.sh` | Choose **Run** when the file manager asks; in GNOME Files, right-click → **Run as a Program**. |

The only thing it needs is Python 3.9 or newer (see [Requirements](#requirements)).
If none is installed, the launcher says so and, on macOS and Windows, opens the
python.org download page.

A terminal window opens alongside the browser tab. That window is the app: leave it
open while you use the map, and close it to stop, or press **quit** on the page.
Double-clicking the launcher again while the app is running just reopens the tab.
From a terminal, the same thing is `python3 app.py` (Windows: `py app.py`).

The app runs at `http://127.0.0.1:8765`, or the next free port if something else
holds that one. The first visit is a setup page that
walks through syncing Zotero, creating a read-only API key and linking it, then builds
the first map. After that the page is the map itself, with one extra strip above the
title: where the library is being read from (*reading zotero app* or *reading
zotero.org*, with the reason behind `[?]`), how many items have changed since the map
was built (new, edited, removed, with titles behind `[show]`), and an **update map**
button that shows each stage, a progress bar and the time left.
Two guide pages hang off the strip, each with the current map's own numbers:
**tagging** (`/tagging`: the four facets, the rules, the live vocabulary against its
cap, and prompts for having Claude tag with the `zotero-tag` skill) and **citations**
(`/citations`: how OpenAlex and Semantic Scholar lookups become lines and roles, and
prompts for chasing a wrong-looking source with the `zotero-map` skill).

Changes are counted from whichever source can be read now, whichever the map was
built from. While Zotero is open with its local API on (see Requirements), that is the
Zotero app, and an edit counts as soon as it is made. Otherwise it is zotero.org, where
an edit made in the Zotero app counts once Zotero has synced it, and one made on
zotero.org, another computer or by the skills counts at once. Items are compared with
the map one by one, on the fields the map shows, so moving between the two loses
nothing; an edit the map cannot show is not counted. The time estimate is learned: each finished update records how long every
stage took on this machine in `cache/app/timings.json`, and the next one starts from
that.

The app is a thin layer over the same scripts. Everything below still works from a
terminal, and `out/map.html` is still a standalone page. `app.py --port N` pins the
port, and `--no-browser` skips opening a tab.

## Pipeline

```
MapTheGap_*   double-click launchers: _Mac.command, _Windows.bat, _Linux.sh
app.py        the local app: setup, the map, change tracking, update with progress
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

- **Python 3.9 or newer**, standard library only. No `pip install`, no virtualenv,
  nothing else to install.
  - *macOS:* use Python from [python.org](https://www.python.org/downloads/) or
    Homebrew (`brew install python`). The python.org installer leaves HTTPS
    certificates unconfigured until you run **Install Certificates.command** in
    *Applications → Python 3.x*. Do that once, or every call fails, and the build
    will tell you so.
  - *Windows:* install from [python.org](https://www.python.org/downloads/) and keep
    *py launcher* ticked; the commands here are then `py …` where macOS and Linux
    say `python3 …`. Python from the Microsoft Store also works, as `python …`.
  - *Linux:* the distribution's `python3` package.
- **A Zotero Web API key**, linked through the app's setup page. It is stored in
  your home folder rather than the repo, at `~/.config/zotero-api.conf` on macOS
  and Linux and `%USERPROFILE%\.config\zotero-api.conf` on Windows. To write it by
  hand instead, the file is one line, in curl's config format so that curl can
  use it too:

  ```
  header = "Zotero-API-Key: <your-key>"
  ```

  On macOS and Linux keep it at mode `600`; on Windows your profile folder is
  already private to your account. **Never put it inside this repo.**
- **Zotero's local API** *(optional, recommended)*. In Zotero 7 or later, tick
  *Allow other applications on this computer to communicate with Zotero* in
  *Settings → Advanced*. While Zotero is open the library is then read from the
  desktop app itself, so edits count before they have synced and no request goes to
  zotero.org. The local API serves only the account Zotero is signed in to, and that
  account must match the key. If it doesn't, or Zotero is closed, or the setting is
  off, the build reads zotero.org instead and says so in its first lines. Nothing
  here opens `zotero.sqlite` directly; the local API goes through Zotero.
- **A contact address** *(optional, recommended)* for the OpenAlex / Semantic
  Scholar **polite pool**, which is faster and throttled less aggressively than the
  common pool. Enter it on the setup page, or for terminal runs set
  `ZOTERO_MAP_MAILTO`:

  | | |
  |---|---|
  | macOS, Linux | `export ZOTERO_MAP_MAILTO=you@example.com` |
  | Windows (PowerShell) | `$env:ZOTERO_MAP_MAILTO = "you@example.com"` |
  | Windows (cmd) | `set ZOTERO_MAP_MAILTO=you@example.com` |

  Unset is supported: the address is simply omitted from the User-Agent and the
  OpenAlex query, and `build.py` prints a warning once per run. No address is
  hardcoded anywhere in this repo.

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
python3 vocab.py             # refresh from the library  (Windows: py vocab.py)
python3 vocab.py --no-fetch  # from the recorded pull, offline
```

## Usage from a terminal

From the repo folder, on macOS or Linux:

```bash
python3 build.py          # add --no-fetch to work from cache only, no network
python3 render.py
open out/map.html         # macOS;  xdg-open out/map.html  on Linux
```

On Windows, in PowerShell or cmd:

```bat
py build.py
py render.py
start out\map.html
```

`out/` and `cache/` are gitignored — both are regenerable from the two commands above.

## Layout notes

There are **no arrowheads**. Direction is carried by colour on selection — red for
what the source cites, green for what cites it — and an arrowhead on top of that
was redundant ink.

In the clustering layout every shared-vocabulary link pulls with the same strength,
half that of a citation, whichever tags the two sources share. Weighting rare shared
tags above common ones was tried and measured; it said something finer but spread the
weights five to one, and the flat weight leaves the layout making one plain claim: a
shared vocabulary is half the evidence of a citation. See the module docstring in
`force.py` for the three decisions that carry the design and the measurements behind
each.
