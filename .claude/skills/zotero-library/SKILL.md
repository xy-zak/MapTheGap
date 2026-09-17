---
name: zotero-library
description: >
  Tag, file and tidy a Zotero library through the Zotero Web API, including the
  prefixed tag vocabulary the citation map reads. Use when asked to tag papers, design
  or extend a tag vocabulary, file loose items into collections, find or merge
  duplicates, fix orphaned attachments, flag citations with no PDF, or audit a library.
  Triggers: Zotero, zotero.sqlite, "my library", "tag these papers", "set up a tag
  vocabulary", "duplicates in Zotero", "which papers am I missing the PDF for". API
  mechanics and failure modes live in references/zotero-api.md.
---

# Organising a Zotero library

A library is someone's research memory. Every write syncs to their account and every
device, so the standing bias is: **read widely, write narrowly, verify after.**

This skill ships with the MapTheGap repo because the citation map depends on the tag
vocabulary described below — a library with no prefixed tags still produces a citation
graph, but every banding facet collapses into one `(unclassified)` band and no
vocabulary edges form. It is useful on its own too.

## Before anything else

**Never write to `zotero.sqlite` directly.** Zotero holds it open with WAL journalling
and maintains sync version columns; hand-written rows corrupt the library or get
clobbered on the next sync. The sqlite file is for *reading* — and even then, copy it to
a scratch directory and query the copy.

All writes go through the Web API. See references/zotero-api.md.

### Locate the key

The API key lives in a curl config file, by convention `~/.config/zotero-api.conf`,
containing one line:

```
header = "Zotero-API-Key: <key>"
```

Use it as `curl --config ~/.config/zotero-api.conf`. A config file rather than `-H`
keeps the key out of `ps` output and out of the conversation transcript.

If the file is absent, ask the person to create it in *their own* terminal — not
through you, and not with the `!` prefix, either of which puts the key in the
transcript. They generate one at zotero.org/settings/keys with **write access to the
personal library**.

Get the numeric user ID from `/keys/current`, but **filter the response** — it echoes
the key back in plaintext:

```bash
curl -s --config ~/.config/zotero-api.conf https://api.zotero.org/keys/current \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["userID"], d["access"])'
```

If the key does get echoed, say so plainly and suggest rotating it.

## The facets the citation map reads

If the library is being tagged so the map can use it, these prefixes are not a
suggestion — they are what the code looks for:

| facet | what it answers | used by the map for |
|---|---|---|
| `subject:` | what the item is about | a banding facet, and vocabulary edges |
| `question:` | what problem it addresses | a banding facet, and vocabulary edges |
| `approach:` | what tradition or technique it uses | a banding facet, and vocabulary edges |
| any other prefix, e.g. `evidence:` | whatever it answers | **cluster labels only** |
| `role:` | the map's own output | read back as a judged input; excluded from the layout |

`role:` is written by the map, not by hand, with one exception: `role: contrarian` is a
human judgement the build deliberately lets win over its own rules. Never apply the
other `role:` values by hand — they are recomputed every run.

Two properties matter more than the exact terms. **Every tag should span at least two
items** across the whole library, or it is a note rather than a category. And items
should carry **more than one** value in a facet only when that is genuinely true: the
banding puts each source in the band of its *rarest* tag in the facet, so a generously
tagged item lands somewhere surprising.

## Read the vocabulary before inventing one

A library organised this way usually has a **standalone note in the library root**
recording its vocabulary. It is the authority.

Finding it takes a small search, because **notes carry no title field in the API**.
Zotero derives the title from the first line of the body, so you must do the same — see
references/zotero-api.md for the query.

If no such note exists, say so and offer to create one as part of the work. Read it
fully before tagging anything: it carries the facets, the definition of each term, the
conventions and the provenance of past decisions.

Conventions such a note typically encodes, which you must honour rather than re-derive:

- **Prefixed facets**, so the Zotero tag selector groups them. One tag is
  conventionally unprefixed — a to-do marker like `MISSING` — so it sorts to the top.
- **Spelling and punctuation** exactly as written, including British vs. American
  spelling and ampersands vs. "and". The map matches on the literal string.
- **Add a value rather than stretching one.** If an item does not fit, the facet is
  probably missing a term.
- **Some facets travel, most do not.** A facet describing *what kind of claim an item
  supports* is the same question in any literature and should be shared. Subject facets
  are per-collection: a vocabulary for governance theory means nothing in a
  machine-learning collection, and forcing one on both serves neither.

After any change, **update the note** — its counts, and a dated provenance paragraph
saying what you did and why. A vocabulary note whose numbers have drifted is worse than
none.

## Scope

If the person has not named papers or a collection, **ask before acting**. Offer the
collections by name with item counts. Do not default to the whole library.

When *applying an existing documented vocabulary*, act directly and report. When
*designing a new vocabulary* for a collection that has none, present the proposed terms
and the per-item assignment for approval first — the vocabulary is a long-lived
decision and the person's subject knowledge beats yours.

## Tagging

**Ground every tag in the item's own text.** Fetch abstracts from Crossref, then
OpenAlex, then Semantic Scholar; coverage is patchy and differs between them. When none
has one, tag from title and venue and **say which items those were**, both in your
report and in the note's provenance. Never quietly infer content.

Where the library holds the PDF, read it. `storage/<attachmentKey>/.zotero-ft-cache` is
the extracted plain text of a stored file, far cheaper than parsing the PDF.

**Replacing tags replaces the whole set.** Import translators leave catalogue and
subject-code noise — arXiv category codes, bilingual library headings, DataCite `FOS:`
strings. That noise is what you are clearing, and a PATCH with the new tag list removes
it in the same operation. Keep the originals in scratch so they are recoverable.

## MISSING — citations with no file

Mark an item whose attachments include no `imported_file` or `imported_url`. A
`linked_url` attachment is a bookmark, not a file, and still counts as missing. Do not
apply it to blog posts or recordings, where the linked source *is* the item.

When asked to fetch missing files, check open access first via Unpaywall. Two cautions
learned the hard way:

- **`bronze` is unreliable.** It means "looks free on the publisher's site, no licence
  stated" and is inferred. `gold` and `hybrid` carry real licences and hold up.
- **Publisher sites block automated downloads.** Major publishers return 403 or a login
  page regardless of user-agent, and repository mirrors often 401. Do not promise a
  fetch you cannot make — report the OA status, hand over the URLs, and let the
  person's browser or the Zotero connector do it, which works because it is their IP
  and their session.

## Filing root-level items

Items belonging to no collection are usually import accidents. File each into its
best-suited collection and tag it to that collection's vocabulary.

**Leave the vocabulary note itself unfiled** — it describes the whole library and
belongs in the root. Do not tag it either; tagging a vocabulary note with its own
vocabulary pollutes the counts it documents.

## Duplicates

**Same title is not the same work.** Compare every substantive field before concluding
anything. A reprint, an excerpt, a preprint and the published article all share a title
and are four different records with different pagination, venue and DOI — and the one
already filed is not necessarily the one worth keeping. When fields differ, read the
PDF's first page before deciding; an excerpt announces itself.

This matters doubly for the citation map, where a duplicate splits one work's inbound
edges across two nodes and makes both look peripheral.

The API has **no merge operation** — merging is a client-side function that sets a
`dc:replaces` relation. The equivalent you can do:

1. Compare substantive fields on both records; report any the filed copy lacks.
2. Re-parent attachments the canonical item does not already have.
3. Trash the redundant copy with `{"deleted": 1}` — never hard-delete. Trash is
   recoverable; a DELETE is not.

Say plainly that this is a re-parent-and-trash, and that Zotero's own Duplicate Items
view does a true merge if they want the relation recorded.

## Orphaned attachments

An attachment with no `parentItem` is orphaned. Identify what it is — the filename and
`.zotero-ft-cache` usually say — then either re-parent it to the right item or report
it. **Do not delete files on your own judgment.**

## Verify, and mean it

After writing, re-read from the API and check:

- every count stated in the vocabulary note against the live library
- no tag with a single holder
- no unprefixed tag other than the intended marker
- no untagged item inside a collection
- no item outside every collection except the note
- the trash contains what you expect and nothing else

This step catches real mistakes — stale counts, sections duplicated during a note
rewrite, an item missed. Run it every time, and report what it found rather than
asserting success.

When comparing note counts to live tags, remember the note stores HTML: unescape
`&amp;` before matching, or ampersand tags look like phantom mismatches.
