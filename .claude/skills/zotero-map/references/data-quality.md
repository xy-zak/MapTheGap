# Identity resolution, and judging what cannot be computed

## Identity resolution is the main source of error

When an item looks wrongly isolated, **suspect identity resolution before believing the
graph.** Confirm by searching the cached reference lists under `cache/openalex/` for the
candidate work IDs.

Three failure modes, all of which occur in practice:

1. **Books fragment across records.** OpenAlex splits an influential book over
   editions, reprints and reviews, and the highest-cited record is sometimes a *review*
   with its own DOI. Meanwhile the Zotero entry may hold a later reissue DOI that
   nothing cites — so the most important book in a collection shows as isolated. Fixed
   by listing the real target IDs under `work_aliases` in `aliases.json`, which is
   frequently worth several inbound edges each.
2. **Some DOIs have no record at all.** A journal DOI can simply be absent from
   OpenAlex while a different printing of the same work exists as a separate record.
   Record these under `unresolvable` so the build stops retrying and the map can say
   why the item is isolated.
3. **Preprints lack reference lists.** OpenAlex returns `refs: 0` for much preprint
   literature; Semantic Scholar usually has them, matched by arXiv id where there is no
   usable DOI. **An empty Semantic Scholar response is usually a 429, not an absence** —
   check the status code before concluding a paper is unindexed.

### aliases.json

The only hand-maintained data in the repo. Four sections, each carrying a `_comment`:

| key | holds |
|---|---|
| `work_aliases` | Zotero item key → extra OpenAlex work IDs that citing papers actually point at |
| `manual_openalex_ids` | for items with no DOI. Leave empty until an ID is confirmed — a wrong ID is worse than none |
| `manual_edges.edges` | `[citing_key, cited_key]` pairs established by reading the paper, where no index has the reference |
| `unresolvable` | known-bad identifiers, recorded so the build stops retrying and the map can explain itself |

Write full prose into `unresolvable`: which DOI, which record it collides with, and
what was checked. That text reaches the detail panel, and the next person to look at an
isolated node needs to know it was investigated rather than missed.

## Contrarian is judged

A reference list records *that* one work cited another, never whether it agreed.
Polarity cannot be derived from the graph, and `role: contrarian` is therefore the one
classification the build never computes — it reads it from Zotero and lets it win.

A keyword pass over abstracts does not work. "however" fires on the motivation sentence
of nearly every paper ever written.

The procedure: read the abstracts, propose candidates **with the verbatim quote that
justifies each**, and let the person approve individually. Two failure modes produce
most of the false positives:

- **A paper critiquing something the foundational set also critiques is an ally, not an
  opponent.** Shared enemies read as opposition to a keyword pass and as agreement to a
  reader.
- **Gap-filling from inside a programme is not rejection of it.** "Systematic
  development is lacking" is a call for more of the same work, not a challenge to it.

Where the library holds the PDF, prefer it to the abstract:
`~/Zotero/storage/<attachmentKey>/.zotero-ft-cache` is the extracted plain text of a
stored file, far cheaper than parsing the PDF.

## Dates

The **Zotero date wins** over OpenAlex. OpenAlex reports the year of whichever edition
the DOI points at, so a reissue DOI carries the reprint year and drags the work forward
on the timeline — and the Zotero date is the one field the person can correct.

A citation can only point backwards. `build.py` prints a warning for every edge whose
cited work is dated later than the citing one; each is a wrong date on one of the two
records, usually a reissue DOI, and is invisible on the map unless it is called out.
Treat that warning as a to-do list against the library, not as a bug in the build.

## Failures are never cached

Only successful responses go into `cache/`. A cached error is indistinguishable from a
cached negative on the next run, so one bad afternoon becomes a permanent hole in the
graph — this is not hypothetical; it cost several papers their entire reference lists
before the rule existed.

The cost of not caching failures is a re-request per failing identifier per build,
which is nothing. The benefit is that the error text reaches the build summary instead
of being frozen into the cache, where a 404 meaning "not indexed" and a 429 meaning
"ask again" look identical.

Consequences to know:

- The `FETCH FAILED` and `OPENALEX FAILED` lines reappear on every run, and their text
  legitimately varies between 429 and 404 as the upstream service decides. The **set
  and order** of failing identifiers is stable; the message is not.
- Because a failed lookup writes its error into that node's `unresolved` field, a
  `--no-fetch` build and a live build produce genuinely different `graph.json` files
  for any item whose failure is not already covered by `aliases.json`. That is expected.
- A failed reference fetch and a paper that genuinely cites nothing are
  indistinguishable in the edge list. The build reports the counts separately so that
  isolated nodes are not mistaken for findings.
