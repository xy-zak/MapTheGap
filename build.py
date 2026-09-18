#!/usr/bin/env python3
"""Build a citation map of a Zotero library.

Pipeline: pull -> resolve identity -> fetch references -> build edges -> classify -> emit.

Computed values (degree, year, citation counts) are recomputed every run and never
stored, so they cannot drift. Only judged facts persist: `role: contrarian` tags in
Zotero, and the identity fixes in aliases.json.

Usage:  python3 build.py [--no-fetch]
        --no-fetch   work from the recorded library and cached API responses only;
                     makes no network calls at all. Needs one prior ordinary run to
                     have recorded the Zotero pull under cache/zotero/.
"""

import argparse
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_OA = os.path.join(HERE, "cache", "openalex")
CACHE_S2 = os.path.join(HERE, "cache", "s2")
CACHE_ZOTERO = os.path.join(HERE, "cache", "zotero")
OUT = os.path.join(HERE, "out")
CURL_CONF = os.path.expanduser("~/.config/zotero-api.conf")
# OpenAlex and Semantic Scholar both run a "polite pool": calls carrying a contact
# address get faster and more reliable service. Set ZOTERO_MAP_MAILTO to opt in.
# Leaving it unset is supported - the address is simply omitted and the calls fall
# back to the common pool - so no personal address is baked into this file.
MAILTO = os.environ.get("ZOTERO_MAP_MAILTO", "").strip()
USER_AGENT = f"zotero-map ({MAILTO})" if MAILTO else "zotero-map"


# ---------------------------------------------------------------- Zotero

def _curl(args: list, what: str, show_stderr: bool = True):
    """Run curl and return the parsed body, or fail with a message that names the cause.

    Without the exit-status check a missing or unreadable curl config surfaces as
    `Expecting value: line 1 column 1` from inside a JSON parser, which points
    nowhere near the actual problem.
    """
    r = subprocess.run(["curl", "-s"] + args, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        tail = r.stderr.strip()[:200]
        detail = f" - {tail}" if show_stderr and tail else ""
        raise SystemExit(f"curl failed fetching {what} (exit {r.returncode}). Check that "
                         f"{CURL_CONF} exists, is readable, and carries a "
                         f"Zotero-API-Key header.{detail}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        # deliberately does not echo the body - see Fetcher.connect below
        raise SystemExit(f"Zotero returned a non-JSON body for {what}, which usually "
                         f"means the key in {CURL_CONF} was rejected.")


# ---------------------------------------------------------------- external APIs

def _get_json(url: str, timeout: int = 40):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def _cache_read(path: str, what: str):
    """A cached response, or None when there is nothing usable on disk.

    A killed build can leave a half-written file behind, and a cold build is slow
    enough - Semantic Scholar alone sleeps 5s per fetch - that interrupting one is
    routine. Before this, a single truncated file made every later run crash in
    json.load with a manual `rm` as the only recovery. The warning is the point: a
    silent miss would conflate "corrupt" with "cites nothing", which is exactly the
    conflation the failure reporting below exists to prevent.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        print(f"WARNING: unreadable cache entry for {what} "
              f"({os.path.basename(path)}) - refetching: {e}")
        return None


def _need_recorded(cache: str) -> SystemExit:
    """The error for --no-fetch when nothing has been recorded yet."""
    return SystemExit(
        f"--no-fetch has nothing recorded at {cache}. Run once without --no-fetch "
        "to record the library, then --no-fetch works offline.")


def _cache_write(path: str, obj) -> None:
    """Write through a temp file, so an interrupted run cannot leave a partial entry.

    The .tmp name cannot collide with a lookup: every cache path is a sanitised
    identifier plus ".json".
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def _zotero_cache_name(path, params):
    """The cache filename for a Zotero endpoint plus the query that selected the rows.

    The query has to be part of the name. Keying on the path alone meant
    items?itemType=-attachment and items?itemType=attachment were the same file, so
    whichever call ran last silently overwrote the other and the next reader got a
    recorded pull of the wrong half of the library - with nothing in the file saying
    which half it held. Nothing in this repo makes both calls, but a caller working
    against the library alongside a build does, and the failure is silent.

    `limit` is excluded deliberately: it is a pagination detail, and every page size
    returns the same rows.

    The result stays a sanitised identifier plus ".json", which is what lets
    _cache_write use a ".tmp" suffix without risking a collision with a lookup.
    """
    slug = ",".join(f"{k}={params[k]}" for k in sorted(params))
    return re.sub(r"[^A-Za-z0-9.,=~_-]", "_", f"{path}~{slug}" if slug else path) + ".json"


class Fetcher:
    """Every outbound call, plus the per-run state they accumulate.

    Three things were module globals and are now here: the Zotero user id, which is
    a network result rather than configuration and so could never be a constant, and
    the two failure lists. They stay LISTS - keying them by DOI would silently
    dedupe a DOI that fails twice, and the count is part of the build summary.

    The genuinely constant configuration (cache paths, CURL_CONF, MAILTO,
    USER_AGENT) stays at module scope, where it reads as configuration.
    """

    def __init__(self, user_id, no_fetch):
        self.user_id = user_id
        self.no_fetch = no_fetch
        # Reference-list fetches that failed outright, as (doi, error). Kept so the run
        # can say how much of the graph is missing rather than reporting only what it
        # found: a failed fetch and a paper that genuinely cites nothing are
        # indistinguishable in the edge list, and silently conflating them makes
        # isolated nodes look like findings.
        self.oa_failures = []
        self.s2_failures = []

    # ------------------------------------------------------------ Zotero

    @classmethod
    def connect(cls, no_fetch):
        """Resolve the library's user id, from the recorded copy when offline.

        Only the integer id is ever written to disk. The /keys/current response
        echoes the API key back in plaintext, so it is never cached, never printed,
        and curl's stderr for it is never shown.
        """
        cache = os.path.join(CACHE_ZOTERO, "user_id.json")
        if no_fetch:
            hit = _cache_read(cache, "the Zotero user id")
            if hit is None:
                raise _need_recorded(cache)
            return cls(hit, no_fetch)
        user_id = _curl(["-m", "30", "--config", CURL_CONF,
                         "https://api.zotero.org/keys/current"],
                        "the API key owner", show_stderr=False)["userID"]
        _cache_write(cache, user_id)
        return cls(user_id, no_fetch)

    def zotero(self, path, **params):
        url = f"https://api.zotero.org/users/{self.user_id}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return _curl(["-m", "60", "--config", CURL_CONF, url], path)

    def zotero_all(self, path, **params):
        """Every row of a Zotero endpoint, following pagination, and recorded to cache.

        The un-paginated `limit=100` this replaces was TWO items from silently
        truncating the library: the items query reports Total-Results 98 today, and at
        101 the overflow would simply have been dropped, with `pulled %d items` quietly
        reporting the smaller number.

        No `sort=` is sent, deliberately. The server's default order sets the order in
        which the OpenAlex and Semantic Scholar calls below are made, and so the order
        of the failure lines in the build summary; imposing a sort here would reorder
        output that has nothing to do with sorting.

        The response is recorded so that --no-fetch can honour its promise. Before
        this it still made three live calls, so the flag could not be used offline at
        all despite saying "never hit the network".

        The cache file is named for the path AND the query - see
        _zotero_cache_name, which exists because naming it for the path alone let two
        different queries share one file.
        """
        limit = params.pop("limit", 100)
        cache = os.path.join(CACHE_ZOTERO, _zotero_cache_name(path, params))
        if self.no_fetch:
            hit = _cache_read(cache, "the recorded Zotero " + path)
            if hit is None:
                raise _need_recorded(cache)
            return hit
        rows, start = [], 0
        while True:
            page = self.zotero(path, start=start, limit=limit, **params)
            rows += page
            if len(page) < limit:
                break
            start += limit
        _cache_write(cache, rows)
        return rows

    # ------------------------------------------------------- external APIs

    def openalex_by_doi(self, doi):
        """Resolve a DOI to an OpenAlex work.

        Only successful responses are cached, for the same reason as s2_refs: a cached
        error is indistinguishable from a cached negative on the next run, so one bad
        afternoon becomes a permanent hole in the graph. The cost of not caching is a
        re-request per failing DOI per build at 0.12s, which is nothing.

        A 404 here is usually real rather than transient - the Journal of Law and
        Economics DOI for Coase 1960 has no OpenAlex record at all - so the point is not
        that these will succeed next time. It is that the error text reaches the build
        summary instead of being silently frozen into the cache, where a 404 that means
        "not indexed" and a 429 that means "ask again" look identical."""
        f = os.path.join(CACHE_OA, re.sub(r"[^A-Za-z0-9._-]", "_", doi) + ".json")
        hit = _cache_read(f, doi)
        if hit is not None:
            return hit
        if self.no_fetch:
            return {"error": "not cached, --no-fetch"}
        url = "https://api.openalex.org/works/doi:" + urllib.parse.quote(doi, safe="")
        if MAILTO:
            url += "?mailto=" + urllib.parse.quote(MAILTO, safe="")
        try:
            w = _get_json(url)
        except Exception as e:
            w = {"error": str(e)[:80]}
        if "error" in w:
            self.oa_failures.append((doi, w["error"]))
        else:
            _cache_write(f, w)
        time.sleep(0.12)
        return w


    def s2_refs(self, doi):
        """Semantic Scholar fallback. Covers preprints OpenAlex does not index.
        Unauthenticated and heavily throttled, so back off on 429.

        Only successful responses are cached. Caching the error too - which this did
        until a 429 storm left eight papers permanently reference-less - turns a
        transient rate-limit into a permanent hole, because every later run is a cache
        hit on the failure and never retries.

        One attempt, not a backoff ladder. The ladder existed because a failure was
        cached forever, so each paper got exactly one chance and it was worth spending
        a minute on it. Now that failures are not cached the next run retries anyway,
        and these 429s are sustained rather than per-request, so re-asking within the
        same run mostly bought idle time: four attempts cost 65s per failing paper
        against 5s now. The trailing sleep stays - it paces requests to the roughly one
        per five seconds the unauthenticated endpoint allows, and dropping it would
        guarantee the 429s it is there to avoid."""
        key = re.sub(r"[^A-Za-z0-9._-]", "_", doi)
        f = os.path.join(CACHE_S2, key + ".json")
        hit = _cache_read(f, doi)
        if hit is not None:
            return hit
        if self.no_fetch:
            return {"error": "not cached, --no-fetch"}
        m = re.match(r"10\.48550/arxiv\.(.+)", doi, re.I)
        ident = "ARXIV:" + m.group(1) if m else "DOI:" + doi
        url = ("https://api.semanticscholar.org/graph/v1/paper/"
               + urllib.parse.quote(ident, safe=":")
               + "?fields=title,year,externalIds,references.externalIds")
        try:
            d = _get_json(url)
            if "error" in d or "message" in d:
                d = {"error": str(d.get("error") or d.get("message"))[:60]}
        except Exception as e:
            d = {"error": str(e)[:80]}
        if "error" in d:
            self.s2_failures.append((doi, d["error"]))
        else:
            _cache_write(f, d)
        time.sleep(5)
        return d


# ---------------------------------------------------------------- pipeline

def norm_doi(d) -> str:
    return (d or "").strip().lower().replace("https://doi.org/", "")


ARXIV_RE = re.compile(r"(?:arxiv[:.]|abs/|pdf/)\s*(\d{4}\.\d{4,5})", re.I)


def norm_arxiv(*fields):
    """arXiv id from any of a Zotero item's identifier fields, version stripped.

    Semantic Scholar identifies much of this library's machine-learning literature
    by ArXiv id and no DOI at all - every TESSERA reference to Barlow Twins, AnySat
    and MOSAIKS arrives as {"ArXiv": ..., "DBLP": ..., "CorpusId": ...} - so matching
    S2 reference lists on DOI alone dropped those edges silently. Several fields are
    checked because the id lands in a different one depending on which translator
    imported the item: DOI for an arXiv-DOI preprint, archiveID for a Zotero arXiv
    import, url or extra for a record catalogued as its published version."""
    for f in fields:
        m = ARXIV_RE.search(str(f or ""))
        if m:
            return m.group(1)
    return None


def pull(fetch):
    """The library, minus notes, attachments and anything in the trash."""
    raw = fetch.zotero_all("items", limit=100, itemType="-attachment")
    items = [i["data"] for i in raw
             if i["data"]["itemType"] not in ("note", "attachment")
             and not i["data"].get("deleted")]
    colls = {c["data"]["key"]: c["data"]["name"] for c in fetch.zotero_all("collections", limit=50)}
    print(f"pulled {len(items)} items, {len(colls)} collections")
    return items, colls


def resolve_identity(fetch, items, colls, AL):
    """One node per item, with its OpenAlex identity resolved and its facets read off its tags.

    Iterates `items` in the order Zotero returned them, never sorted: that order
    sets the order of the OpenAlex calls, and so the order of the failure lines in
    the build summary.
    """
    nodes, oa_by_key = {}, {}
    for it in items:
        k = it["key"]
        doi = norm_doi(it.get("DOI"))
        ids, cited_by, oa_year, err = [], None, None, None
        if doi:
            w = fetch.openalex_by_doi(doi)
            if w.get("error"):
                err = w["error"]
            else:
                if w.get("id"):
                    ids.append(w["id"])
                cited_by = w.get("cited_by_count")
                oa_year = w.get("publication_year")
                oa_by_key[k] = w
        ids += AL["work_aliases"].get(k, [])
        manual = AL["manual_openalex_ids"].get(k)
        if manual:
            ids.append(manual)
        # The Zotero date wins. OpenAlex reports the year of whichever edition the DOI
        # points at, so a reissue DOI carries the reprint year and drags the work
        # forward on the timeline - and that is the one field the user can correct.
        m = re.search(r"(1[89]\d\d|20\d\d)", it.get("date") or "")
        year = int(m.group(1)) if m else oa_year
        tags = [t["tag"] for t in it.get("tags", [])]
        nodes[k] = {
            "key": k, "title": it.get("title") or "(untitled)",
            "creators": [(c.get("lastName") or c.get("name") or "?")
                         for c in it.get("creators", [])][:3],
            "itemType": it["itemType"], "date": it.get("date") or "", "year": year,
            "date_added": it.get("dateAdded") or "",
            "doi": doi or None, "ids": [i for i in ids if i],
            "arxiv": norm_arxiv(it.get("DOI"), it.get("archiveID"),
                                it.get("url"), it.get("extra")),
            "cited_by": cited_by, "tags": tags,
            "collections": [colls.get(c, c) for c in it.get("collections", [])],
            "abstract": (it.get("abstractNote") or "").strip(),
            "stored_role": next((t.split(": ", 1)[1] for t in tags if t.startswith("role: ")), None),
            "unresolved": AL["unresolvable"].get(k) or err,
        }
    return nodes, oa_by_key


def fetch_references(fetch, nodes, oa_by_key):
    """Reference lists: OpenAlex, then Semantic Scholar for the gaps.

    Iterates nodes.items() rather than sorted(nodes) for the same reason
    resolve_identity iterates `items` unsorted - it fixes the order of the
    Semantic Scholar calls, and so of the FETCH FAILED lines.
    """
    refs, doi_refs, arxiv_refs = {}, {}, {}
    fallbacks = 0
    for k, n in nodes.items():
        w = oa_by_key.get(k, {})
        r = w.get("referenced_works") or []
        refs[k] = set(r)
        doi_refs[k] = set()
        arxiv_refs[k] = set()
        if not r and n["doi"]:
            d = fetch.s2_refs(n["doi"])
            if not d.get("error"):
                fallbacks += 1
                for ref in d.get("references") or []:
                    ex = ref.get("externalIds") or {}
                    if ex.get("DOI"):
                        doi_refs[k].add(norm_doi(ex["DOI"]))
                    if ex.get("ArXiv"):
                        arxiv_refs[k].add(norm_arxiv("arXiv:" + str(ex["ArXiv"])))
    missing = [k for k, n in nodes.items()
               if not refs[k] and not doi_refs[k] and not arxiv_refs[k]]
    return refs, doi_refs, arxiv_refs, fallbacks, missing


def report_fetch(fetch, refs, fallbacks, missing):
    """How much of the graph is missing, and why. Prints only.

    Its own step, between fetching and edge building, so these lines keep their
    position in the transcript.
    """
    failed = len(fetch.s2_failures) + len(fetch.oa_failures)
    print(f"reference lists: {sum(1 for v in refs.values() if v)} from OpenAlex, "
          f"{fallbacks} recovered via Semantic Scholar, {failed} FAILED, "
          f"{len(missing)} with none available")
    for doi, err in fetch.oa_failures:
        print(f"   OPENALEX FAILED  {doi:<31} {err}")
    for doi, err in fetch.s2_failures:
        print(f"   FETCH FAILED  {doi:<34} {err}")
    if fetch.s2_failures or fetch.oa_failures:
        print("   ^ these carry no outbound edges in this build. The failure is not "
              "cached, so re-running retries them.")


def build_edges(nodes, refs, doi_refs, arxiv_refs, AL):
    """Citation edges, by whichever identifier resolves to a node in this library."""
    id2key, doi2key, arxiv2key = {}, {}, {}
    for k, n in nodes.items():
        for i in n["ids"]:
            id2key[i] = k
        if n["doi"]:
            doi2key[n["doi"]] = k
        if n["arxiv"]:
            arxiv2key[n["arxiv"]] = k
    edges, seen = [], set()

    def add(src, dst, how):
        if src == dst or (src, dst) in seen:
            return
        seen.add((src, dst))
        edges.append({"source": src, "target": dst, "via": how})

    for k in sorted(nodes):                      # sorted: sets iterate unstably
        for r in sorted(refs[k]):
            if r in id2key:
                add(k, id2key[r], "openalex")
        for d in sorted(doi_refs[k]):
            if d in doi2key:
                add(k, doi2key[d], "semanticscholar")
        for a in sorted(x for x in arxiv_refs[k] if x):
            if a in arxiv2key:
                add(k, arxiv2key[a], "semanticscholar")
    for src, dst in AL["manual_edges"]["edges"]:
        add(src, dst, "manual")

    indeg = {k: 0 for k in nodes}
    outdeg = {k: 0 for k in nodes}
    for e in edges:
        outdeg[e["source"]] += 1
        indeg[e["target"]] += 1
    # A citation can only point backwards. A forward edge means a wrong date on the
    # citing or cited record - usually a reissue DOI carrying the reprint year - and it
    # is invisible on the map unless it is called out here.
    backwards = [e for e in edges
                 if nodes[e["source"]]["year"] and nodes[e["target"]]["year"]
                 and nodes[e["source"]]["year"] < nodes[e["target"]]["year"]]
    if backwards:
        print(f"WARNING: {len(backwards)} citation(s) point forward in time - "
              "check these dates:")
        for e in backwards:
            s, d = nodes[e["source"]], nodes[e["target"]]
            print(f'   {(s["creators"] or ["?"])[0]} {s["year"]} -> '
                  f'{(d["creators"] or ["?"])[0]} {d["year"]}  '
                  "(cited work dated later than the citing one)")

    via = Counter(e["via"] for e in edges)
    print(f'edges: {len(edges)} ({via["openalex"]} openalex, '
          f'{via["semanticscholar"]} s2, {via["manual"]} manual)')
    return edges, indeg, outdeg


def classify(nodes, indeg, outdeg):
    """Assign each node a role, and describe the threshold used.

    Returns the threshold as graph.json records it, which keeps PCTILE local to
    the comment that justifies it.
    """
    # Percentile-based so the threshold stays meaningful as the library grows: a
    # fixed constant would let the foundational set drift upward in count as
    # sources are added.
    #
    # 80th rather than 85th. The in-degree distribution is very flat in the middle
    # - every percentile from the 85th to the 92nd returns the same value - so the
    # exact cut lands arbitrarily on whichever integer the tail happens to sit on,
    # and a paper one inbound citation short is not meaningfully less central than
    # one exactly on the line. The 80th to 84th all return the next value down,
    # which is the same kind of plateau: the choice is between two stable shelves,
    # not a fine-grained tuning.
    PCTILE = 0.80
    pos = sorted([v for v in indeg.values() if v > 0])
    pcut = pos[int(len(pos) * PCTILE)] if pos else 0
    thresh = max(3, pcut)
    for k, n in nodes.items():
        n["in_degree"], n["out_degree"] = indeg[k], outdeg[k]
        if n["stored_role"] == "contrarian":          # judged beats computed
            n["role"], n["role_source"] = "contrarian", "judged"
        elif indeg[k] >= thresh:
            n["role"], n["role_source"] = "foundational", "computed"
        elif outdeg[k] >= 1 or indeg[k] >= 1:
            n["role"], n["role_source"] = "additional", "computed"
        else:
            n["role"], n["role_source"] = "satellite", "computed"
    return {"foundational_in_degree": thresh,
            "basis": f"max(3, {round(PCTILE * 100)}th percentile of non-zero in-degree)"}


# One vocabulary for the whole library: subject (what it is about), question (what
# problem it addresses) and approach (what tradition or technique it uses) apply to
# every collection, so a link can form between any two sources.
#
# Module level, and recorded in graph.json as "affinity", because two other places
# need to agree with it: render.py's BAND_FIELDS, and the cluster labelling in
# force.py. The labelling used to allow any facet, so a cluster could be named by an
# evidence: tag that had taken no part in forming it. Shipping the list with the
# graph means the renderer reads what actually built the edges instead of restating it.
AFFINITY = ("subject:", "question:", "approach:")


def tag_affinity(nodes, edges):
    """Shared-vocabulary edges, where no citation already joins the pair."""
    # Shared vocabulary, not shared citation. Restricted to the two conceptual
    # facets: lens (which tradition) and theme (which argument). Emitted only where
    # no citation edge already joins the pair — where one exists it says strictly
    # more, and drawing both would double the line for no added meaning.
    TAG_MIN = 0.5

    def _lt(n):
        return {x for x in n["tags"] if x.startswith(AFFINITY)}

    cited_pairs = {(e["source"], e["target"]) for e in edges}
    cited_pairs |= {(b, a) for a, b in cited_pairs}
    keys = sorted(nodes)
    tag_edges = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            A, B = _lt(nodes[a]), _lt(nodes[b])
            if not A or not B or (a, b) in cited_pairs:
                continue
            inter = A & B
            j = len(inter) / len(A | B)
            if j >= TAG_MIN:
                tag_edges.append({"a": a, "b": b, "j": round(j, 3), "shared": sorted(inter)})
    print(f"vocabulary edges: {len(tag_edges)} at Jaccard >= {TAG_MIN:.2f} "
          f"({sum(1 for n in nodes.values() if _lt(n))} items carry affinity facets)")
    return tag_edges, TAG_MIN


def emit(nodes, edges, tag_edges, threshold, tag_min):
    """Write out/graph.json and summarise the run."""
    graph = {
        "generated": time.strftime("%Y-%m-%d"),
        "affinity": list(AFFINITY),
        "tag_edges": tag_edges,
        "tag_min": tag_min,
        "threshold": threshold,
        "counts": {"nodes": len(nodes), "edges": len(edges),
                   "unresolved": sum(1 for n in nodes.values() if n["unresolved"]),
                   "tag_edges": len(tag_edges),
                   "no_doi": sum(1 for n in nodes.values() if not n["doi"])},
        "nodes": sorted(nodes.values(), key=lambda n: (n["year"] or 0, n["title"])),
        "edges": sorted(edges, key=lambda e: (e["source"], e["target"])),
    }
    p = os.path.join(OUT, "graph.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=1, sort_keys=True)
    print(f'wrote {p}  |  foundational threshold: '
          f'in-degree >= {threshold["foundational_in_degree"]}')
    print("roles:", dict(Counter(n["role"] for n in nodes.values())))


def main():
    ap = argparse.ArgumentParser(
        description="Build a citation map of a Zotero library.")
    ap.add_argument("--no-fetch", action="store_true",
                    help="work from the recorded library and cached API responses "
                         "only; make no network calls")
    args = ap.parse_args()

    for d in (CACHE_OA, CACHE_S2, CACHE_ZOTERO, OUT):
        os.makedirs(d, exist_ok=True)

    if not MAILTO and not args.no_fetch:
        print("WARNING: ZOTERO_MAP_MAILTO unset - OpenAlex and Semantic Scholar calls go "
              "to the common pool, which is slower and rate-limited more aggressively.")
        print("   export ZOTERO_MAP_MAILTO=you@example.com   to join the polite pool")

    fetch = Fetcher.connect(args.no_fetch)

    with open(os.path.join(HERE, "aliases.json"), encoding="utf-8") as fh:
        AL = json.load(fh)

    items, colls = pull(fetch)
    nodes, oa_by_key = resolve_identity(fetch, items, colls, AL)
    refs, doi_refs, arxiv_refs, fallbacks, missing = fetch_references(fetch, nodes, oa_by_key)
    report_fetch(fetch, refs, fallbacks, missing)
    edges, indeg, outdeg = build_edges(nodes, refs, doi_refs, arxiv_refs, AL)
    threshold = classify(nodes, indeg, outdeg)
    tag_edges, tag_min = tag_affinity(nodes, edges)
    emit(nodes, edges, tag_edges, threshold, tag_min)


if __name__ == "__main__":
    main()
