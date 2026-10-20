#!/usr/bin/env python3
"""Build a citation map of a Zotero library.

Pipeline: pull -> resolve identity -> fetch references -> build edges -> classify -> emit.

Computed values (degree, year, citation counts) are recomputed every run and never
stored, so they cannot drift. Only judged facts persist: `role: contrarian` tags in
Zotero, and the identity fixes in aliases.json.

Usage:  python3 build.py [--no-fetch] [--progress]
        --no-fetch   work from the recorded library and cached API responses only;
                     makes no network calls at all. Needs one prior ordinary run to
                     have recorded the Zotero pull under cache/zotero/.
        --progress   also write machine-readable progress to stderr, one JSON object
                     per line, for app.py. stdout is unchanged either way.
"""

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_OA = os.path.join(HERE, "cache", "openalex")
CACHE_S2 = os.path.join(HERE, "cache", "s2")
CACHE_ZOTERO = os.path.join(HERE, "cache", "zotero")
OUT = os.path.join(HERE, "out")
# The Zotero key. Same path on every platform - ~ is the home folder on macOS and Linux
# and %USERPROFILE% on Windows - and still in curl's config-file format, so the curl
# commands in the zotero-library skill read the same file this does. ZOTERO_API_CONF
# exists so app.py's setup flow can be exercised against a scratch file.
KEY_FILE = os.environ.get("ZOTERO_API_CONF") or os.path.join(
    os.path.expanduser("~"), ".config", "zotero-api.conf")
# OpenAlex and Semantic Scholar both run a "polite pool": calls carrying a contact
# address get faster and more reliable service. Set ZOTERO_MAP_MAILTO to opt in.
# Leaving it unset is supported - the address is simply omitted and the calls fall
# back to the common pool - so no personal address is baked into this file.
MAILTO = os.environ.get("ZOTERO_MAP_MAILTO", "").strip()
USER_AGENT = f"zotero-map ({MAILTO})" if MAILTO else "zotero-map"
# Where Zotero keeps its profiles, whose prefs.js holds a non-default server port.
ZOTERO_PROFILES = {
    "win32": os.path.join(os.environ.get("APPDATA", ""), "Zotero", "Zotero", "Profiles"),
    "darwin": os.path.expanduser("~/Library/Application Support/Zotero/Profiles"),
}.get(sys.platform, os.path.expanduser("~/.zotero/zotero"))
ZOTERO_PORT = 23119        # Zotero's own default for its local server
PORT_PREF = re.compile(r'user_pref\("extensions\.zotero\.httpServer\.port",\s*(\d+)\)')


# ---------------------------------------------------------------- Zotero

def zotero_key():
    """The API key from KEY_FILE, or a SystemExit that says how to provide one."""
    try:
        with open(KEY_FILE, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        raise SystemExit(f"No Zotero API key at {KEY_FILE}. Run app.py to link one, or "
                         "see Requirements in README.md.")
    m = re.search(r"Zotero-API-Key:\s*([A-Za-z0-9]+)", text)
    if not m:
        raise SystemExit(f"{KEY_FILE} carries no Zotero-API-Key header. Run app.py to "
                         "link the key again.")
    return m.group(1)


CERT_HELP = ("Python could not verify the HTTPS certificate of {host}. With Python from "
             "python.org on macOS, run 'Install Certificates.command' in the "
             "Applications/Python 3.x folder once, then try again.")


def cert_failure(e):
    """True when a network error is a missing certificate store, not a bad connection.

    The python.org installer on macOS ships without one until a bundled script is
    run, and every HTTPS call fails until then. That has to stop the run with the
    fix spelled out: caught like any other error it would become a FETCH FAILED line
    per paper, and an empty graph that looks like a finding.
    """
    return isinstance(getattr(e, "reason", e), ssl.SSLCertVerificationError)


def zotero_http(path, params=None, key=None, headers=None, timeout=30):
    """GET from the Zotero Web API. Returns (status, headers, body bytes).

    Any HTTP status comes back rather than raising, 304 included, so callers can
    branch on it. A failed connection raises urllib.error.URLError or OSError.

    Python's own urllib rather than curl, which this used to shell out to: it is the
    same on macOS, Windows and Linux, reads the system proxy settings on each, and
    decodes nothing - curl's output came back through the platform's default text
    encoding, which on Windows is not UTF-8.
    """
    url = "https://api.zotero.org/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Zotero-API-Key": key or zotero_key(), "Zotero-API-Version": "3",
        "User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def zotero_port():
    """Zotero's local server port: its own default unless a profile's prefs.js changes it."""
    try:
        profiles = os.listdir(ZOTERO_PROFILES)
    except OSError:
        return ZOTERO_PORT
    for name in sorted(profiles):
        try:
            with open(os.path.join(ZOTERO_PROFILES, name, "prefs.js"), encoding="utf-8",
                      errors="replace") as fh:
                m = PORT_PREF.search(fh.read())
        except OSError:
            continue
        if m:
            return int(m.group(1))
    return ZOTERO_PORT


# No proxy for 127.0.0.1. urllib reads the system proxy settings on Windows and macOS,
# and a proxy answering for 127.0.0.1 would read as Zotero answering.
LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def zotero_local_http(path, params=None, headers=None, timeout=60):
    """GET from the local API of the Zotero desktop app. Same contract as zotero_http.

    The local API (Zotero 7 and later, off until "Allow other applications on this
    computer to communicate with Zotero" is ticked in Settings > Advanced) answers the
    Web API's read requests from the zotero.sqlite the app has open, through Zotero
    itself - so nothing here reads the database file, and nothing waits for a sync.

    No API key is sent: the local API needs none, and the key goes only to zotero.org.
    A response without Zotero's own Zotero-API-Version header comes back as status 0,
    so whatever else might be listening on the port is never read as the library.
    """
    url = f"http://127.0.0.1:{zotero_port()}/api/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Zotero-API-Version": "3", "User-Agent": USER_AGENT, **(headers or {})})
    try:
        with LOCAL_OPENER.open(req, timeout=timeout) as r:
            status, hdrs, body = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        status, hdrs, body = e.code, e.headers, e.read()
    if not (hdrs and hdrs.get("Zotero-API-Version")):
        return 0, hdrs, body
    return status, hdrs, body


def zotero_local_problem(user_id, timeout=10):
    """None when the local API serves this user's library, else why it doesn't.

    The path names the real user id, not the local API's alias 0, so that Zotero
    itself refuses when it is signed in to a different account - or to none - and
    the map is never built from someone else's library.
    """
    try:
        status, _, body = zotero_local_http(f"users/{user_id}/items/top",
                                            {"limit": 1, "format": "keys"}, timeout=timeout)
    except (urllib.error.URLError, OSError):
        return "Zotero is not running"
    if status == 200:
        return None
    if status == 403:
        return ("its local API is off - tick 'Allow other applications on this computer "
                "to communicate with Zotero' in Zotero's Settings > Advanced")
    if status == 400 and b"logged-in user" in body:
        return "Zotero on this computer is signed in to a different account, or to none"
    if status in (0, 404):
        return "no local API answered - it needs Zotero 7 or later"
    return f"its local API answered HTTP {status}"


def _zotero_json(path, params, what, timeout):
    """A Zotero call that must succeed: the parsed body, or a SystemExit naming the cause.

    The body is never echoed into an error. /keys/current returns the key itself.
    """
    try:
        status, _, body = zotero_http(path, params, timeout=timeout)
    except (urllib.error.URLError, OSError) as e:
        if cert_failure(e):
            raise SystemExit(CERT_HELP.format(host="api.zotero.org"))
        raise SystemExit(f"Could not reach api.zotero.org fetching {what}: "
                         f"{getattr(e, 'reason', e)}")
    if status in (401, 403):
        raise SystemExit(f"Zotero rejected the key in {KEY_FILE} fetching {what}. "
                         "Run app.py to link the key again.")
    if status != 200:
        raise SystemExit(f"Zotero answered HTTP {status} fetching {what}.")
    try:
        return json.loads(body)
    except ValueError:
        raise SystemExit(f"Zotero returned a non-JSON body for {what}.")


# ---------------------------------------------------------------- progress

def stdout_never_fails():
    """Make printing a title that the console cannot encode print '?' instead of crashing.

    On Windows, output redirected to a file or a pipe is encoded with the locale's
    code page, so an author's name outside it raised UnicodeEncodeError partway
    through a run. On a UTF-8 terminal - macOS, Linux, the Windows console itself -
    nothing is ever replaced, so the output is unchanged there.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def no_progress(**event):
    """The default progress sink: a terminal run reports nothing beyond stdout."""


def stderr_progress(**event):
    """--progress: one JSON object per line on stderr, which app.py reads.

    stderr rather than stdout so the human transcript stays byte-identical with and
    without the flag - app.py keeps that transcript as the run log. Events are
    {"p": "stage", "stage", "total"?, "uncached"?} when a stage opens and
    {"p": "tick", "stage", "done", "net"} per unit of work, where net says whether
    that unit went to the network rather than the cache - which is what lets the
    app's time estimate tell a 5s Semantic Scholar call from a cache hit.
    """
    print(json.dumps(event), file=sys.stderr, flush=True)


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
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def oa_cache_path(doi):
    return os.path.join(CACHE_OA, re.sub(r"[^A-Za-z0-9._-]", "_", doi) + ".json")


def s2_cache_path(doi):
    return os.path.join(CACHE_S2, re.sub(r"[^A-Za-z0-9._-]", "_", doi) + ".json")


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


class LocalGone(Exception):
    """The Zotero app's local API stopped serving the library partway through a run."""


class Fetcher:
    """Every outbound call, plus the per-run state they accumulate.

    Three things were module globals and are now here: the Zotero user id, which is
    a network result rather than configuration and so could never be a constant, and
    the two failure lists. They stay LISTS - keying them by DOI would silently
    dedupe a DOI that fails twice, and the count is part of the build summary.

    The genuinely constant configuration (cache paths, KEY_FILE, MAILTO,
    USER_AGENT) stays at module scope, where it reads as configuration.
    """

    def __init__(self, user_id, no_fetch, progress=no_progress, source="web"):
        self.user_id = user_id
        self.no_fetch = no_fetch
        self.progress = progress
        # Where the library is read from: "local", the Zotero desktop app's local API,
        # or "web", zotero.org. After each zotero_all call it is the source of the rows
        # that call returned, which pull() records next to the library version, since
        # the two sources count versions differently - see zotero_all.
        self.source = source
        # Outbound reference-list calls made so far. A loop reads it before and after
        # each item to report whether that item cost a network round trip.
        self.net_calls = 0
        # Reference-list fetches that failed outright, as (doi, error). Kept so the run
        # can say how much of the graph is missing rather than reporting only what it
        # found: a failed fetch and a paper that genuinely cites nothing are
        # indistinguishable in the edge list, and silently conflating them makes
        # isolated nodes look like findings.
        self.oa_failures = []
        self.s2_failures = []

    # ------------------------------------------------------------ Zotero

    @classmethod
    def connect(cls, no_fetch, progress=no_progress):
        """Resolve the library's user id, and choose where to read the library from.

        Local first: when the recorded id is one the Zotero app on this computer is
        signed in to and serving through its local API, that is the whole connection
        and zotero.org is not contacted. Otherwise /keys/current names the key's owner,
        and the local API is tried again for that id - a first run has nothing
        recorded, and the recorded id may be from a key since replaced - before
        falling back to the Web API.

        Only the integer id is ever written to disk. The /keys/current response
        echoes the API key back in plaintext, so it is never cached and never
        printed, not even inside an error.
        """
        cache = os.path.join(CACHE_ZOTERO, "user_id.json")
        if no_fetch:
            hit = _cache_read(cache, "the Zotero user id")
            if hit is None:
                raise _need_recorded(cache)
            return cls(hit, no_fetch, progress)
        recorded = _cache_read(cache, "the Zotero user id")
        if recorded is not None and zotero_local_problem(recorded) is None:
            print("zotero: reading the library from Zotero on this computer")
            return cls(recorded, no_fetch, progress, "local")
        user_id = _zotero_json("keys/current", None, "the API key owner", 30)["userID"]
        _cache_write(cache, user_id)
        problem = zotero_local_problem(user_id)
        if problem is None:
            print("zotero: reading the library from Zotero on this computer")
            return cls(user_id, no_fetch, progress, "local")
        print(f"zotero: reading the library from zotero.org ({problem})")
        return cls(user_id, no_fetch, progress)

    def zotero(self, path, **params):
        return _zotero_json(f"users/{self.user_id}/{path}", params, path, 60)

    def zotero_local(self, path, **params):
        """A local API call, or LocalGone when the app stops serving the library."""
        try:
            status, _, body = zotero_local_http(f"users/{self.user_id}/{path}", params)
        except (urllib.error.URLError, OSError) as e:
            raise LocalGone(f"stopped answering: {getattr(e, 'reason', e)}")
        if status != 200:
            raise LocalGone(f"answered HTTP {status}" if status else "stopped answering")
        try:
            return json.loads(body)
        except ValueError:
            raise LocalGone("returned a non-JSON body")

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

        The recording carries its source along with the rows. An item's `version`
        means something different in each: zotero.org counts synced changes, while
        recent Zotero versions count local edits in the local API, with no relation
        between the two numbers. A version is only comparable with others from the
        same source, so the source has to travel with the rows. A recording from
        before sources were tracked is a bare list, and came from zotero.org.

        When the local API stops answering partway through a run - Zotero was quit -
        this endpoint is read again in full from zotero.org, and so is every endpoint
        after it, so no single recording mixes rows from both.

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
            if isinstance(hit, list):
                self.source = "web"
                return hit
            self.source = hit["source"]
            return hit["rows"]
        rows = None
        if self.source == "local":
            try:
                rows = self._pages(self.zotero_local, path, limit, params)
            except LocalGone as e:
                print(f"zotero: Zotero on this computer {e} - reading {path} from zotero.org")
                self.source = "web"
        if rows is None:
            rows = self._pages(self.zotero, path, limit, params)
        _cache_write(cache, {"source": self.source, "rows": rows})
        return rows

    @staticmethod
    def _pages(get, path, limit, params):
        rows, start = [], 0
        while True:
            page = get(path, start=start, limit=limit, **params)
            rows += page
            if len(page) < limit:
                break
            start += limit
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
        f = oa_cache_path(doi)
        hit = _cache_read(f, doi)
        if hit is not None:
            return hit
        if self.no_fetch:
            return {"error": "not cached, --no-fetch"}
        self.net_calls += 1
        url = "https://api.openalex.org/works/doi:" + urllib.parse.quote(doi, safe="")
        if MAILTO:
            url += "?mailto=" + urllib.parse.quote(MAILTO, safe="")
        try:
            w = _get_json(url)
        except Exception as e:
            if cert_failure(e):
                raise SystemExit(CERT_HELP.format(host="api.openalex.org"))
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
        f = s2_cache_path(doi)
        hit = _cache_read(f, doi)
        if hit is not None:
            return hit
        if self.no_fetch:
            return {"error": "not cached, --no-fetch"}
        self.net_calls += 1
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
            if cert_failure(e):
                raise SystemExit(CERT_HELP.format(host="api.semanticscholar.org"))
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


FINGERPRINT_FIELDS = ("itemType", "title", "date", "dateAdded", "DOI", "archiveID", "url",
                      "extra", "abstractNote")


def item_fingerprint(d):
    """A short hash of the fields of a Zotero item's data that a build reads.

    app.py compares it with the library to say what has changed since a map was
    built, and the comparison has to hold across sources: the Zotero app's local API
    and zotero.org number versions differently, but serve the same field values. So
    no version or dateModified goes in, only what resolve_identity reads - the
    fields above, the first three creators' names, the tags and the collections,
    those two sorted because their order is not part of the item. An edit the map
    cannot show, a note's text or a URL's access date, changes nothing here.
    """
    sig = {f: d.get(f) or "" for f in FINGERPRINT_FIELDS}
    sig["creators"] = [c.get("lastName") or c.get("name") or "" for c in d.get("creators", [])][:3]
    sig["tags"] = sorted(t["tag"] for t in d.get("tags", []))
    sig["collections"] = sorted(d.get("collections", []))
    return hashlib.sha1(json.dumps(sig, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def pull(fetch):
    """The library, minus notes, attachments and anything in the trash.

    Also returns the highest item version in the pull. It is the high-water mark the
    map was built from: app.py takes the map's nodes as that source's library as of
    it, and asks only for items?since=<it>. Since it comes from the pull itself it stays right for a
    --no-fetch build of an older recording. Taken over the raw rows, trash and notes
    included, because a change to any of them is a change this build has seen.

    And returns the source the items came from, "local" or "web", because a version
    can only be compared with versions from the same source; app.py asks that one.
    """
    fetch.progress(p="stage", stage="pull")
    raw = fetch.zotero_all("items", limit=100, itemType="-attachment")
    source = fetch.source      # read before the next call, which may fall back to the web
    items = [i["data"] for i in raw
             if i["data"]["itemType"] not in ("note", "attachment")
             and not i["data"].get("deleted")]
    colls = {c["data"]["key"]: c["data"]["name"] for c in fetch.zotero_all("collections", limit=50)}
    print(f"pulled {len(items)} items, {len(colls)} collections")
    return items, colls, max((i.get("version") or 0 for i in raw), default=0), source


def resolve_identity(fetch, items, colls, AL):
    """One node per item, with its OpenAlex identity resolved and its facets read off its tags.

    Iterates `items` in the order Zotero returned them, never sorted: that order
    sets the order of the OpenAlex calls, and so the order of the failure lines in
    the build summary.
    """
    nodes, oa_by_key = {}, {}
    dois = [d for d in (norm_doi(it.get("DOI")) for it in items) if d]
    fetch.progress(p="stage", stage="openalex", total=len(dois),
                   uncached=sum(1 for d in dois if not os.path.exists(oa_cache_path(d))))
    done = 0
    for it in items:
        k = it["key"]
        doi = norm_doi(it.get("DOI"))
        ids, cited_by, oa_year, err = [], None, None, None
        if doi:
            before = fetch.net_calls
            w = fetch.openalex_by_doi(doi)
            done += 1
            fetch.progress(p="tick", stage="openalex", done=done, net=fetch.net_calls > before)
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
            "zfp": item_fingerprint(it),
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
    want = [n["doi"] for k, n in nodes.items()
            if n["doi"] and not oa_by_key.get(k, {}).get("referenced_works")]
    fetch.progress(p="stage", stage="s2", total=len(want),
                   uncached=sum(1 for d in want if not os.path.exists(s2_cache_path(d))))
    done = 0
    for k, n in nodes.items():
        w = oa_by_key.get(k, {})
        r = w.get("referenced_works") or []
        refs[k] = set(r)
        doi_refs[k] = set()
        arxiv_refs[k] = set()
        if not r and n["doi"]:
            before = fetch.net_calls
            d = fetch.s2_refs(n["doi"])
            done += 1
            fetch.progress(p="tick", stage="s2", done=done, net=fetch.net_calls > before)
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
    # aliases.json is per-library data keyed by Zotero item keys, so an edge can name an
    # item this library does not hold - one since deleted, or a copy of the file from
    # someone else's checkout. Skipped and counted, never a KeyError further down.
    foreign = 0
    for src, dst in AL["manual_edges"]["edges"]:
        if src in nodes and dst in nodes:
            add(src, dst, "manual")
        else:
            foreign += 1
    if foreign:
        print(f"WARNING: {foreign} manual edge(s) in aliases.json name items not in this "
              "library - skipped. Remove them if the file came from another library.")

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


def emit(nodes, edges, tag_edges, threshold, tag_min, library_version, library_source):
    """Write out/graph.json and summarise the run."""
    graph = {
        "generated": time.strftime("%Y-%m-%d"),
        # provenance, not a computed value: the pull this graph was built from
        "library_version": library_version,
        "library_source": library_source,
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
    with open(p, "w", encoding="utf-8", newline="\n") as fh:   # LF on Windows too
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
    ap.add_argument("--progress", action="store_true",
                    help="also write JSON progress lines to stderr, for app.py")
    args = ap.parse_args()
    stdout_never_fails()
    progress = stderr_progress if args.progress else no_progress

    for d in (CACHE_OA, CACHE_S2, CACHE_ZOTERO, OUT):
        os.makedirs(d, exist_ok=True)

    if not MAILTO and not args.no_fetch:
        print("WARNING: ZOTERO_MAP_MAILTO unset - OpenAlex and Semantic Scholar calls go "
              "to the common pool, which is slower and rate-limited more aggressively.")
        # in the shell syntax of the platform the run is on; app.py's setup page
        # takes the address too, and passes it on
        if sys.platform == "win32":
            print('   $env:ZOTERO_MAP_MAILTO = "you@example.com"   (PowerShell) to join '
                  "the polite pool")
        else:
            print("   export ZOTERO_MAP_MAILTO=you@example.com   to join the polite pool")

    progress(p="stage", stage="connect")
    fetch = Fetcher.connect(args.no_fetch, progress)

    with open(os.path.join(HERE, "aliases.json"), encoding="utf-8") as fh:
        AL = json.load(fh)

    items, colls, library_version, library_source = pull(fetch)
    nodes, oa_by_key = resolve_identity(fetch, items, colls, AL)
    refs, doi_refs, arxiv_refs, fallbacks, missing = fetch_references(fetch, nodes, oa_by_key)
    report_fetch(fetch, refs, fallbacks, missing)
    progress(p="stage", stage="edges")
    edges, indeg, outdeg = build_edges(nodes, refs, doi_refs, arxiv_refs, AL)
    threshold = classify(nodes, indeg, outdeg)
    tag_edges, tag_min = tag_affinity(nodes, edges)
    emit(nodes, edges, tag_edges, threshold, tag_min, library_version, library_source)


if __name__ == "__main__":
    main()
