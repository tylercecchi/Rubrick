"""`rubrick ui` — the local app for reviewing and toggling product systems.

A small standard-library HTTP server (no extra dependencies): it serves one page and a JSON API
that calls the engine directly. Everything it reads and writes is the same local data the CLI
and MCP server use — systems/*.json, learned.json, runs/ — so git stays the record of change.
Compiles and checks run in background threads; the page polls their progress.

Data home: $RUBRICK_HOME or the current directory (see rubrick.paths).
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import threading
import time
import traceback
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from rubrick import learned, paths

_INDEX = pathlib.Path(__file__).with_name("index.html")
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


# ---- products & targets ---------------------------------------------------------------

def _targets_file() -> pathlib.Path:
    return paths.systems_dir() / "targets.json"


def _targets() -> dict:
    f = _targets_file()
    return json.loads(f.read_text()) if f.exists() else {}


def _save_target(name: str, repo: str, gcss: str, comps: str) -> None:
    t = _targets()
    t[name] = {"repo": repo, "globals_css": gcss, "components_dir": comps}
    _targets_file().write_text(json.dumps(t, indent=2))



def pick_folder(prompt: str = "Choose the product's folder") -> str | None:
    """Open the OS's own folder picker and return the chosen absolute path (None when the
    person cancels). A browser page can't learn a real folder path, so the local server
    asks the OS — macOS through AppleScript, elsewhere through Tk when it's available."""
    import platform
    import subprocess
    if platform.system() == "Darwin":
        safe = prompt.replace('"', "'")
        r = subprocess.run(["osascript", "-e",
                            f'POSIX path of (choose folder with prompt "{safe}")'],
                           capture_output=True, text=True, timeout=600)
        return (r.stdout.strip().rstrip("/") or None) if r.returncode == 0 else None
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        raise RuntimeError("no folder picker on this system — type the path instead")
    root = tkinter.Tk(); root.withdraw(); root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(title=prompt) or None
    finally:
        root.destroy()


def _layout(repo: str, b: dict) -> tuple[str, str]:
    """The stylesheet and components folder for a repo: what the person typed, else detected."""
    from rubrick.discover import detect_layout
    d = detect_layout(repo)
    return (b.get("globals_css") or d["globals_css"], b.get("components_dir") or d["components_dir"])


def _review_path(name: str) -> pathlib.Path:
    return paths.systems_dir() / f"{name}.review.json"


def _review(name: str) -> dict:
    f = _review_path(name)
    return json.loads(f.read_text()) if f.exists() else {}


def _target(name: str) -> dict | None:
    t = _targets().get(name) or _review(name).get("calibration_target")
    return t if t and t.get("repo") else None


def _manifest_path(name: str) -> pathlib.Path:
    return paths.systems_dir() / f"{name}.json"


def _names() -> list[str]:
    return sorted(p.stem for p in paths.systems_dir().glob("*.json")
                  if not p.name.endswith(".review.json") and p.name != "targets.json")


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat(timespec="seconds")


def _live(name: str, catalog: list) -> list:
    """The catalog with the product's CURRENT switches applied — the manifest holds the state
    as of the last compile; a switch flipped since then must show immediately."""
    sw = learned.load().get("switches", {}).get(name, {})
    return [{**c, "state": sw[c["key"]]["state"], "set_by": "you"} if c["key"] in sw else c
            for c in catalog]


def _needs_look(c: dict) -> bool:
    return c.get("set_by") == "rubrick" and (c.get("new") or c.get("default") == "off")


def _swatch(m: dict) -> str:
    col = next((s for s in m.get("styles", []) if s["facet"] == "color"), None)
    anchors = (col or {}).get("concrete", {}).get("anchors", [])
    sat = [a for a in anchors if isinstance(a, str) and a.startswith("#") and len(a) == 7
           and max(int(a[i:i + 2], 16) for i in (1, 3, 5)) - min(int(a[i:i + 2], 16) for i in (1, 3, 5)) > 60]
    return sat[0] if sat else "#929292"


def products() -> list[dict]:
    out = []
    for n in _names():
        try:
            m = json.loads(_manifest_path(n).read_text())
        except Exception:
            continue
        mtime = _manifest_path(n).stat().st_mtime
        edited = learned.edited_at(n)
        out.append({"name": n, "swatch": _swatch(m), "compiled_at": _iso(mtime),
                    "needs": sum(1 for c in _live(n, m.get("catalog", [])) if _needs_look(c)),
                    "has_catalog": bool(m.get("catalog")), "can_compile": bool(_target(n)),
                    "pending": bool(edited and edited >= _iso(mtime))})
    return out


# ---- one product, everything the page shows ----------------------------------------------

def _humanize(slug: str) -> str:
    s = slug.replace("-", " ").replace("_", " ").strip()
    return s[:1].upper() + s[1:]


def _describe(key: str, m: dict, review: dict) -> dict:
    """label, description and evidence for one catalog item, from the manifest + review."""
    from rubrick.orchestrate import _move_descriptions
    from rubrick.subtractions import BUILTINS
    head, _, rest = key.partition(":")
    pend = {(p.get("modality"), p.get("name")): p for p in review.get("pending_promotions", [])}
    if head == "new":
        if rest.startswith("behavior:"):
            _, sub, name = rest.split(":", 2)
            mod = f"behavior:{sub}"
        else:
            mod, _, name = rest.partition(":")
        p = pend.get((mod, name), {})
        return {"label": _humanize(name), "desc": p.get("instead") and f"Instead: {p['instead']}" or p.get("evidence", ""),
                "evidence": p.get("evidence", ""), "instead": p.get("instead", ""), "against": p.get("against", ""),
                "confidence": p.get("confidence", ""), "exemplars": p.get("exemplars", []),
                "host": p.get("host", ""), "name": name, "modality": mod,
                "kind": "omission" if mod == "absence" else "new"}
    if head == "absence":
        note = BUILTINS.get(rest, {}).get("note") or next((s["note"] for s in m.get("subtractions", []) if s["omits"] == rest), "")
        return {"label": _humanize(rest), "desc": note, "kind": "omission"}
    if head == "component":
        comp = next((c for c in m.get("components", []) if c["role"] == rest), {})
        return {"label": _humanize(rest), "desc": comp.get("instantiate", ""), "kind": "part"}
    if head == "surface":
        s = next((x for x in m.get("surfaces", []) if x["applies_to"] == rest), {})
        layers = ", ".join(s.get("requires", []))
        return {"label": "Lit focal object", "desc": f"Material layers: {layers}" if layers else "", "kind": "part"}
    if head == "rule":
        r = next((x for x in m.get("rules", []) if x["applies_to"] == rest), {})
        feats = ", ".join(_humanize(f).lower() for f in r.get("requires", []))
        ms = f" · about {r['exit_ms']} ms" if r.get("exit_ms") else ""
        return {"label": f"The ‘{rest}’ interaction", "desc": f"{feats}{ms}", "kind": "part"}
    if key == "composition":
        c = m.get("composition") or {}
        return {"label": _humanize(c.get("archetype", "layout")),
                "desc": f"{_humanize(c.get('composition', ''))}" + (f", anchored on {c['focal_anchor']}" if c.get("focal_anchor") else ""),
                "kind": "part"}
    desc = _move_descriptions(head, [rest]).get(rest, "")
    st = next((s for s in m.get("styles", []) if s["facet"] == head), {})
    prev = (st.get("prevalence") or {}).get(rest)
    if prev is not None:
        desc += (" · " if desc else "") + (f"reserved — about {round(prev * 100)}% of files" if prev <= 0.35
                                          else f"common — about {round(prev * 100)}% of files")
    return {"label": _humanize(rest), "desc": desc, "kind": "move"}


def detail(name: str) -> dict:
    from rubrick.product_system import describe_metrics
    from rubrick.runs import item_result, load_runs
    from rubrick.status import verification
    m = json.loads(_manifest_path(name).read_text())
    review = _review(name)
    runs = load_runs(name)
    latest = runs[0] if runs else None
    items = []
    for c in _live(name, m.get("catalog", [])):
        d = _describe(c["key"], m, review)
        # no review file (or no entry in it): the catalog entry's own description stands
        d = {k: v for k, v in d.items() if v not in ("", [], None) or k not in c}
        if c["key"].startswith("new:") and not d.get("desc"):
            d["desc"] = c.get("evidence", "")
        votes = re.match(r"(\d+)/(\d+) generic twin", c.get("why", "") or "")
        items.append({**c, **d, "needs": _needs_look(c), "verification": verification(c["key"]),
                      "votes": [int(votes.group(1)), int(votes.group(2))] if votes else None,
                      "result": item_result(latest, c["key"]) if latest else None})
    by_facet = {s["because"]: s for s in m.get("styles", [])}
    principles = []
    for p in m.get("principles", []):
        st = by_facet.get(p["id"])
        principles.append({**p, "area": _humanize(st["facet"]) if st else "",
                           "metrics": describe_metrics(st.get("metrics", {})) if st else []})
    target = _target(name)
    overrides = learned.load().get("job_overrides", {})
    rk = str(pathlib.Path(target["repo"]).resolve()) if target else ""
    jobs = [{**j, "override": overrides.get(rk, {}).get(j["original"].strip().lower())}
            for j in (m.get("about") or {}).get("jobs", [])]
    mtime = _manifest_path(name).stat().st_mtime
    edited = learned.edited_at(name)
    return {"name": name, "kind": (m.get("about") or {}).get("kind", ""), "items": items,
            "principles": principles, "jobs": jobs, "compiled_at": _iso(mtime),
            "pending": bool(edited and edited >= _iso(mtime)), "can_compile": bool(target),
            "target": target, "builder": {"checklist": m.get("_checklist", []), "guide": m.get("_guide", {})},
            "runs": [{k: r[k] for k in ("at", "label", "mode", "summary", "candidate")} for r in runs[:10]],
            "swatch": _swatch(m), "specimen": (sp := _specimen(name, m, target)),
            "bento": _bento_summary(name), "drawings": _drawing_summaries(name, items, sp),
            "drawing_queue": _drawing_queue(name)}


def _scene_ref(s: dict, base: str) -> dict:
    return {"id": s["id"], "width": s.get("width"), "height": s.get("height"),
            "rehearsal": s.get("rehearsal"), "plan": s.get("plan", ""),
            "url": f"{base}/{s['id']}.html"}


def _bento_summary(name: str) -> dict | None:
    from urllib.parse import quote
    from rubrick.scenes import load_bento
    doc = load_bento(name)
    if not doc:
        return None
    base = f"/stage/{quote(name)}/bento/-"
    return {"made_at": doc["made_at"], "scenes": [_scene_ref(s, base) for s in doc["scenes"]]}


def _drawing_summaries(name: str, items: list, sp: dict) -> dict:
    """Per item key: its cached drawing (and whether the evidence it was drawn from changed)."""
    from urllib.parse import quote
    from rubrick.scenes import _dir, drawing_fingerprint
    out = {}
    folder = _dir(name) / "drawings"
    if not folder.exists():
        return out
    docs = {}
    for f in folder.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            docs[d["key"]] = d
        except Exception:
            continue
    for i in items:
        d = docs.get(i["key"])
        if d:
            base = f"/stage/{quote(name)}/drawing/{d['ref']}"
            out[i["key"]] = {"made_at": d["made_at"], "stale": d.get("fingerprint") != drawing_fingerprint(i, sp),
                             "scenes": [_scene_ref(s, base) for s in d["scenes"]]}
    return out


def _specimen(name: str, m: dict, target: dict | None) -> dict:
    """The product's real materials for the header bento; font files become app URLs."""
    from urllib.parse import quote
    from rubrick.specimen import specimen
    try:
        sp = specimen(m, *((target["repo"], target["globals_css"], target["components_dir"])
                           if target else ()))
    except Exception as e:  # a display nicety: never let it break the page
        return {"source": "none", "error": str(e)}
    for f in sp.get("fonts", []):
        f["url"] = f"/api/products/{quote(name)}/font?f={quote(f.pop('file'))}"
    return sp


# ---- background jobs: compile and check -------------------------------------------------

def _job(kind: str, fn, tag: str = "") -> str:
    """Run fn in the background. A fn taking one argument gets a `log(status)` callable whose
    latest line the page shows. A running job with the same tag is reused, not duplicated."""
    if tag:
        live = next((j for j in _JOBS.values() if j.get("tag") == tag and j["state"] == "running"), None)
        if live:
            return live["id"]
    jid = uuid.uuid4().hex[:10]
    _JOBS[jid] = {"id": jid, "kind": kind, "tag": tag, "state": "running", "started": time.time(),
                  "result": None, "error": None, "status": ""}

    def log(line) -> None:  # a status line, or {"progress": {"done", "total"}}
        if isinstance(line, dict):
            _JOBS[jid].update(line)
        else:
            _JOBS[jid]["status"] = str(line)[:200]

    def run():
        try:
            _JOBS[jid]["result"] = fn(log) if getattr(fn, "__code__", None) and fn.__code__.co_argcount == 1 else fn()
            _JOBS[jid]["state"] = "done"
        except Exception as e:
            _JOBS[jid]["error"] = f"{type(e).__name__}: {e}"
            _JOBS[jid]["trace"] = traceback.format_exc()[-2000:]
            _JOBS[jid]["state"] = "error"
    threading.Thread(target=run, daemon=True).start()
    return jid


def _compile(name: str, log=None) -> dict:
    from rubrick.orchestrate import compile_product_system
    from rubrick.product_system import save_product_system
    from rubrick.review import emit_review
    t = _target(name)
    if not t:
        raise RuntimeError(f"no source repo recorded for {name!r} — add it with its repo path first")
    with _LOCK:  # one compile at a time: the learned store and caches are shared files
        ps = compile_product_system(t["repo"], t["globals_css"], t["components_dir"], [], name)
        save_product_system(ps, str(_manifest_path(name)))
        emit_review(ps, name, str(_review_path(name)), t["repo"], t["globals_css"], t["components_dir"])
    # then draw the system — the header's stills and every item's comparison — as its own
    # background job, so the compile finishes and the page stays usable while it draws
    return {"log": getattr(ps, "_log", [])[-40:], "draw_job": start_drawing_system(name)}


DRAW_WORKERS = 3                     # drawings at once (each also films two scenes in Chrome)
_DRAWING: dict[str, set] = {}        # product -> item keys queued or being drawn by the system job
_DRAW_LOCK = threading.Lock()


def start_drawing_system(name: str, bento: bool = True) -> str:
    return _job("draw", lambda log: _draw_system(name, log, bento), tag=f"draw:{name}")


def _draw_system(name: str, log, bento: bool = True) -> dict:
    """Draw the header's stills, then every item whose drawing is missing or was drawn from
    evidence that has since changed. Unchanged items keep their drawings, so a recompile only
    redraws what moved. A failure is recorded per item; it never stops the rest."""
    from concurrent.futures import ThreadPoolExecutor
    from rubrick.scenes import make_drawing
    out: dict = {"errors": {}}
    m, d = _scene_inputs(name)
    todo = [i for i in d["items"] if not d["drawings"].get(i["key"]) or d["drawings"][i["key"]]["stale"]]
    with _DRAW_LOCK:
        _DRAWING[name] = {i["key"] for i in todo}
    total = len(todo) + (1 if bento else 0)
    finished = [0]

    def step():
        finished[0] += 1
        log({"progress": {"done": finished[0], "total": total}})
    log({"progress": {"done": 0, "total": total}})
    try:
        if bento:
            try:
                log("Drawing the header’s stills…")
                _bento(name, log)
            except Exception as e:
                out["bento_error"] = f"{type(e).__name__}: {e}"
            step()
        done = [0]
        log(f"Drawing {len(todo)} comparisons…" if todo else "Every comparison is up to date.")

        def one(item):
            try:
                make_drawing(name, m, d["items"], item, d["specimen"], d["target"], log=lambda _s: None)
            except Exception as e:
                out["errors"][item["key"]] = f"{type(e).__name__}: {e}"
            finally:
                with _DRAW_LOCK:
                    _DRAWING.get(name, set()).discard(item["key"])
                done[0] += 1
                log(f"Drawn {done[0]} of {len(todo)} comparisons")
                step()
        with ThreadPoolExecutor(max_workers=DRAW_WORKERS) as ex:
            list(ex.map(one, todo))
    finally:
        with _DRAW_LOCK:
            _DRAWING.pop(name, None)
    out["drawn"] = len(todo) - len(out["errors"])
    return out


def _drawing_queue(name: str) -> dict | None:
    job = next((j for j in _JOBS.values() if j.get("tag") == f"draw:{name}" and j["state"] == "running"), None)
    if not job:
        return None
    with _DRAW_LOCK:
        keys = sorted(_DRAWING.get(name, set()))
    return {"job": job["id"], "status": job.get("status", ""), "keys": keys,
            "progress": job.get("progress") or {"done": 0, "total": 0}}


def _scene_inputs(name: str) -> tuple[dict, dict]:
    m = json.loads(_manifest_path(name).read_text())
    return m, detail(name)


def _bento(name: str, log) -> dict:
    from rubrick.scenes import make_bento
    m, d = _scene_inputs(name)
    doc = make_bento(name, m, d["items"], d["specimen"], d["target"], log=log)
    return {"scenes": [s["id"] for s in doc["scenes"]]}


def _drawing(name: str, key: str, log) -> dict:
    from rubrick.scenes import make_drawing
    with _DRAW_LOCK:
        if key in _DRAWING.get(name, set()):
            raise RuntimeError("it's already being drawn with the rest of the system")
    m, d = _scene_inputs(name)
    item = next((i for i in d["items"] if i["key"] == key), None)
    if item is None:
        raise RuntimeError(f"{key} isn't in {name}'s system")
    doc = make_drawing(name, m, d["items"], item, d["specimen"], d["target"], log=log)
    return {"key": key, "ref": doc["ref"]}


def _check(name: str, repo: str, gcss: str, comps: str, native: bool) -> dict:
    from rubrick.conform import check_conformance
    from rubrick.product_system import load_product_system
    from rubrick.runs import record_run
    ps = load_product_system(str(_manifest_path(name)))
    report = check_conformance(repo, gcss, comps, f"ui:{name}:{repo}", ps, native=native)
    run = record_run(name, repo, native, report)
    return {"summary": run["summary"], "at": run["at"]}


def _promote(name: str, key: str, as_name: str, description: str) -> dict:
    """Name a new find and make it active for this product — the review file's promotion
    path for one item (vocabulary is global; ACTIVE is this product's)."""
    import tempfile
    from rubrick.review import apply_review
    review = _review(name)
    head, _, rest = key.partition(":")
    if rest.startswith("behavior:"):
        _, sub, nm = rest.split(":", 2)
        mod = f"behavior:{sub}"
    else:
        mod, _, nm = rest.partition(":")
    item = next((p for p in review.get("pending_promotions", []) if p.get("modality") == mod and p.get("name") == nm), None)
    if item is None:
        raise RuntimeError(f"{key} is not pending in {name}'s review — recompile first")
    data = {"system": name, "calibration_target": review.get("calibration_target") or _target(name) or {},
            "pending_promotions": [{**item, "decision": "promote", "as": as_name or nm, "description": description}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data, f)
    with _LOCK:
        res = apply_review(f.name)
    learned.touch(name)
    return res


# ---- HTTP ----------------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "rubrick-ui"

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body, ctype="application/json", cors=False, cache=False):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if cors:  # fonts and the kit, loaded by sandboxed (opaque-origin) scene frames
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _scene(self, path: str):
        from rubrick.scenes import find_scene, font_faces_css, load_bento, scene_html, _dir
        parts = path.split("/")
        if len(parts) != 6:
            return self._send(404, {"error": "not found"})
        _, _, name, kind, ref, leaf = parts
        sid, _, ext = leaf.rpartition(".")
        if kind not in ("bento", "drawing") or ext not in ("html", "css") or not re.fullmatch(r"[\w-]+", ref + sid):
            return self._send(404, {"error": "not found"})
        if not _manifest_path(name).exists():
            return self._send(404, {"error": "no such product"})
        s = find_scene(name, kind, ref, sid)
        if s is None:
            return self._send(404, {"error": "no such scene"})
        if ext == "css":
            return self._send(200, s.get("css", "").encode(), "text/css", cors=True)
        doc = load_bento(name) if kind == "bento" else json.loads((_dir(name) / "drawings" / f"{ref}.json").read_text())
        m = json.loads(_manifest_path(name).read_text())
        sp = _specimen(name, m, _target(name))
        origin = f"http://{self.headers.get('Host', '127.0.0.1')}"
        page = scene_html(s, css_href=f"/stage/{parts[2]}/{kind}/{ref}/{sid}.css", origin=origin,
                          fonts_css=font_faces_css(sp), look=doc.get("look", ""))
        return self._send(200, page.encode(), "text/html; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _local_only(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):  # refuse DNS-rebinding style access
            self._send(403, {"error": "local access only"})
            return False
        return True

    def do_GET(self):
        if not self._local_only():
            return
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                return self._send(200, _INDEX.read_bytes(), "text/html; charset=utf-8")
            if path in ("/kit/runtime.js", "/kit/runtime.css"):
                from rubrick.scenes import RUNTIME_DIR
                f = RUNTIME_DIR / path.rsplit("/", 1)[1]
                return self._send(200, f.read_bytes(), "text/javascript" if f.suffix == ".js" else "text/css",
                                  cors=True, cache=True)
            if path.startswith("/stage/"):  # /stage/<product>/<bento|drawing>/<ref>/<id>.(html|css)
                return self._scene(path)
            if path == "/api/products":
                return self._send(200, products())
            if path.startswith("/api/products/") and path.endswith("/font"):
                from urllib.parse import parse_qs
                from rubrick.specimen import font_file
                t = _target(path.split("/")[3])
                rel = parse_qs(urlparse(self.path).query).get("f", [""])[0]
                f = font_file(t["repo"], rel) if t and rel else None
                if f is None:
                    return self._send(404, {"error": "no such font"})
                return self._send(200, f.read_bytes(), "font/" + f.suffix.lstrip(".").lower(), cors=True)
            if path.startswith("/api/products/"):
                name = path.split("/")[3]
                if not _manifest_path(name).exists():
                    return self._send(404, {"error": f"no product system named {name!r}"})
                return self._send(200, detail(name))
            if path.startswith("/api/jobs/"):
                j = _JOBS.get(path.split("/")[3])
                return self._send(200 if j else 404, j or {"error": "no such job"})
            if path == "/api/learned":
                from rubrick.review import inspect_learned
                return self._send(200, inspect_learned())
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if not self._local_only():
            return
        path = unquote(urlparse(self.path).path)
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(415, {"error": "JSON only"})  # also blocks simple cross-site form posts
        try:
            b = self._body()
            if path == "/api/products":  # add a product: record its repo and compile it
                name = re.sub(r"[^A-Za-z0-9 _.-]", "", b.get("name", "")).strip()
                repo = str(pathlib.Path(b.get("repo", "")).expanduser().resolve())
                if not name or not pathlib.Path(repo).is_dir():
                    return self._send(400, {"error": "a name and an existing repo folder are required"})
                _save_target(name, repo, *_layout(repo, b))
                return self._send(200, {"job": _job("compile", lambda log: _compile(name, log)), "name": name})
            if path == "/api/pick-folder":  # the OS folder picker; blocks until chosen
                folder = pick_folder(b.get("prompt") or "Choose the product's folder")
                return self._send(200, {"path": folder})
            if path == "/api/detect":  # what Rubrick will read in a folder, before compiling
                from rubrick.discover import detect_layout
                repo = pathlib.Path(b.get("repo", "")).expanduser()
                if not repo.is_dir():
                    return self._send(400, {"error": "that folder doesn't exist"})
                d = detect_layout(str(repo))
                pkg = repo / "package.json"
                guess = ""
                try:
                    guess = json.loads(pkg.read_text()).get("name", "") if pkg.exists() else ""
                except Exception:
                    pass
                guess = (guess.split("/")[-1] or repo.name).replace("-", " ").replace("_", " ")
                return self._send(200, {**d, "repo": str(repo.resolve()),
                                        "name_guess": guess.strip().title()})
            if path == "/api/learned/revoke":
                from rubrick.detectors import revoke_detector
                return self._send(200, {"revoked": revoke_detector(b["key"])})
            parts = path.split("/")
            if len(parts) >= 5 and parts[1] == "api" and parts[2] == "products":
                name, action = parts[3], parts[4]
                if not _manifest_path(name).exists():
                    return self._send(404, {"error": f"no product system named {name!r}"})
                if action == "switch":
                    for k in b.get("keys") or [b["key"]]:
                        learned.record_switch(name, k, b["state"])
                    return self._send(200, {"ok": True})
                if action == "principle":
                    if b.get("prior") is not None:
                        learned.record_rationale(b["id"], b["prior"], product=name)
                    if b.get("title") is not None:
                        learned.record_title(b["id"], b["title"], name)
                    return self._send(200, {"ok": True})
                if action == "job":
                    t = _target(name)
                    if not t:
                        return self._send(400, {"error": "no repo recorded for this product"})
                    learned.record_job_override(str(pathlib.Path(t["repo"]).resolve()), b["original"], b["value"])
                    learned.touch(name)
                    return self._send(200, {"ok": True})
                if action == "promote":
                    return self._send(200, {"job": _job("promote", lambda: _promote(
                        name, b["key"], b.get("name", ""), b.get("description", "")))})
                if action == "draw":  # stills + every missing or outdated comparison
                    return self._send(200, {"job": start_drawing_system(name, bento=bool(b.get("bento", True)))})
                if action == "bento":
                    return self._send(200, {"job": _job("bento", lambda log: _bento(name, log), tag=f"bento:{name}")})
                if action == "drawing":
                    key = b["key"]
                    return self._send(200, {"job": _job("drawing", lambda log: _drawing(name, key, log),
                                                        tag=f"drawing:{name}:{key}")})
                if action == "recompile":
                    return self._send(200, {"job": _job("compile", lambda log: _compile(name, log))})
                if action == "check":
                    repo = str(pathlib.Path(b.get("repo", "")).expanduser().resolve())
                    if not pathlib.Path(repo).is_dir():
                        return self._send(400, {"error": "that folder doesn't exist"})
                    gcss, comps = _layout(repo, b)
                    return self._send(200, {"job": _job("check", lambda: _check(
                        name, repo, gcss, comps, bool(b.get("native"))))})
            return self._send(404, {"error": "not found"})
        except KeyError as e:
            return self._send(400, {"error": f"missing field {e}"})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})


def serve(port: int = 7317, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    print(f"Rubrick is running at {url}  (data: {paths.home()})  — Ctrl+C to stop")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
