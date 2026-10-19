#!/usr/bin/env python3
"""Record the library's live tag vocabulary as a document the zotero-tag skill reads.

Writes .claude/skills/zotero-tag/references/vocabulary.md: every facet value with its
holder count, each facet measured against the per-facet limit, the two-holder rule
checked, and merge candidates proposed for any facet that is over budget.

The point is drift. Counts stated from memory go stale within a pass or two, and a
term whose meaning nobody can recall gets re-invented under a second name. This file
is regenerated from the library rather than edited, so it cannot disagree with it.

Usage:  python3 vocab.py [--no-fetch]
        --no-fetch   use the recorded library pull under cache/zotero/; no network
"""

import argparse
import collections
import difflib
import html
import os
import re
import time

import build   # the Zotero client, pagination and offline path all live there

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, ".claude", "skills", "zotero-tag", "references", "vocabulary.md")

# The map reads the first three for banding and vocabulary edges; the fourth can only
# name a cluster. All four are capped, because the cap is about human legibility of the
# vocabulary rather than about what the layout does with it.
FACETS = ("subject", "question", "approach", "evidence")
LIMIT = 15

# role: is the map's output, recomputed every build, so it is reported but never capped
# and never a merge candidate.
REPORTED_ONLY = ("role",)

RETIRED_BEGIN = "<!-- RETIRED:BEGIN - hand-maintained, preserved across regenerations -->"
RETIRED_END = "<!-- RETIRED:END -->"

STOPWORDS = {"and", "of", "the", "a", "in", "to", "for", "on", "with"}


def words(value):
    return {w for w in re.split(r"[^a-z]+", value.lower()) if w and w not in STOPWORDS}


def merge_candidates(holders):
    """Pairs worth considering for a merge, most promising first.

    Two signals, and the second is a veto rather than a trigger.

    LEXICAL similarity catches the shape a redundant pair actually has: similar
    wording, one term arguably subsuming the other.

    ITEM OVERLAP - the share of the smaller term's items that also carry the larger -
    counts AGAINST a merge. Two values that are applied to the same items are
    describing different aspects of those items, so collapsing them destroys a real
    distinction. Values that are genuine alternatives get used instead of one another,
    so their holder sets barely intersect.
    """
    out = []
    names = sorted(holders)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = holders[a], holders[b]
            shared = words(a) & words(b)
            lex = difflib.SequenceMatcher(None, a, b).ratio()
            overlap = len(A & B) / min(len(A), len(B))
            if not (shared or lex >= 0.72):
                continue
            # disjoint holders and similar wording is the strongest case
            score = lex * (1 - overlap)
            out.append({"a": a, "b": b, "na": len(A), "nb": len(B), "lex": lex,
                        "overlap": overlap, "shared": " ".join(sorted(shared)),
                        "score": score})
    return sorted(out, key=lambda c: -c["score"])


def glossed(items):
    """Facet values the library's own vocabulary note glosses.

    A gloss is a human having already drawn the line between two neighbouring terms,
    which is evidence against merging them. Best effort: if there is no vocabulary
    note, or its shape has changed, this simply returns nothing.
    """
    try:
        note = next(i["data"]["note"] for i in items
                    if i["data"]["itemType"] == "note"
                    and not i["data"].get("parentItem")
                    and not i["data"].get("collections"))
    except (StopIteration, KeyError):
        return set()
    text = html.unescape(re.sub(r"<[^>]+>", "\n", note))
    return {m.group(1).strip() for m in
            re.finditer(r"^\s*([a-z][a-zA-Z &/\-]*?)\s+—\s+\d+\s*·", text, re.M)}


def main():
    ap = argparse.ArgumentParser(
        description="Record the library's live tag vocabulary for the zotero-tag skill.")
    ap.add_argument("--no-fetch", action="store_true",
                    help="use the recorded library pull under cache/zotero/; no network")
    args = ap.parse_args()
    build.stdout_never_fails()

    os.makedirs(build.CACHE_ZOTERO, exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fetch = build.Fetcher.connect(args.no_fetch)
    raw = fetch.zotero_all("items", limit=100, itemType="-attachment")
    items = [i for i in raw
             if i["data"]["itemType"] not in ("note", "attachment")
             and not i["data"].get("deleted")]

    holders = collections.defaultdict(lambda: collections.defaultdict(set))
    unprefixed = collections.defaultdict(set)
    for i in items:
        key = i["data"]["key"]
        for t in (x["tag"] for x in i["data"].get("tags", [])):
            if ": " in t:
                facet, value = t.split(": ", 1)
                holders[facet][value].add(key)
            else:
                unprefixed[t].add(key)

    gl = glossed(raw)
    L = []
    w = L.append
    w("# Tag vocabulary, as recorded in the library")
    w("")
    w("Generated by `vocab.py` on %s from %d tagged items. "
      % (time.strftime("%Y-%m-%d"), len(items)))
    w("**Do not edit the generated sections** - regenerate with `python3 vocab.py`.")
    w("Only the retired-terms block at the end is hand-maintained, and it is preserved.")
    w("")
    w("Counts are holder counts across the whole library. A value glossed in the "
      "library's own vocabulary note is marked `*`, meaning someone has already drawn "
      "the line between it and a neighbour - treat that as evidence against merging it.")
    w("")

    over = []
    for facet in FACETS:
        vals = holders.get(facet, {})
        n = len(vals)
        status = "**OVER the limit of %d by %d**" % (LIMIT, n - LIMIT) if n > LIMIT \
            else "%d of %d used" % (n, LIMIT)
        if n > LIMIT:
            over.append(facet)
        w("## `%s:` - %s" % (facet, status))
        w("")
        w("| value | items | glossed |")
        w("|---|---:|:---:|")
        for v, ks in sorted(vals.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            w("| %s | %d | %s |" % (v, len(ks), "*" if v in gl else ""))
        w("")
        singles = sorted(v for v, ks in vals.items() if len(ks) == 1)
        if singles:
            w("Single-holder values, which are notes rather than categories and should "
              "be merged or dropped first: %s" % ", ".join("`%s`" % s for s in singles))
            w("")

    for facet in REPORTED_ONLY:
        vals = holders.get(facet, {})
        if not vals:
            continue
        w("## `%s:` - reported only, not capped" % facet)
        w("")
        w("Recomputed from the citation graph on every build, so hand edits are "
          "overwritten. `contrarian` is the exception: judged and sticky.")
        w("")
        w("| value | items |")
        w("|---|---:|")
        for v, ks in sorted(vals.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            w("| %s | %d |" % (v, len(ks)))
        w("")

    if unprefixed:
        w("## Unprefixed tags")
        w("")
        for t, ks in sorted(unprefixed.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            w("- `%s` - %d items" % (t, len(ks)))
        w("")

    w("## Merge candidates")
    w("")
    if not over:
        w("Every facet is within its limit, so **no merge is needed**. Candidates are "
          "listed anyway, because a pair that scores high here is also a pair a reader "
          "may confuse.")
        w("")
    else:
        w("`%s` %s over the limit. Merge from the top of the relevant list, and see the "
          "zotero-tag skill for the procedure - a merge rewrites tags across many items "
          "and needs approval before any write."
          % ("` and `".join(over), "is" if len(over) == 1 else "are"))
        w("")
    w("`lex` is wording similarity. `overlap` is the share of the smaller value's items "
      "that also carry the larger one, and it counts **against** a merge: values applied "
      "to the same items describe different aspects of them, so collapsing the pair "
      "destroys a distinction. Genuine alternatives are used instead of one another and "
      "so barely intersect.")
    w("")
    for facet in over:
        # When no lexical pair is safe to merge, the remedy is to retire the narrowest
        # term instead: re-tag its holders under a broader existing value. The
        # lowest-count values are where the least meaning is lost, and a term with a
        # handful of holders is rarely carrying its own weight in a capped facet.
        vals = holders.get(facet, {})
        need = len(vals) - LIMIT
        narrow = sorted(vals.items(), key=lambda kv: (len(kv[1]), kv[0]))[:max(3, need + 2)]
        w("### `%s:` retirement candidates" % facet)
        w("")
        w("%d value%s must go. If no merge above is safe, retire from here instead - "
          "re-tag these holders under a broader value that already exists, and record "
          "the move in the retired-terms block."
          % (need, "" if need == 1 else "s"))
        w("")
        w("| value | items | glossed |")
        w("|---|---:|:---:|")
        for v, ks in narrow:
            w("| `%s` | %d | %s |" % (v, len(ks), "*" if v in gl else ""))
        w("")

    for facet in FACETS:
        cands = merge_candidates(holders.get(facet, {}))[:6]
        if not cands:
            continue
        w("### `%s:`%s" % (facet, "  - over the limit" if facet in over else ""))
        w("")
        w("| | | lex | overlap | shared wording | verdict |")
        w("|---|---|---:|---:|---|---|")
        for c in cands:
            # A gloss on EITHER value is the signal, not on both: a gloss exists
            # precisely to separate a term from the neighbour it would be confused
            # with, so one is enough to show the distinction was drawn on purpose.
            if c["overlap"] >= 0.5:
                verdict = "do not merge - complementary"
            elif c["a"] in gl or c["b"] in gl:
                verdict = "deliberate - read the gloss first"
            elif c["overlap"] == 0 and c["lex"] >= 0.5:
                verdict = "strongest candidate"
            else:
                verdict = "consider"
            w("| `%s` (%d) | `%s` (%d) | %.2f | %.2f | %s | %s |"
              % (c["a"], c["na"], c["b"], c["nb"], c["lex"], c["overlap"],
                 c["shared"] or "-", verdict))
        w("")

    # Preserve the hand-maintained retired-terms block across regenerations.
    kept = None
    if os.path.exists(OUT):
        prev = open(OUT, encoding="utf-8").read()
        m = re.search(re.escape(RETIRED_BEGIN) + r"(.*?)" + re.escape(RETIRED_END),
                      prev, re.S)
        if m:
            kept = m.group(1)
    w("## Retired terms")
    w("")
    w(RETIRED_BEGIN)
    if kept is not None:
        w(kept.strip("\n"))
    else:
        w("")
        w("Every merge or rename goes here, so a distinction that was deliberately "
          "collapsed is not re-invented under a new name three months later. One line "
          "each: `retired value` -> `value it became`, the date, and why in a clause.")
        w("")
        w("_Nothing retired yet._")
        w("")
    w(RETIRED_END)
    w("")

    text = "\n".join(L)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:   # LF on Windows too
        fh.write(text)
    rel = os.path.relpath(OUT, HERE)
    print("wrote %s - %d items, %d facets"
          % (rel, len(items), len([f for f in FACETS if holders.get(f)])))
    for facet in FACETS:
        n = len(holders.get(facet, {}))
        print("   %-10s %2d/%d %s" % (facet, n, LIMIT, "OVER" if n > LIMIT else ""))
    if kept is not None:
        print("   retired-terms block preserved (%d chars)" % len(kept.strip()))


if __name__ == "__main__":
    main()
