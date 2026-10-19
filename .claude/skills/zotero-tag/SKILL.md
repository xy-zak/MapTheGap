---
name: zotero-tag
description: >
  Apply, extend and consolidate the prefixed tag vocabulary of a Zotero library — the
  subject/question/approach/evidence facets the citation map reads. Use when asked to
  tag papers, design or extend a tag vocabulary, work out which tag an item should
  carry, reduce or tidy a tag list that has grown too long, merge tags that mean nearly
  the same thing, or record the vocabulary so it stops drifting. Triggers: "tag these
  papers", "how should I tag this", tag vocabulary, too many tags, merge tags,
  consolidate tags, facets, "what tags do I have". The live vocabulary is recorded in
  references/vocabulary.md; filing, duplicates and API mechanics are in the
  zotero-library skill.
---

# How to tag

Four facets, one vocabulary for the whole library. Prefixes keep them grouped in
Zotero's tag selector. **Ask the four questions in order and stop when you run out of
answers** — not every item earns every facet.

| # | facet | the question it answers | how many per item |
|---|---|---|---|
| 1 | `subject:` | what is it *about*? the real-world thing under study | one or two |
| 2 | `question:` | what *problem* does it address? | two or three |
| 3 | `approach:` | what *tradition or technique* does it use? | one or two |
| 4 | `evidence:` | what kind of *claim* can it support? | usually exactly one |

A median of six prefixed tags per item is a healthy target. Fewer than three means the
item has not really been read; more than nine usually means a facet is being used as a
list of everything the paper mentions.

**`subject:` needs an escape hatch.** Reserve one value — `cross-cutting` is the
conventional name — for items that span several subjects by design, or that are purely
about method. Without it, methodological work gets filed under whichever domain its
worked example happened to use.

**`approach:` is the machinery the authors actually work with, not everything they
cite.** This is the facet most often over-applied, because a literature review touches
many traditions while working in one.

**`evidence:` is about the argument, not the format.** The Zotero item type already
records whether something is a book, a preprint or a recording. This facet is the most
portable of the four — it asks the same question of any literature — so it is the one
worth carrying between libraries:

> `conceptual` · `case study` · `comparative cases` · `systematic review` ·
> `formal model` · `benchmark / experiments` · `quasi-experimental` ·
> `network analysis` · `dataset / product` · `popular / secondary`

That is a starting set, not a fixed list. It leans towards empirical research; a
humanities or theory-heavy library may need values like `close reading`, `archival` or
`interpretive`, and can drop the ones nothing in it uses. Change it deliberately, once,
and record the change in the vocabulary note.

`subject:`, `question:` and `approach:` are the opposite: they are specific to a
literature, and a vocabulary built for one field means nothing in another. Build them
from the items in front of you, not from a template.

## Two tags the vocabulary does not own

- **`role:`** is written by the citation map, recomputed from the graph on every build,
  so hand edits are overwritten. The single exception is `role: contrarian`, which is
  judged and sticky — a hand-set value always wins. Use it for an item that argues
  *against* the foundational position, never for one that merely notes a gap.
- **One unprefixed marker**, conventionally `MISSING`, for a citation with no file
  attached. Deliberately unprefixed so it sorts to the top of the tag selector and
  reads as a to-do. A link-only attachment still counts as missing. Not used for blog
  posts or recordings, where the link *is* the source.

## Read the recorded vocabulary first

**references/vocabulary.md** is generated from the live library by `vocab.py` and is the
authority on what exists right now. It is per-library and gitignored, so on a fresh
clone it does not exist yet: run `vocab.py` before anything else: every facet value, its holder count, which values
carry a gloss, and how close each facet is to its limit.

```bash
python3 vocab.py              # refresh from the library  (Windows: py vocab.py)
python3 vocab.py --no-fetch    # from the recorded pull, offline
```

**Read it before proposing a single tag, and regenerate it after any write.** It exists
because stated counts go stale within a pass or two, and a term whose meaning nobody
can recall gets re-invented under a second name. Regenerating is cheap; guessing is
what produces two tags for one idea.

Many libraries also keep a **standalone note in the library root** — conventionally
titled "How to tag" — holding the facet definitions, a gloss on each easily-confused
value, and a dated provenance log. Where it exists it is the human authority and
`vocabulary.md` is the machine-checked snapshot of the same thing; they must agree.
Update the note's provenance after every pass, and never hand-increment its counts —
recompute them.

## The rules that matter

**Ground every tag in the item's own text.** Fetch abstracts from Crossref, then
OpenAlex, then Semantic Scholar; coverage is patchy and differs between them. Where the
library holds the PDF, read it —
`~/Zotero/storage/<attachmentKey>/.zotero-ft-cache` is the extracted plain text, far
cheaper than parsing (`~/Zotero` is the default data directory; Zotero's *Settings →
Advanced → Files and Folders* shows the real one). When no abstract exists anywhere, tag from title and venue and
**say which items those were**, in your report and in the note's provenance. Name the
single least certain call you made. Never quietly infer content.

**Every value spans at least two items**, counted across the whole library, not within
one collection. A term with a single holder is a note, not a category — merge it or
drop it. `vocabulary.md` lists these first.

**Add a value rather than stretching one.** If an item does not fit, the facet is
probably missing a term — subject to the cap below.

**Follow the existing spelling exactly**, including British vs. American forms and
`&` vs. "and". The map matches on the literal string, so a value that reads identically
to a human but differs by one character is a different tag to the code.

**Replacing tags replaces the whole set.** A PATCH with the new list wipes
import-translator noise — arXiv category codes, bilingual library headings, DataCite
`FOS:` strings — in the same operation. Keep the originals in scratch so they are
recoverable.

## Language

Measured conventions that keep a vocabulary readable in a tag selector:

| | |
|---|---|
| case | lowercase, except acronyms that are always capitalised |
| length | short noun phrases, two words typical, four the practical maximum |
| conjunction | `&`, never the word "and" |
| alternatives | ` / ` for a genuine pairing or alternative, e.g. `benchmark / experiments` — not for a hierarchy |
| number | plural where the thing is plural; singular for a field or technique |
| verbs | none. A tag is a noun phrase, never a sentence |
| glosses | live in the vocabulary note, never in the tag itself |

Add a gloss to any value that a reader could confuse with its neighbour. A gloss is the
cheapest way to stop the same distinction being re-drawn under a third name, and
`vocab.py` treats a glossed value as evidence that a distinction was deliberate.

## The cap: at most 15 values per facet

`subject:`, `question:`, `approach:` and `evidence:` are each capped at **15 distinct
values**. Beyond that a facet stops being a facet: nobody can hold the list in mind, so
the same idea gets tagged two ways and the selector becomes a search problem.

`vocabulary.md` reports each facet against the cap and flags any that is over.

When a facet is over, **consolidate — do not simply stop adding.** Refusing new values
in a full facet is worse than merging, because it forces items into terms that do not
fit and the facet quietly stops meaning anything.

### Choosing what to merge

`vocab.py` proposes candidates on two signals. Understand what each one means, because
the second is counter-intuitive:

- **`lex` — wording similarity.** Catches the shape a redundant pair actually has:
  similar wording, one term arguably subsuming the other.
- **`overlap` — the share of the smaller value's items that also carry the larger.**
  This counts **against** a merge. Two values applied to the *same* items are
  describing different aspects of those items, so collapsing them destroys a real
  distinction. Genuine alternatives get used *instead of* one another, so their holder
  sets barely intersect. **High overlap means complementary, not redundant.**

So the strongest candidate is **similar wording with near-zero overlap**: two terms
people reach for interchangeably, which is exactly the confusion the cap exists to
prevent.

Three things that should stop a merge:

1. **Either value is glossed.** A gloss exists precisely to separate a term from the
   neighbour it would be confused with, so one gloss is enough to show somebody already
   made this call deliberately. Read it before overriding it.
2. **The pair is complementary** — high overlap, per above.
3. **One of them names a cluster on the map.** Check before merging; collapsing it
   changes what the map calls that community.

### When no merge is safe

Common, and the vocabulary document says so explicitly. The remedy is then to **retire
the narrowest term**: re-tag its handful of holders under a broader value that already
exists. The lowest-count values are where the least meaning is lost, and a two-holder
term is rarely carrying its weight in a capped facet. `vocabulary.md` lists retirement
candidates for any over-budget facet, with glosses marked.

Accepting an overage is a legitimate third option, but only with the reason recorded in
the note's provenance. An unexplained overage becomes permanent.

### Carrying out a merge

A merge rewrites tags across many items, so:

1. **Propose before writing.** List each pair or retirement with its counts, the items
   affected, the surviving value, and what is lost. Get explicit approval. This is a
   long-lived vocabulary decision and the person's subject knowledge beats yours.
2. **Merge into the broader existing term** where one subsumes the other. Where neither
   does, a new parent term is right and *both* children retire — that still reduces the
   count by one.
3. **PATCH one item at a time**, pinned to the version you read. Remember that a tag
   PATCH replaces the item's whole tag set, so send the full intended list.
4. **Record it in the retired-terms block** of `vocabulary.md`: `retired value` →
   `value it became`, the date, and why in a clause. `vocab.py` preserves that block
   across regenerations — it is the only hand-maintained part of the file, and it is
   what stops a collapsed distinction being re-invented next month.
5. **Regenerate `vocabulary.md`** and update the note's provenance with what moved and
   why.

### What a merge changes downstream

Merging is not cosmetic. If the library feeds the citation map:

- **Vocabulary edges change.** Two values become one shared tag, so pairs that shared
  nothing may now share a term and cross the overlap threshold, gaining an edge — and
  every vocabulary edge pulls equally, so each one gained moves the layout and can
  move the communities.
- **Band membership changes.** Each source sits in the band of its **rarest** value in
  the banding facet, so merging two rare values into one commoner one can move items
  into a different band entirely — including items that carried neither.
- **A band disappears.** One fewer value in a banding facet is one fewer swimlane.
- **Cluster labels may change**, since labels are picked by distinctiveness and a
  merged term is commoner, so it scores as less distinctive.

Rebuild the map after a merge and report the diff, rather than letting the next rebuild
surprise someone.

## Verify, and mean it

After writing, regenerate `vocabulary.md` and check:

- every facet within its cap
- no value with a single holder
- no unprefixed tag other than the intended marker
- no untagged item inside a collection
- every count in the vocabulary note matching the regenerated document
- the retired-terms block containing everything this pass collapsed

Report what the check found rather than asserting success. When comparing note counts
to live tags, remember the note stores HTML: unescape `&amp;` first, or ampersand
values look like phantom mismatches.
