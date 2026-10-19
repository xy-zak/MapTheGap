---
name: zotero-library
description: >
  File and tidy a Zotero library through the Zotero Web API — collections, duplicates,
  orphaned attachments and missing files. Use when asked to file loose items into
  collections, find or merge duplicate records, fix orphaned attachments, flag or fetch
  citations with no PDF, or audit a library. Triggers: Zotero, zotero.sqlite, "my
  library", "file these papers", "duplicates in Zotero", "which papers am I missing the
  PDF for", orphaned attachment. API mechanics and failure modes live in
  references/zotero-api.md. Applying the tag vocabulary itself is the zotero-tag skill.
---

# Organising a Zotero library

A library is someone's research memory. Every write syncs to their account and every
device, so the standing bias is: **read widely, write narrowly, verify after.**

This skill ships with the MapTheGap repo, and covers everything about a library
*except* its tag vocabulary. **Tagging is the `zotero-tag` skill** — the facets, the
language, the per-facet cap and the merge procedure all live there. Use this one for
where items sit and which files they have.

## Before anything else

**Never write to `zotero.sqlite` directly.** Zotero holds it open with WAL journalling
and maintains sync version columns; hand-written rows corrupt the library or get
clobbered on the next sync. The sqlite file is for *reading* — and even then, copy it to
a scratch directory and query the copy.

All writes go through the Web API. See references/zotero-api.md.

### Locate the key

The API key lives in a curl config file, by convention `~/.config/zotero-api.conf`
(on Windows, `%USERPROFILE%\.config\zotero-api.conf`, which is the same `~` in Git
Bash), containing one line:

```
header = "Zotero-API-Key: <key>"
```

Use it as `curl --config ~/.config/zotero-api.conf`. A config file rather than `-H`
keeps the key out of `ps` output and out of the conversation transcript.

curl ships with macOS, Linux and Windows 10 and later, so these recipes work on all
three from a Bash shell, which is what Claude Code uses on Windows (Git Bash). In
Windows PowerShell, `curl` is an alias for `Invoke-WebRequest`; call `curl.exe`
explicitly there. Likewise `python3` is often `py` or `python` on Windows.

If the file is absent, ask the person to link a key through MapTheGap's setup page
(`python3 app.py`) or to create the file in *their own* terminal — not through you,
and not with the `!` prefix, either of which puts the key in the transcript. They
generate one at zotero.org/settings/keys with **write access to the personal
library**. The map alone only needs read access, so a key made for it may lack
write access; a 403 on a write means exactly that, and the fix is to edit the key at
zotero.org, not to retry.

Get the numeric user ID from `/keys/current`, but **filter the response** — it echoes
the key back in plaintext:

```bash
curl -s --config ~/.config/zotero-api.conf https://api.zotero.org/keys/current \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["userID"], d["access"])'
```

If the key does get echoed, say so plainly and suggest rotating it.

## Scope

If the person has not named papers or a collection, **ask before acting**. Offer the
collections by name with item counts. Do not default to the whole library.

Filing and tagging usually want doing together: an item moved into a collection should
carry that collection's vocabulary. Do the move here and hand the tagging to
`zotero-tag`, which owns the facets and the per-facet cap.

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

- no untagged item inside a collection
- no item outside every collection except the vocabulary note
- every attachment either parented or reported
- the trash contains what you expect and nothing else

This step catches real mistakes — an item missed, a re-parent that did not take. Run it
every time, and report what it found rather than asserting success.

Vocabulary checks — counts, single-holder values, the per-facet cap — belong to the
`zotero-tag` skill, which regenerates
`.claude/skills/zotero-tag/references/vocabulary.md` from the library and verifies
against that.
