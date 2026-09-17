#!/usr/bin/env python3
"""Build a citation map of a Zotero library.

Pipeline: pull -> resolve identity -> fetch references -> build edges -> classify -> emit.

Computed values (degree, year, citation counts) are recomputed every run and never
stored, so they cannot drift. Only judged facts persist: `role: contrarian` tags in
Zotero, and the identity fixes in aliases.json.

Usage:  python3 build.py [--no-fetch]
        --no-fetch   use cache only; never hit the network
"""

import json, os, re, subprocess, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_OA = os.path.join(HERE, "cache", "openalex")
CACHE_S2 = os.path.join(HERE, "cache", "s2")
OUT = os.path.join(HERE, "out")
CURL_CONF = os.path.expanduser("~/.config/zotero-api.conf")
# OpenAlex and Semantic Scholar both run a "polite pool": calls carrying a contact
# address get faster and more reliable service. Set ZOTERO_MAP_MAILTO to opt in.
# Leaving it unset is supported - the address is simply omitted and the calls fall
# back to the common pool - so no personal address is baked into this file.
MAILTO = os.environ.get("ZOTERO_MAP_MAILTO", "").strip()
USER_AGENT = "zotero-map (%s)" % MAILTO if MAILTO else "zotero-map"
NO_FETCH = "--no-fetch" in sys.argv

for d in (CACHE_OA, CACHE_S2, OUT):
    os.makedirs(d, exist_ok=True)

if not MAILTO and not NO_FETCH:
    print("WARNING: ZOTERO_MAP_MAILTO unset - OpenAlex and Semantic Scholar calls go "
          "to the common pool, which is slower and rate-limited more aggressively.")
    print("   export ZOTERO_MAP_MAILTO=you@example.com   to join the polite pool")


# ---------------------------------------------------------------- Zotero

def zotero(path, **params):
    url = "https://api.zotero.org/users/%s/%s" % (USER_ID, path)
    if params:
        url += "?" + urllib.parse.urlencode(params)
    r = subprocess.run(["curl", "-s", "-m", "60", "--config", CURL_CONF, url],
                       capture_output=True, text=True)
    return json.loads(r.stdout)


def zotero_user_id():
    r = subprocess.run(["curl", "-s", "-m", "30", "--config", CURL_CONF,
                        "https://api.zotero.org/keys/current"],
                       capture_output=True, text=True)
    # never print this response: it echoes the API key back in plaintext
    return json.loads(r.stdout)["userID"]


# ---------------------------------------------------------------- external APIs

def _get_json(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


# Same contract as S2_FAILURES below, for the OpenAlex side.
OA_FAILURES = []


def openalex_by_doi(doi):
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
    if os.path.exists(f):
        return json.load(open(f))
    if NO_FETCH:
        return {"error": "not cached, --no-fetch"}
    url = "https://api.openalex.org/works/doi:%s" % urllib.parse.quote(doi, safe="")
    if MAILTO:
        url += "?mailto=" + urllib.parse.quote(MAILTO, safe="")
    try:
        w = _get_json(url)
    except Exception as e:
        w = {"error": str(e)[:80]}
    if "error" in w:
        OA_FAILURES.append((doi, w["error"]))
    else:
        json.dump(w, open(f, "w"))
    time.sleep(0.12)
    return w


# Reference-list fetches that failed outright, as (doi, error). Kept so the run can
# say how much of the graph is missing rather than reporting only what it found: a
# failed fetch and a paper that genuinely cites nothing are indistinguishable in the
# edge list, and silently conflating them makes isolated nodes look like findings.
S2_FAILURES = []


def s2_refs(doi):
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
    if os.path.exists(f):
        return json.load(open(f))
    if NO_FETCH:
        return {"error": "not cached, --no-fetch"}
    m = re.match(r"10\.48550/arxiv\.(.+)", doi, re.I)
    ident = "ARXIV:" + m.group(1) if m else "DOI:" + doi
    url = ("https://api.semanticscholar.org/graph/v1/paper/%s"
           "?fields=title,year,externalIds,references.externalIds" % urllib.parse.quote(ident, safe=":"))
    try:
        d = _get_json(url)
        if "error" in d or "message" in d:
            d = {"error": str(d.get("error") or d.get("message"))[:60]}
    except Exception as e:
        d = {"error": str(e)[:80]}
    if "error" in d:
        S2_FAILURES.append((doi, d["error"]))
    else:
        json.dump(d, open(f, "w"))
    time.sleep(5)
    return d


# ---------------------------------------------------------------- pipeline

def norm_doi(d):
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


def main():
    global USER_ID
    USER_ID = zotero_user_id()
    AL = json.load(open(os.path.join(HERE, "aliases.json")))

    # 1. pull -----------------------------------------------------------
    raw = zotero("items", limit=100, itemType="-attachment")
    items = [i["data"] for i in raw
             if i["data"]["itemType"] not in ("note", "attachment")
             and not i["data"].get("deleted")]
    colls = {c["data"]["key"]: c["data"]["name"] for c in zotero("collections", limit=50)}
    print("pulled %d items, %d collections" % (len(items), len(colls)))

    # 2. resolve identity ------------------------------------------------
    nodes, oa_by_key = {}, {}
    for it in items:
        k = it["key"]
        doi = norm_doi(it.get("DOI"))
        ids, cited_by, oa_year, err = [], None, None, None
        if doi:
            w = openalex_by_doi(doi)
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
            "evidence": next((t.split(": ", 1)[1] for t in tags if t.startswith("evidence: ")), None),
            "stored_role": next((t.split(": ", 1)[1] for t in tags if t.startswith("role: ")), None),
            "unresolved": AL["unresolvable"].get(k) or err,
        }

    # 3. fetch references (OpenAlex, then Semantic Scholar for the gaps) --
    refs, doi_refs, arxiv_refs = {}, {}, {}
    fallbacks = 0
    for k, n in nodes.items():
        w = oa_by_key.get(k, {})
        r = w.get("referenced_works") or []
        refs[k] = set(r)
        doi_refs[k] = set()
        arxiv_refs[k] = set()
        if not r and n["doi"]:
            d = s2_refs(n["doi"])
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
    print("reference lists: %d from OpenAlex, %d recovered via Semantic Scholar, "
          "%d FAILED, %d with none available"
          % (sum(1 for v in refs.values() if v), fallbacks,
             len(S2_FAILURES) + len(OA_FAILURES), len(missing)))
    for doi, err in OA_FAILURES:
        print("   OPENALEX FAILED  %-31s %s" % (doi, err))
    for doi, err in S2_FAILURES:
        print("   FETCH FAILED  %-34s %s" % (doi, err))
    if S2_FAILURES or OA_FAILURES:
        print("   ^ these carry no outbound edges in this build. The failure is not "
              "cached, so re-running retries them.")

    # 4. build edges -----------------------------------------------------
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
        print("WARNING: %d citation(s) point forward in time - check these dates:" % len(backwards))
        for e in backwards:
            s, d = nodes[e["source"]], nodes[e["target"]]
            print("   %s %s -> %s %s  (cited work dated later than the citing one)"
                  % ((s["creators"] or ["?"])[0], s["year"], (d["creators"] or ["?"])[0], d["year"]))

    print("edges: %d (%d openalex, %d s2, %d manual)" % (
        len(edges), sum(1 for e in edges if e["via"] == "openalex"),
        sum(1 for e in edges if e["via"] == "semanticscholar"),
        sum(1 for e in edges if e["via"] == "manual")))

    # 5. classify --------------------------------------------------------
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
        elif outdeg[k] >= 1:
            n["role"], n["role_source"] = "additional", "computed"
        elif indeg[k] >= 1:
            n["role"], n["role_source"] = "additional", "computed"
        else:
            n["role"], n["role_source"] = "satellite", "computed"

    # 6. tag affinity ----------------------------------------------------
    # Shared vocabulary, not shared citation. Restricted to the two conceptual
    # facets: lens (which tradition) and theme (which argument). Emitted only where
    # no citation edge already joins the pair — where one exists it says strictly
    # more, and drawing both would double the line for no added meaning.
    TAG_MIN = 0.5
    # One vocabulary for the whole library: subject (what it is about), question (what
    # problem it addresses) and approach (what tradition or technique it uses) apply to
    # every collection, so a link can form between any two sources.
    AFFINITY = ("subject:", "question:", "approach:")

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
    for k in nodes:
        nodes[k]["tag_degree"] = sum(1 for e in tag_edges if k in (e["a"], e["b"]))
    print("vocabulary edges: %d at Jaccard >= %.2f (%d items carry affinity facets)"
          % (len(tag_edges), TAG_MIN, sum(1 for n in nodes.values() if _lt(n))))

    graph = {
        "generated": time.strftime("%Y-%m-%d"),
        "tag_edges": tag_edges,
        "tag_min": TAG_MIN,
        "threshold": {"foundational_in_degree": thresh,
                      "basis": "max(3, %dth percentile of non-zero in-degree)" % round(PCTILE * 100)},
        "counts": {"nodes": len(nodes), "edges": len(edges),
                   "unresolved": sum(1 for n in nodes.values() if n["unresolved"]),
                   "tag_edges": len(tag_edges),
                   "no_doi": sum(1 for n in nodes.values() if not n["doi"])},
        "nodes": sorted(nodes.values(), key=lambda n: (n["year"] or 0, n["title"])),
        "edges": sorted(edges, key=lambda e: (e["source"], e["target"])),
    }
    p = os.path.join(OUT, "graph.json")
    json.dump(graph, open(p, "w"), indent=1, sort_keys=True)
    print("wrote %s  |  foundational threshold: in-degree >= %d" % (p, thresh))
    from collections import Counter
    print("roles:", dict(Counter(n["role"] for n in nodes.values())))


if __name__ == "__main__":
    main()
