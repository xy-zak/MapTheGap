#!/usr/bin/env python3
"""MapTheGap as a local app: setup, the map, and a button that rebuilds it.

    python3 app.py [--port N] [--no-browser]

or double-click the launcher for the platform: MapTheGap_Mac.command,
MapTheGap_Windows.bat or MapTheGap_Linux.sh. Starting it while it is already running
just opens the running app again.

Serves on 127.0.0.1 only. The first visit walks through linking a Zotero Web API
key; after that `/` is out/map.html exactly as render.py wrote it, with one strip
appended at serve time - whether the library is being read from the Zotero app on
this computer or from zotero.org, what has changed in it since the map was built, and
an update button with progress and a time estimate.

The build itself is unchanged: build.py --progress, then render.py, as subprocesses.
A subprocess rather than an import because build.py ends a run with SystemExit on
any error, which must not take the server with it, and because cancel is then a
kill. Their stdout is the same transcript a terminal run prints, kept as the log.

Standard library only, like the rest of the repo, and the same on macOS, Windows
and Linux. The key is written to one file and sent only to zotero.org: it is never
echoed to the browser and never logged.
"""

import argparse
import collections
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import webbrowser

import build   # KEY_FILE, the Zotero transport, the cache layout and its atomic writer

HERE = build.HERE
TEMPLATES = os.path.join(HERE, "templates")
GRAPH = os.path.join(build.OUT, "graph.json")
MAP = os.path.join(build.OUT, "map.html")
TIMINGS = os.path.join(HERE, "cache", "app", "timings.json")
# Beside the key, outside the repo: who the key belongs to, and the optional contact
# address for the polite pool. No secret in it, but it is per-user, like the key.
SETTINGS = os.path.join(os.path.dirname(build.KEY_FILE), "mapthegap.json")

STATIC = {
    "/app/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app/map.css": ("map.css", "text/css; charset=utf-8"),
    "/setup": ("setup.html", "text/html; charset=utf-8"),
}
INJECT = '\n<link rel="stylesheet" href="/app/app.css">\n<script src="/app/app.js"></script>\n'


# ---------------------------------------------------------------- small files

def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write_private(path, text):
    """Write a file only its owner can read, through a temp file so a crash leaves no half-key.

    Mode 600 on macOS and Linux. Windows ignores all but the read-only bit of a mode;
    there the file is private because it sits in the user's own profile folder, whose
    permissions already exclude other accounts.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)          # O_CREAT's mode does not apply to an existing .tmp
    os.replace(tmp, path)


def settings():
    return _read_json(SETTINGS, {}) or {}


def save_settings(**changes):
    s = settings()
    s.update(changes)
    _write_private(SETTINGS, json.dumps(s, indent=1))


_graph_cache = {"mtime": None, "graph": None}


def graph():
    """out/graph.json, re-read only when it changes on disk."""
    try:
        mtime = os.path.getmtime(GRAPH)
    except OSError:
        return None
    if mtime != _graph_cache["mtime"]:
        _graph_cache.update(mtime=mtime, graph=_read_json(GRAPH))
    return _graph_cache["graph"]


def map_info():
    """Where the map on screen was read from, and when it was built, for the strip."""
    g = graph()
    if g is None:
        return None
    t = time.localtime(_graph_cache["mtime"])
    # the day without a leading zero, which strftime spells differently on Windows
    return {"source": g.get("library_source", "web"),
            "built": f"{t.tm_mday} {time.strftime('%b %H:%M', t)}"}


# ---------------------------------------------------------------- Zotero

class ZoteroError(Exception):
    pass


def zotero_get(path, params=None, headers=None, key=None):
    """GET from the Zotero Web API. Returns (status, headers, body text).

    With `key`, that key is used instead of the saved one - setup checks a key before
    writing it. A failed connection becomes a ZoteroError the page can show.
    """
    try:
        status, hdrs, body = build.zotero_http(path, params, key=key, headers=headers,
                                               timeout=20)
    except (urllib.error.URLError, OSError) as e:
        if build.cert_failure(e):
            raise ZoteroError(build.CERT_HELP.format(host="api.zotero.org"))
        raise ZoteroError("couldn't reach api.zotero.org - check the connection")
    except SystemExit as e:        # build.zotero_key: no key file, or no key in it
        raise ZoteroError(str(e))
    return status, hdrs, body.decode("utf-8", "replace")


def zotero_local_get(path, params=None, headers=None):
    """GET from the Zotero app's local API. Returns (status, headers, body text).

    Same shape as zotero_get, and no key is sent. A failed connection, or anything
    but Zotero answering, becomes a ZoteroError the page can show.
    """
    try:
        status, hdrs, body = build.zotero_local_http(path, params, headers=headers,
                                                     timeout=20)
    except (urllib.error.URLError, OSError):
        status = 0
    if status == 0:
        raise ZoteroError("Zotero on this computer isn't answering through its local API")
    return status, hdrs, body.decode("utf-8", "replace")


def identify(key=None):
    """Who a key belongs to, as {user_id, username, library}. Never returns the key.

    /keys/current echoes the key back in plaintext, so only the three fields below
    are lifted out of the response and the rest is dropped on the spot.
    """
    status, _, body = zotero_get("keys/current", key=key)
    if status in (403, 404):
        raise ZoteroError("Zotero rejected that key - check that it was copied whole")
    if status != 200:
        raise ZoteroError(f"Zotero answered {status} - try again in a moment")
    d = json.loads(body)
    return {"user_id": d.get("userID"), "username": d.get("username") or "",
            "library": bool(((d.get("access") or {}).get("user") or {}).get("library"))}


def zotero_running():
    """Whether the Zotero desktop app is running, from the system's process list.

    This, not the connector ping below, is the main test. The ping only answers while
    Zotero's local server is up, and Zotero runs without one whenever it starts to
    find its port taken - silently, so the app looked closed while it was in use.
    Returns None when the process list can't be read, so the ping decides.
    """
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                                 timeout=5, creationflags=subprocess.CREATE_NO_WINDOW).stdout
            # bytes, decoded as latin-1: tasklist writes the console code page, and a
            # strict decode of someone else's process name must not break the check
            names = {line.split(",")[0].strip('"').lower()
                     for line in out.decode("latin-1").splitlines() if line}
            return "zotero.exe" in names
        # comm is the bare executable: "zotero" on macOS (with its path) and in the
        # Linux launcher script, "zotero-bin" for the Linux binary itself
        out = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, timeout=5).stdout
        return any(os.path.basename(line.strip()).lower() in ("zotero", "zotero-bin")
                   for line in out.decode("latin-1").splitlines())
    except (OSError, subprocess.SubprocessError):
        return None


def zotero_ping():
    """Whether Zotero's connector server answers. Needs no Zotero setting turned on."""
    try:
        build.LOCAL_OPENER.open(f"http://127.0.0.1:{build.zotero_port()}/connector/ping",
                                timeout=0.5).close()
        return True
    except urllib.error.HTTPError:
        return True                # something answered on Zotero's port
    except (urllib.error.URLError, OSError):
        return False


def zotero_open():
    """Checked on every status request, so opening or closing Zotero shows within one poll."""
    return zotero_running() or zotero_ping()


def reading_from(is_open):
    """Where the library is read from right now, "local" or "web", and why when not local.

    The same choice build.Fetcher.connect makes, so the change count and the next
    update read the same place. Asked on every status request, so opening or closing
    Zotero moves the strip within one poll.
    """
    if not is_open:
        return {"source": "web", "why": None}
    uid = settings().get("user_id") or _read_json(
        os.path.join(build.CACHE_ZOTERO, "user_id.json"))
    if not uid:
        return {"source": "web", "why": "no Zotero user id is recorded yet"}
    problem = build.zotero_local_problem(uid, timeout=2)
    if not problem:
        return {"source": "local", "why": None}
    if problem == "Zotero is not running":   # the process is there, its server isn't
        problem = "its local server isn't answering - it may still be starting"
    return {"source": "web", "why": problem}


class Changes:
    """What has changed in the library since the current map was built.

    Asked of whichever source the library can be read from now - the Zotero app's
    local API while Zotero is open and serving it, zotero.org otherwise - whichever
    the map itself was read from. Each source has its own copy of the library here,
    {key: (fingerprint, title)} as of a version, brought up to date with
    items?since=<that version> at most once a minute, in the background. A copy is
    compared with the map's nodes item by item, by build.item_fingerprint, so the
    answer holds across sources: a version from one cannot be asked about at the
    other, but the fields both serve are the same.

    The copy of the source the map was built from starts as the map's own nodes, at
    the map's library_version, so asking it costs what it always did. The other
    source's copy is read in full the first time it is asked, and from then on only
    what has changed. Comparing items rather than versions is also what keeps an edit
    the map has not seen from being missed: an edit made on zotero.org that the
    Zotero app had not synced yet when the map was built from it, or an app edit not
    yet synced when it was built from zotero.org, still differs from the map's node.

    From the local API an edit counts at once, synced or not. From zotero.org, an
    edit made in the Zotero app counts once Zotero has synced it; one made on
    zotero.org, on another computer or by the Claude skills counts at once.
    """

    INTERVAL = 60

    def __init__(self):
        self.lock = threading.Lock()
        self.busy = False
        self.copies = {}           # (user_id, source) -> {"version", "items": {key: (fp, title)}}
        self.results = {}          # source -> (graph mtime, time checked, result)
        self.latest = None         # the source of the last result handed out

    def snapshot(self, source):
        g = graph()
        s = settings()
        if g is None or g.get("library_version") is None or any(
                "zfp" not in n for n in g["nodes"]):
            return {"state": "untracked"}
        if s.get("built_for") and s.get("user_id") and s["built_for"] != s["user_id"]:
            return {"state": "untracked"}
        gid = _graph_cache["mtime"]
        with self.lock:
            r = self.results.get(source)
            stale = r is None or r[0] != gid or time.time() - r[1] > self.INTERVAL
            if stale and not self.busy:
                self.busy = True
                threading.Thread(target=self._check, args=(source, g, gid), daemon=True).start()
            if r and r[0] == gid:
                self.latest = source
                return dict(r[2])
        return {"state": "pending", "source": source}

    def current(self):
        """The result last handed out, for the update's time estimate."""
        with self.lock:
            r = self.results.get(self.latest)
            return r[2] if r and r[0] == _graph_cache["mtime"] else {}

    def _check(self, source, g, gid):
        try:
            uid = settings().get("user_id") or _read_json(
                os.path.join(build.CACHE_ZOTERO, "user_id.json"))
            if not uid:
                raise ZoteroError("no Zotero user id recorded - link Zotero again")
            result = self._diff(self._copy(uid, source, g), g, source)
        except (ZoteroError, ValueError, KeyError) as e:
            result = {"state": "error", "error": str(e), "source": source}
        with self.lock:
            self.results[source] = (gid, time.time(), result)
            self.busy = False

    def _copy(self, uid, source, g):
        """This source's copy of the library, brought up to date."""
        c = self.copies.get((uid, source))
        version = g["library_version"]
        if g.get("library_source", "web") == source and (c is None or c["version"] < version):
            c = {"version": version,
                 "items": {n["key"]: (n["zfp"], n["title"]) for n in g["nodes"]}}
        elif c is None:
            c = {"version": 0, "items": {}}
        self._advance(uid, source, c)
        self.copies[(uid, source)] = c
        return c

    def _advance(self, uid, source, c):
        local = source == "local"
        get = zotero_local_get if local else zotero_get
        where = "Zotero on this computer" if local else "zotero.org"
        hdr = {"If-Modified-Since-Version": str(c["version"])} if c["version"] else None
        # Top-level items only: a regular item is never a child, and the child notes
        # and attachments it would otherwise list are never nodes.
        params = {"format": "versions", "itemType": "-attachment", "includeTrashed": 1}
        if local:
            # The local API has no /deleted, so ask for every key's version, the trash
            # included: a key missing from the answer was deleted outright.
            status, h, body = get(f"users/{uid}/items/top", params, hdr)
        else:
            status, h, body = get(f"users/{uid}/items/top", dict(params, since=c["version"]), hdr)
        if status == 304:
            return
        if status != 200:
            raise ZoteroError(f"{where} answered {status}")
        versions = json.loads(body)
        if local:
            changed = [k for k, v in versions.items() if v > c["version"]]
            gone = [k for k in c["items"] if k not in versions]
        else:
            changed = list(versions)
            gone = []
            if c["version"]:
                status, _, body = get(f"users/{uid}/deleted", {"since": c["version"]})
                if status != 200:
                    raise ZoteroError(f"{where} answered {status}")
                gone = json.loads(body).get("items", [])
        items = c["items"]
        keys = sorted(changed)
        for i in range(0, len(keys), 50):
            # includeTrashed, so that an item moved to the trash comes back marked deleted
            status, _, body = get(f"users/{uid}/items", {
                "itemKey": ",".join(keys[i:i + 50]), "format": "json", "limit": 50,
                "includeTrashed": 1})
            if status != 200:
                raise ZoteroError(f"{where} answered {status}")
            for it in json.loads(body):
                d = it["data"]
                if d["itemType"] in ("note", "attachment") or d.get("deleted"):
                    items.pop(d["key"], None)
                else:
                    items[d["key"]] = (build.item_fingerprint(d), d.get("title") or "(untitled)")
        for k in gone:
            items.pop(k, None)
        c["version"] = int(h.get("last-modified-version") or 0) or max(
            versions.values(), default=c["version"])

    @staticmethod
    def _diff(c, g, source):
        nodes = {n["key"]: n for n in g["nodes"]}
        items = c["items"]
        added, edited, removed = [], [], []
        for k, (fp, title) in items.items():
            if k not in nodes:
                added.append({"key": k, "title": title})
            elif nodes[k]["zfp"] != fp:
                edited.append({"key": k, "title": title})
        for k, n in nodes.items():
            if k not in items:
                removed.append({"key": k, "title": n["title"]})
        for rows in (added, edited, removed):
            rows.sort(key=lambda r: r["title"].lower())
        return {"state": "ok", "added": added, "edited": edited, "removed": removed,
                "count": len(added) + len(edited) + len(removed),
                "checked": time.strftime("%H:%M"), "source": source}


# ---------------------------------------------------------------- the build

STAGES = ("connect", "pull", "openalex", "s2", "edges", "render")
LABELS = {"connect": "connecting to zotero", "pull": "pulling the library",
          "openalex": "resolving works · openalex",
          "s2": "reference lists · semantic scholar",
          "edges": "building the graph", "render": "rendering the map"}
# Starting costs, in seconds, until a finished run has measured this machine. The s2
# rate is set by the fixed time.sleep(5) in build.Fetcher.s2_refs plus the request.
DEFAULTS = {"connect": 0.8, "pull": 3.0, "edges": 0.6, "render": 1.5,
            "openalex_net": 0.6, "s2_net": 5.4, "cached": 0.004,
            "s2_share": 0.18, "s2_persist": 0}
PRIOR_WEIGHT = 3   # how many observed calls it takes for the live rate to outvote the prior


class Run:
    """One build-and-render, its progress, and the estimate of what is left."""

    def __init__(self, expect_new):
        self.state = "running"
        self.started = time.time()
        self.finished = None
        self.error = None
        self.stages = {}
        self.current = None
        self.log = collections.deque(maxlen=3000)
        self.proc = None
        self.cancelled = False
        self.expect_new = expect_new
        self.T = dict(DEFAULTS, **(_read_json(TIMINGS, {}) or {}))

    # -- events

    def open_stage(self, name, total=None, uncached=None, now=None):
        now = now or time.time()
        if self.current and self.current in self.stages:
            self.stages[self.current]["t1"] = now
        self.current = name
        self.stages[name] = {"t0": now, "t1": None, "total": total, "uncached": uncached,
                             "done": 0, "net_done": 0, "net_time": 0.0, "last": now}

    def tick(self, name, done, net, now=None):
        now = now or time.time()
        st = self.stages.get(name)
        if not st:
            return
        dt = now - st["last"]
        st["done"], st["last"] = done, now
        if net:
            st["net_done"] += 1
            st["net_time"] += dt

    def close(self, now=None):
        if self.current in self.stages:
            self.stages[self.current]["t1"] = now or time.time()

    # -- estimate

    def _rate(self, name):
        st, prior = self.stages.get(name), self.T[name + "_net"]
        if not st:
            return prior
        return (prior * PRIOR_WEIGHT + st["net_time"]) / (PRIOR_WEIGHT + st["net_done"])

    def remaining(self, now):
        T, left = self.T, 0.0
        oa = self.stages.get("openalex")
        oa_net = oa["uncached"] if oa else self.expect_new
        for name in STAGES:
            st = self.stages.get(name)
            if st and st["t1"]:
                continue
            if name in ("openalex", "s2"):
                rate = self._rate(name)
                if st:
                    net_left = max(0, (st["uncached"] or 0) - st["net_done"])
                    cached_left = max(0, (st["total"] or 0) - st["done"] - net_left)
                    rem = net_left * rate + cached_left * T["cached"]
                    if net_left:            # the call in flight is already partly paid
                        rem -= min(now - st["last"], rate * 0.95)
                elif name == "openalex":
                    rem = self.expect_new * rate
                else:
                    rem = (T["s2_persist"] + oa_net * T["s2_share"]) * rate
            else:
                rem = T[name] - (now - st["t0"] if st else 0)
            left += max(0.0, rem)
        return left

    def learn(self):
        """Fold this run's measurements into the starting costs for the next one."""
        T = {k: self.T[k] for k in DEFAULTS}
        for name in ("connect", "pull", "edges", "render"):
            st = self.stages.get(name)
            if st and st["t1"]:
                T[name] = round(st["t1"] - st["t0"], 3)
        oa, s2 = self.stages.get("openalex"), self.stages.get("s2")
        for name, st in (("openalex", oa), ("s2", s2)):
            if st and st["net_done"]:
                T[name + "_net"] = round(st["net_time"] / st["net_done"], 3)
        if oa and s2 and oa["total"]:
            T["s2_share"] = round(s2["total"] / oa["total"], 3)
            # Semantic Scholar failures are not cached, so they come back next run
            T["s2_persist"] = max(0, (s2["uncached"] or 0)
                                  - round((oa["uncached"] or 0) * T["s2_share"]))
        os.makedirs(os.path.dirname(TIMINGS), exist_ok=True)
        build._cache_write(TIMINGS, T)

    def snapshot(self, with_log=False):
        now = self.finished or time.time()
        elapsed = now - self.started
        left = self.remaining(now) if self.state == "running" else 0.0
        st = self.stages.get(self.current) or {}
        snap = {"state": self.state, "stage": self.current,
                "label": LABELS.get(self.current, "starting"),
                "done": st.get("done"), "total": st.get("total"),
                "elapsed": round(elapsed, 1), "eta": round(left, 1),
                "fraction": round(elapsed / (elapsed + left), 4) if elapsed + left else 0,
                "error": self.error, "finished": self.finished}
        if with_log:
            snap["log"] = "\n".join(self.log)
        return snap


class Runner:
    def __init__(self):
        self.lock = threading.Lock()
        self.run = None

    def start(self, expect_new):
        with self.lock:
            if self.run and self.run.state == "running":
                return False
            self.run = Run(expect_new)
            threading.Thread(target=self._go, args=(self.run,), daemon=True).start()
            return True

    def cancel(self):
        with self.lock:
            run = self.run
        if run and run.state == "running":
            run.cancelled = True
            if run.proc:
                run.proc.terminate()

    def snapshot(self, with_log=False):
        with self.lock:
            run = self.run
        return run.snapshot(with_log) if run else {"state": "idle"}

    def _env(self):
        # unbuffered so the log keeps up; UTF-8 because a pipe on Windows otherwise
        # gets the locale's code page, which cannot carry every author's name
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        mailto = settings().get("mailto")
        if mailto and not env.get("ZOTERO_MAP_MAILTO"):
            env["ZOTERO_MAP_MAILTO"] = mailto
        return env

    def _step(self, run, argv, progress):
        """Run one script; stdout to the log, --progress lines to the run. True on success."""
        run.proc = p = subprocess.Popen([sys.executable] + argv, cwd=HERE, env=self._env(),
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        encoding="utf-8", errors="replace", bufsize=1)
        errors = []

        def read_err():
            for line in p.stderr:
                line = line.rstrip("\n")
                ev = None
                if progress and line.startswith('{"p"'):
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        pass
                if ev is None:
                    errors.append(line)
                    run.log.append(line)
                elif ev["p"] == "stage":
                    run.open_stage(ev["stage"], ev.get("total"), ev.get("uncached"))
                elif ev["p"] == "tick":
                    run.tick(ev["stage"], ev["done"], ev["net"])

        t = threading.Thread(target=read_err, daemon=True)
        t.start()
        for line in p.stdout:
            run.log.append(line.rstrip("\n"))
        p.wait()
        t.join()
        if p.returncode != 0 and not run.cancelled:
            # build.py's SystemExit messages are written as the last stderr line
            run.error = next((e for e in reversed(errors) if e.strip()),
                             f"{argv[0]} exited with status {p.returncode}")
        return p.returncode == 0

    def _go(self, run):
        try:
            ok = self._step(run, ["build.py", "--progress"], True)
            if ok and not run.cancelled:
                run.open_stage("render")
                ok = self._step(run, ["render.py"], False)
            run.close()
            if run.cancelled:
                run.state = "cancelled"
            elif ok:
                run.state = "done"
                run.learn()
                uid = settings().get("user_id")
                if uid:
                    save_settings(built_for=uid)
            else:
                run.state = "failed"
        except Exception as e:     # a crashed runner must still end the run
            run.error, run.state = f"{type(e).__name__}: {e}", "failed"
        run.finished = time.time()


# ---------------------------------------------------------------- HTTP

CHANGES = Changes()
RUNNER = Runner()
KEY_RE = re.compile(r"^[A-Za-z0-9]{8,64}$")
MAIL_RE = re.compile(r"^[^@\s\"\\]+@[^@\s\"\\]+\.[^@\s\"\\]+$")


def linked():
    return os.path.exists(build.KEY_FILE)


def setup_state():
    s = settings()
    if linked() and not s.get("username"):
        # a key written by hand before this app existed: learn whose it is, once
        try:
            who = identify()
            save_settings(user_id=who["user_id"], username=who["username"])
            s = settings()
        except (ZoteroError, ValueError):
            pass
    return {"linked": linked(), "username": s.get("username"), "user_id": s.get("user_id"),
            "mailto": s.get("mailto") or os.environ.get("ZOTERO_MAP_MAILTO", ""),
            "conf": build.KEY_FILE.replace(os.path.expanduser("~"), "~", 1),
            "has_map": os.path.exists(MAP),
            "map_matches": not s.get("built_for") or s.get("built_for") == s.get("user_id")}


def do_setup(body):
    key = (body.get("key") or "").strip()
    mailto = (body.get("mailto") or "").strip()
    if not key and linked():
        key = None                 # keep the saved key, only update the address
    elif not KEY_RE.match(key):
        raise ZoteroError("that doesn't look like a Zotero key - it is a run of letters "
                          "and digits, 24 long")
    if mailto and not MAIL_RE.match(mailto):
        raise ZoteroError("that contact address doesn't look like an email address")
    who = identify(key)
    if not who["library"]:
        raise ZoteroError("this key can't read your library - edit it at "
                          "zotero.org/settings/keys and tick 'Allow library access'")
    status, h, _ = zotero_get(f"users/{who['user_id']}/items/top", {"limit": 1, "format": "keys"},
                              key=key)
    count = int(h.get("total-results", 0)) if status == 200 else None
    if key:
        # curl's config-file format, so the zotero-library skill's curl commands share it
        _write_private(build.KEY_FILE, f'header = "Zotero-API-Key: {key}"\n')
        os.makedirs(build.CACHE_ZOTERO, exist_ok=True)
        build._cache_write(os.path.join(build.CACHE_ZOTERO, "user_id.json"), who["user_id"])
    save_settings(user_id=who["user_id"], username=who["username"], mailto=mailto)
    return {"ok": True, "username": who["username"], "user_id": who["user_id"],
            "items": count, **{k: v for k, v in setup_state().items()
                               if k in ("has_map", "map_matches")}}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "MapTheGap"

    def log_message(self, fmt, *args):
        pass                       # the terminal stays quiet; failures are reported in-page

    # -- guards

    def _allowed_hosts(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _host_ok(self):
        # A page elsewhere can point its own hostname at 127.0.0.1 (DNS rebinding);
        # checking Host stops it reading /api/status, which names library items.
        return self.headers.get("Host") in self._allowed_hosts()

    def _origin_ok(self):
        o = self.headers.get("Origin") or ""
        return o in {"http://" + h for h in self._allowed_hosts()}

    # -- responses

    def _send(self, status, body, ctype="application/json", extra=()):
        data = body if isinstance(body, bytes) else (
            json.dumps(body) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, where):
        self._send(302, b"", "text/plain", [("Location", where)])

    def _file(self, name, ctype):
        with open(os.path.join(TEMPLATES, name), "rb") as fh:
            self._send(200, fh.read(), ctype)

    # -- routes

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "bad host"})
        path = urllib.parse.urlsplit(self.path).path
        if path == "/":
            if not linked() or not os.path.exists(MAP):
                return self._redirect("/setup")
            with open(MAP, encoding="utf-8") as fh:
                return self._send(200, fh.read() + INJECT, "text/html; charset=utf-8")
        if path in STATIC:
            return self._file(*STATIC[path])
        if path == "/api/setup":
            return self._send(200, setup_state())
        if path == "/api/status":
            is_open = zotero_open()
            reading = reading_from(is_open)
            return self._send(200, {"linked": linked(), "zotero_open": is_open,
                                    "reading": reading, "map": map_info(),
                                    "changes": CHANGES.snapshot(reading["source"]),
                                    "run": RUNNER.snapshot()})
        if path == "/api/update":
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            return self._send(200, RUNNER.snapshot(with_log="log" in q))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok() or not self._origin_ok():
            return self._send(403, {"error": "requests are only accepted from this app"})
        path = urllib.parse.urlsplit(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n < 10000 else {}
        except ValueError:
            return self._send(400, {"error": "bad request body"})
        if path == "/api/setup":
            try:
                return self._send(200, do_setup(body))
            except (ZoteroError, ValueError) as e:
                return self._send(400, {"error": str(e)})
        if path == "/api/update":
            if not linked():
                return self._send(400, {"error": "link Zotero first"})
            added = len(CHANGES.current().get("added") or [])
            if not RUNNER.start(expect_new=added):
                return self._send(409, {"error": "a build is already running"})
            return self._send(200, RUNNER.snapshot())
        if path == "/api/update/cancel":
            RUNNER.cancel()
            return self._send(200, RUNNER.snapshot())
        if path == "/api/quit":
            # A launcher double-clicked on Linux can run with no terminal window, which
            # leaves the page as the only place to stop the server from.
            RUNNER.cancel()
            self._send(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._send(404, {"error": "not found"})


class Server(http.server.ThreadingHTTPServer):
    # SO_REUSEADDR means "rebind after a restart" on macOS and Linux, but on Windows it
    # lets a second process bind a port that is already taken, so a second app.py
    # would start silently and the two would split the requests between them.
    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True


DEFAULT_PORT = 8765
PORT_TRIES = 10    # without --port, how far past the default to look for a free port


def already_running(port):
    """True when what answers on this port is MapTheGap itself, not just anything."""
    try:
        with build.LOCAL_OPENER.open(f"http://127.0.0.1:{port}/api/setup", timeout=1) as r:
            return r.headers.get("Server", "").startswith(Handler.server_version)
    except (urllib.error.URLError, OSError):
        return False


def main():
    ap = argparse.ArgumentParser(description="Run MapTheGap as a local app.")
    ap.add_argument("--port", type=int,
                    help=f"port to serve on (default: {DEFAULT_PORT}, or the next free one)")
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = ap.parse_args()
    build.stdout_never_fails()

    # Double-clicking the launcher a second time should bring the app back, not fail
    # on a busy port - so a port that answers as MapTheGap is reused, and one taken by
    # anything else is skipped.
    srv, err = None, None
    for port in [args.port] if args.port else range(DEFAULT_PORT, DEFAULT_PORT + PORT_TRIES):
        url = f"http://127.0.0.1:{port}/"
        if already_running(port):
            print(f"MapTheGap is already running at {url} - opening it.")
            if not args.no_browser:
                webbrowser.open(url)
            return
        try:
            srv = Server(("127.0.0.1", port), Handler)
            break
        except OSError as e:
            err = e
    if srv is None:
        tried = args.port or f"{DEFAULT_PORT}-{DEFAULT_PORT + PORT_TRIES - 1}"
        raise SystemExit(f"Can't listen on 127.0.0.1:{tried} ({err.strerror}). "
                         "Pick a free port with --port.")

    print(f"MapTheGap is running at {url}")
    print("Leave this window open while you use it. To stop it, close this window, "
          "press Ctrl-C, or press [quit] in the app.")
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        RUNNER.cancel()
    srv.server_close()
    print("\nMapTheGap has stopped.")


if __name__ == "__main__":
    main()
