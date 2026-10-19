# Zotero Web API recipes

Base URL: `https://api.zotero.org/users/<userID>`
Every call: `curl -s --config ~/.config/zotero-api.conf ...`

The `/keys/current` response **echoes the API key back in plaintext**. Never print it;
pipe it through a filter that extracts only what you need.

## Reading

```bash
# collections, with item counts and parent links
GET /collections?limit=50
#   data.key, data.name, data.parentCollection (false if top level), meta.numItems

# top-level items in a collection (excludes child notes/attachments)
GET /collections/<collKey>/items/top?limit=100&sort=date&direction=asc

# everything except attachments, whole library
GET /items?limit=100&itemType=-attachment

# all attachments — map data.parentItem to find children and orphans
GET /items?itemType=attachment&limit=100

# one item
GET /items/<itemKey>

# items carrying a tag
GET /collections/<collKey>/items/top?tag=MISSING

# the trash
GET /items/trash?limit=50
```

Response headers worth reading: **`Total-Results`** for counts without parsing, and
`Last-Modified-Version` for the library version to pin writes against.

### Pagination is not optional

`limit` caps at **100**. A library of 101 non-attachment items returns 100 and says
nothing about it, so any unpaginated read silently truncates. Loop `start` until a page
comes back shorter than `limit`, and check the row count against `Total-Results`.

**Do not add `sort=` to make a paginated read stable** unless you mean to change the
order. The server's default order is what downstream code sees, and imposing a sort
reorders anything derived from arrival order.

Trashed items are **excluded** from normal item listings. An item vanishing from
`/items` after a trash operation is expected, not a deletion.

## Writing

Always PATCH a single item, pinned to the version you read:

```bash
curl -s --config ~/.config/zotero-api.conf -X PATCH \
  -H "If-Unmodified-Since-Version: <item version>" \
  -H "Content-Type: application/json" \
  -d '{"tags":[{"tag":"approach: <term>"}]}' \
  https://api.zotero.org/users/<uid>/items/<itemKey>
```

Success is **HTTP 204** with an empty body. `412` means the item changed since you read
it — re-read and redo that one write rather than forcing.

PATCH touches only the fields in the body. Prefer it over the multi-object `POST /items`
batch endpoint for updates: the batch endpoint's partial-update semantics are easy to
get wrong, and a full object sent by mistake overwrites every field you omitted. Thirty
sequential PATCHes are slower and completely safe.

Common payloads:

```json
{"tags": [{"tag": "a"}, {"tag": "b"}]}    // replaces the whole tag set
{"collections": ["<collKey>"]}             // replaces collection membership
{"deleted": 1}                             // move to trash (reversible)
{"parentItem": "<itemKey>"}                // re-parent an attachment
{"note": "<h1>...</h1>"}                   // note body, HTML
```

## Notes have no title

A note item has **no `title` field** in either `data` or `meta`. Zotero shows the first
line of the body as the title, so to identify notes you must fetch `data.note` and
parse it. Standalone notes are those with no `parentItem` and an empty `collections`
array; everything else is a child note attached to an item.

Finding the standalone, unfiled notes — which is where a vocabulary note lives:

```bash
curl -s --config ~/.config/zotero-api.conf \
  "https://api.zotero.org/users/<uid>/items?itemType=note&limit=50" \
  | python3 -c 'import sys,json,re
for i in json.load(sys.stdin):
    d=i["data"]
    if d.get("parentItem") or d.get("collections"): continue
    first=re.sub("<[^>]+>","",d["note"]).strip().split("\n")[0]
    print(d["key"], "|", first[:70])'
```

## Creating a standalone note

```bash
curl -s --config ~/.config/zotero-api.conf -X POST \
  -H "Content-Type: application/json" \
  -d '[{"itemType":"note","note":"<h1>Title</h1><p>…</p>","tags":[],"collections":[]}]' \
  https://api.zotero.org/users/<uid>/items
```

Returns `{"successful": {"0": {...}}}` — the new key is in there. An empty `collections`
puts it in the library root. The note's **first line becomes its title**, so open with
an `<h1>`.

Zotero notes accept a limited HTML subset: headings, `<p>`, `<ul>/<li>`, `<strong>`,
`<em>`, `<blockquote>`. Escape `&` as `&amp;`, and prefer named entities for accented
characters a shell heredoc might mangle.

## Editing a long note

Read it, apply exact string replacements, PATCH it back. Assert each replacement matched
exactly once before sending:

```python
for old, new in edits:
    assert n.count(old) == 1, "no unique match: %r" % old[:60]
    n = n.replace(old, new)
```

This catches the common failure where a note rewrite leaves **two copies of a section** —
one current, one stale — which reads as correct until someone checks the numbers.

## Attachment types

| linkMode | is there a file? |
|---|---|
| `imported_file` | yes, stored in `storage/<key>/` |
| `imported_url` | yes, downloaded from a URL |
| `linked_file` | yes, but outside the Zotero directory |
| `linked_url` | **no** — a bookmark only |

## Local reads

```bash
cp ~/Zotero/zotero.sqlite <scratch>/z.sqlite      # never query the live file
python3 -c "import sqlite3; print(sqlite3.connect('<scratch>/z.sqlite').execute('...').fetchall())"
```

`~/Zotero` is the default data directory on macOS, Windows and Linux alike (Zotero's
*Settings → Advanced → Files and Folders* shows the real one). Query the copy through
Python's built-in `sqlite3` module; the `sqlite3` command-line tool is not installed on
Windows.

Useful tables: `items`, `itemData`/`itemDataValues`/`fields`, `itemCreators`/`creators`,
`collections`/`collectionItems`, `itemAttachments`, `itemNotes`, `itemTags`/`tags`,
`deletedItems`.

Extracted PDF text, no parsing needed:
`~/Zotero/storage/<attachmentKey>/.zotero-ft-cache`

## Metadata and open access

```bash
# abstract + full citation
https://api.crossref.org/works/<doi>?mailto=<email>
https://api.openalex.org/works/doi:<urlencoded doi>?mailto=<email>
https://api.semanticscholar.org/graph/v1/paper/DOI:<doi>?fields=title,abstract,openAccessPdf

# open-access status
https://api.unpaywall.org/v2/<doi>?email=<email>
```

OpenAlex returns abstracts as `abstract_inverted_index` — rebuild by sorting positions.
Crossref abstracts are JATS-tagged HTML; strip tags and unescape.

Coverage is patchy and differs between them. Try all three before concluding no abstract
exists, and record which items ended up tagged from title alone.

**Both OpenAlex and Semantic Scholar run a polite pool**: calls carrying a contact
address get faster, more reliable service. Semantic Scholar unauthenticated allows
roughly one request per five seconds and returns 429 freely — an empty response is far
more often a rate limit than a genuine absence, so check the status code before
concluding anything.
