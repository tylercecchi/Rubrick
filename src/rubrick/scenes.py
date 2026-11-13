"""Scenes — faux product UI, drawn with the vendored Stageshow kit (stageshow/VENDORED.md).

Two kinds, both pictures for the app, never inputs to a compile or a check:

    bento    — the header's animated stills: the product's signature interaction (the lead
               tile) and one of its parts at real size. Made after a compile, or on request.
    drawing  — one item's comparison: this product vs a typical build, the same subject drawn
               twice. Made the first time the item is opened, then cached.

The loop, per request:
    1. Claude writes the scenes (JSX against the kit) from the product's real source, its
       compiled system and its measured materials, guided by Stageshow's own skill docs
       (cached in the system prompt).
    2. Each scene is mounted and filmed with Stageshow's `scripts/film.mjs --gate` in headless
       Chrome. The gate's lines (never-intentional faults) and a contact sheet go back to
       Claude for up to FIX_ROUNDS fixes.
    3. The passing scene — or the best attempt, marked with its remaining faults — is stored
       under <RUBRICK_HOME>/scenes/<product>/.

Rubrick sets the LOOK itself: the specimen's ground, surfaces, text, accent, faces and radius
become the kit's --ss-* tokens on a `.rb-look` class every scene uses, so the materials are the
product's by construction. A typical build gets `.rb-typical` (neutral framework defaults).

Rehearsal needs Node and Chrome (filming is set up in ~/.rubrick/film on first use); without them scenes are kept
unrehearsed and say so.
"""

from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rubrick import paths

SCENE_MODEL = "claude-opus-5-5"   # high-craft code generation; measurement stays on its own pin
FIX_ROUNDS = 2
_PKG = pathlib.Path(__file__).resolve().parent
RUNTIME_DIR = _PKG / "ui" / "stage"
STAGESHOW = _PKG / "stageshow"          # vendored Stageshow: skill docs, gold examples, film tools
PLAYWRIGHT = "1.48.2"                    # the playwright-core Stageshow's film tools are written for
CHROME_CANDIDATES = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                     "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser")


# ── storage ──────────────────────────────────────────────────────────────────────────────

def _dir(product: str) -> pathlib.Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in product)
    d = paths.home() / "scenes" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key_file(product: str, key: str) -> pathlib.Path:
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    return _dir(product) / "drawings" / f"{h}.json"


def load_bento(product: str) -> dict | None:
    f = _dir(product) / "bento.json"
    return json.loads(f.read_text()) if f.exists() else None


def load_drawing(product: str, key: str) -> dict | None:
    f = _key_file(product, key)
    return json.loads(f.read_text()) if f.exists() else None


def _save(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def find_scene(product: str, kind: str, ref: str, scene_id: str) -> dict | None:
    """A stored scene by (bento|drawing, drawing key hash or '-', scene id)."""
    if kind == "bento":
        doc = load_bento(product)
    else:
        f = _dir(product) / "drawings" / f"{ref}.json"
        doc = json.loads(f.read_text()) if f.exists() else None
    return next((s for s in (doc or {}).get("scenes", []) if s["id"] == scene_id), None)


# ── the look: specimen → kit tokens ──────────────────────────────────────────────────────

def _lum(hexv: str | None) -> float | None:
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", hexv or "")
    if not m:
        return None
    r, g, b = (int(m.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def look_css(sp: dict) -> tuple[str, str]:
    """(css, theme) — the product's look as a `.rb-look` class over the kit's tokens."""
    ground = sp.get("ground") or "#ffffff"
    dark = (_lum(ground) if _lum(ground) is not None else 1) < 0.45
    faces = sp.get("faces") or {}
    stack = lambda f, fb: f'"{f}", {fb}' if f else fb
    pal = {p.get("name"): p["value"] for p in sp.get("palette", []) if p.get("name")}
    faint = next((v for k, v in pal.items() if re.search(r"(text|fg).*(dim|faint|mute|3)", k)), None)
    mid = next((v for k, v in pal.items() if re.search(r"(text|fg).*(mid|2|secondary)", k)), None)
    r = sp.get("radius_px")
    tok = {
        "--ss-canvas": ground, "--ss-well": ground,
        "--ss-surface": sp.get("surface") or ground, "--ss-raised": sp.get("surface") or ground,
        "--ss-chrome": sp.get("surface") or ground,
        "--ss-text-strong": sp.get("text"), "--ss-text": mid or sp.get("text"),
        "--ss-text-faint": faint, "--ss-line": sp.get("edge"),
        "--ss-accent": sp.get("accent"),
        "--ss-font": stack(faces.get("body") or faces.get("display"), "system-ui, sans-serif"),
        "--ss-mono": stack(faces.get("label"), "ui-monospace, monospace"),
        "--ss-radius-md": f"{r:g}px" if r is not None else None,
        "--ss-radius-lg": f"{r + 2:g}px" if r is not None else None,
        "--ss-radius-sm": f"{max(r - 2, 0):g}px" if r is not None else None,
        "--p-display": stack(faces.get("display"), "system-ui, sans-serif"),
        "--p-shadow": sp.get("shadow"),
        "--p-blur": f"{sp['blur_px']:g}px" if sp.get("blur_px") else None,
        "--p-ease": (sp.get("motion") or {}).get("easing"),
        "--p-duration": (sp.get("motion") or {}).get("duration"),
    }
    for name, val in pal.items():
        tok[f"--p-{name}"] = val
    body = "".join(f"  {k}: {v};\n" for k, v in tok.items() if v)
    return f".rb-look.ss-stage, .rb-look .ss-stage {{\n{body}}}\n", "dark" if dark else "light"


TYPICAL_LOOK = """.rb-typical.ss-stage, .rb-typical .ss-stage {
  --ss-canvas: #f8fafc; --ss-well: #f1f5f9; --ss-surface: #ffffff; --ss-raised: #ffffff;
  --ss-accent: #2563eb; --ss-font: system-ui, -apple-system, "Segoe UI", sans-serif;
  --ss-radius-sm: 6px; --ss-radius-md: 8px; --ss-radius-lg: 12px;
}
"""


def font_faces_css(sp: dict) -> str:
    return "".join(
        f'@font-face{{font-family:{json.dumps(f["family"])};src:url({json.dumps(f["url"])});'
        f'font-weight:{f["weight"]};font-style:{f["style"]};font-display:block}}\n'
        for f in sp.get("fonts", []) if f.get("url"))


# ── the scene page (shared by rehearsal and the app) ─────────────────────────────────────

def scene_html(scene: dict, *, css_href: str, origin: str, fonts_css: str = "",
               look: str = "") -> str:
    """One scene as a page. Loaded in a sandboxed frame; the CSP keeps it to this server and
    blocks any network call. The runtime and kit CSS load from /kit/ (film's gate reads that
    path as the kit's own), the scene's CSS from its own href (so the gate checks it)."""
    payload = {"code": scene["code"]}
    data = json.dumps(payload).replace("</", "<\\/")
    csp = (f"default-src 'none'; script-src {origin} 'unsafe-inline' 'unsafe-eval'; "
           f"style-src {origin} 'unsafe-inline'; font-src {origin} data:; img-src {origin} data: blob:; "
           f"connect-src 'none'")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{html.escape(csp)}">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" href="data:,">
<link rel="stylesheet" href="/kit/runtime.css"><style>{fonts_css}{look}
html,body{{margin:0;background:transparent;overflow:hidden}}#root{{width:100vw;height:100vh;display:flex;flex-direction:column;justify-content:center}}</style>
<link rel="stylesheet" href="{html.escape(css_href)}"></head>
<body><div id="root"></div><script src="/kit/runtime.js"></script>
<script>RubrickStage.mount(document.getElementById("root"), {data});</script></body></html>"""


# ── prompting ────────────────────────────────────────────────────────────────────────────

_GUIDE_FILES = ("SKILL.md", "references/bento.md", "references/craft.md", "references/framing.md",
                "references/motion.md", "references/kit.md", "references/looks.md")
_GOLD = ("dark-bento", "static-card", "chart-scrub", "hero-demo")

_RUBRICK_RULES = """\
You draw faux product UI for Rubrick, using the Stageshow kit and following the Stageshow
skill below in full. Rubrick captures a product's identity as what it does that a typical
build of the same kind of product would not, and what it deliberately leaves out. Your
scenes are how a designer SEES that identity, so each must read as THIS product: its real
anatomy and words (from its source), its real materials, its own motion.

How this environment differs from the skill's workflow:
- You don't run npm, the playground or film.mjs: Rubrick films every scene you write with
  `film.mjs --gate` and sends you the gate's lines and a contact sheet. Fix what they show.
- A scene is ONE JSX source with NO imports and NO exports. It must define
  `function Scene()` returning a single <Stage>. Everything the kit exports is in scope by
  name (Stage, Window, Bar, Text, Row, Card, Button, Icon, Count, Roll, Swap, Collapse, Fly,
  Follow, States, Stream, Popover, Camera, Scroll, Expand, Chart, Code, EASE, easeCss, ...),
  and React plus its hooks (useState, useEffect, useRef, useMemo, useCallback,
  useLayoutEffect, Fragment). Helper components and data constants above Scene are fine.
  Types are allowed (TypeScript is stripped). No lucide-react imports: use the kit's Icon.
- The LOOK is set for you. Put className="rb-look" on the Stage (className="rb-typical" for
  a typical-build scene) and use the theme you are told. That class already maps the
  product's ground, surfaces, text, accent, faces and radius onto the --ss-* tokens, and
  defines --p-* variables for the rest (--p-display for display type, --p-shadow, --p-blur,
  --p-ease, --p-duration, and one --p-<name> per named color in the product's source).
  Use those variables in your CSS instead of hard-coding the product's values.
- Your CSS is plain CSS. Prefix every class you write with the scene's prefix (given per
  scene). Never restyle a kit part's geometry from outside (the gate flags it).
- No network, no images, no photos, no emoji, no brand marks or logos of any company. Draw
  the product's own interface only. SVG and CSS shapes are fine.
- Respect the product's omissions: what it leaves out must stay out of its scenes (if it
  omits drop shadows, nothing casts one; if it omits icons, draw no icons).
- Real words: only the product's own strings where the story needs them (3 to 7 per scene);
  placeholder bars elsewhere.
- Under reduced motion the Stage shows `poster`; set it to the frame that tells the story.

Answer with the scenes only, in exactly this form, one block per scene asked for:

<scene id="ID">
<plan>two to four lines: the focal object, the beats, the payoff, what was left out</plan>
<jsx>
...the scene's JSX source...
</jsx>
<css>
...the scene's CSS...
</css>
</scene>
"""


def _guide_text() -> str:
    parts = [_RUBRICK_RULES, "\n\n# THE STAGESHOW SKILL (vendored, MIT, by Benji Taylor)\n"]
    for f in _GUIDE_FILES:
        p = STAGESHOW / f
        if p.exists():
            parts.append(f"\n\n===== {f} =====\n{p.read_text()}")
    for g in _GOLD:
        d = STAGESHOW / "examples" / g
        for p in sorted(d.glob("*")):
            if p.suffix in (".tsx", ".css") and p.stat().st_size < 30000:
                parts.append(f"\n\n===== gold example {g}/{p.name} =====\n{p.read_text()}")
    return "".join(parts)


_GUIDE_CACHE: str | None = None


def _guide() -> str:
    global _GUIDE_CACHE
    if _GUIDE_CACHE is None:
        _GUIDE_CACHE = _guide_text()
    return _GUIDE_CACHE


def _source_excerpt(repo: str, gcss: str, comps: str, budget: int = 60000) -> str:
    """The product's own source, global stylesheet first, then components — what the scenes
    are drawn from. Budgeted by relevance (larger component files first), never truncated
    mid-file."""
    from rubrick.discover import discover_components
    r = pathlib.Path(repo)
    out, used = [], 0
    g = r / gcss
    if g.is_file():
        t = g.read_text(errors="ignore")
        out.append(f"--- {gcss} ---\n{t}")
        used += len(t)
    files = sorted(discover_components(repo, comps), key=lambda f: -pathlib.Path(f).stat().st_size)
    for f in files:
        t = pathlib.Path(f).read_text(errors="ignore")
        if used + len(t) > budget:
            continue
        out.append(f"--- {pathlib.Path(f).relative_to(r)} ---\n{t}")
        used += len(t)
    return "\n\n".join(out)


def _system_digest(m: dict, items: list[dict]) -> str:
    about = m.get("about") or {}
    on = [i for i in items if i.get("state") == "on"]
    adds = [f"- {i.get('title') or i.get('label')} ({i.get('area', '')}): {i.get('desc', '')}".rstrip(": ")
            for i in on if i["section"] == "add"]
    omits = [f"- {i.get('title') or i.get('label')}: {i.get('desc', '')}".rstrip(": ")
             for i in on if i["section"] == "omit"]
    princ = [f"- {p.get('title')}: {p.get('prior')}" for p in m.get("principles", []) if p.get("active")]
    comps = [f"- {c.get('role')}: gesture {c.get('gesture')}, {c.get('affordance')}; patterns "
             f"{c.get('patterns')}; treatments {c.get('treatments')}" for c in m.get("components", [])]
    rules = [f"- moment '{r.get('applies_to')}': {r.get('requires')} (enter {r.get('enter_ms')}ms, "
             f"exit {r.get('exit_ms')}ms)" for r in m.get("rules", [])]
    comp = m.get("composition") or {}
    return "\n".join([
        f"What it is: {about.get('kind', '')}",
        "Jobs people do in it:\n" + "\n".join(f"- {j.get('need')}" for j in about.get("jobs", [])),
        f"Composition: {comp.get('archetype', '')}, focal anchor {comp.get('focal_anchor', '')}, "
        f"{comp.get('composition', '')}",
        "Principles:\n" + "\n".join(princ),
        "What it does that a typical build wouldn't (active):\n" + "\n".join(adds),
        "What it deliberately leaves out (active — keep these OUT of its scenes):\n" + ("\n".join(omits) or "- none"),
        "Signature parts:\n" + ("\n".join(comps) or "- none recorded"),
        "Interaction moments:\n" + ("\n".join(rules) or "- none recorded"),
    ])


def _materials(sp: dict) -> str:
    pal = ", ".join(f"{p.get('name') or '?'} {p['value']}" for p in sp.get("palette", [])[:18])
    t = sp.get("type") or {}
    return (f"Ground {sp.get('ground')}, text {sp.get('text')}, surface {sp.get('surface')}, edge "
            f"{sp.get('edge')}, accent {sp.get('accent')}. Palette: {pal}. Faces: {sp.get('faces')}"
            f"{' (font files shipped)' if sp.get('fonts') else ' (no font files; the stack falls back)'}. "
            f"Type: sizes {t.get('min_px')}–{t.get('max_px')}px, contrast {t.get('ratio')}x, tracking "
            f"{t.get('tracking_em')}em, max weight {t.get('max_weight')}, uppercase labels {t.get('upper')}. "
            f"Radius {sp.get('radius_px')}px; deepest shadow {sp.get('shadow')}; blur {sp.get('blur_px')}px; "
            f"motion {sp.get('motion')}; elevation moves {sp.get('elevation')}.")


def _bento_brief(name: str, theme: str) -> str:
    return f"""Draw two scenes for the header of {name}'s page in Rubrick: a bento where Rubrick
already draws the other tiles (the product's name in large type, a type specimen, its palette,
a surface sample, its motion timing, and the list of what it leaves out). So do NOT make a
palette, a type specimen or a list of omissions: those are said already (bento rule 9).

1. <scene id="hero"> — the lead tile. The product's signature interaction as a short story:
   the moment that most shows how this product differs from a typical build (its signature
   parts and interaction moments above). A cursor (or no cursor, if the product's identity is
   ambient life) causes one change; 3 to 5 beats; 10 to 16 seconds; loop; the payoff holds;
   the poster shows the result. Stage width={{600}} height={{340}}, compact={{{{ below: 520,
   width: 358, height: 300 }}}}, theme="{theme}". Prefix your classes "hx-".
2. <scene id="part"> — one of its parts at real size or larger, cropped by the tile: not a
   window. One small motion that plays once as it enters (or a quiet ambient loop if ambient
   motion is part of its identity). A different part from the hero's focal object. Stage
   width={{300}} height={{220}}, theme="{theme}". Prefix your classes "pt-"."""


def _drawing_brief(name: str, item: dict, theme: str) -> str:
    section = "omission" if item.get("section") == "omit" else "addition"
    moving = item.get("area") in ("ambient", "interaction", "rule", "behavior") or \
        str(item.get("key", "")).startswith(("rule:", "component:", "ambient:"))
    what = (f"{name} deliberately LEAVES THIS OUT; a typical build has it" if section == "omission"
            else f"{name} DOES THIS; a typical build doesn't")
    motion = ("Both scenes play the same short loop (one cause, one change, 4 to 8 seconds) so the "
              "difference is in the motion itself." if moving else
              "Both are stills (play once, nothing moves after it settles) unless the item is about motion.")
    return f"""Draw one comparison for a single item of {name}'s system, shown in Rubrick's detail
card: two scenes of the SAME subject (the same element, the same words, the same layout) so the
only difference a viewer sees is this item.

The item: "{item.get('title') or item.get('label')}" ({section}; area: {item.get('area', '')}).
{what}.
What it is: {item.get('desc', '')}
Where it lives in the product: {item.get('host', '')}
In {name}'s source: {json.dumps(item.get('evidence', ''))[:3000]}
What {name} does instead: {item.get('instead', '')}
What the typical build does (its code): {json.dumps(item.get('against', ''))[:3000]}

1. <scene id="product"> — {name}'s version, className="rb-look", theme="{theme}". Prefix "pr-".
2. <scene id="typical"> — a typical build's version, className="rb-typical", theme="light",
   built the way the typical build's code above does it. Prefix "ty-".
Each Stage width={{320}} height={{180}}. One component at real size, cropped by the stage,
not a window. Labels are drawn by Rubrick outside the scenes; don't title them. {motion}"""


def _parse(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<scene id="([\w-]+)">(.*?)</scene>', text, re.S):
        body = m.group(2)
        g = lambda tag: (re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", body, re.S) or [None, ""])[1]
        code = re.sub(r"^```\w*\n|\n```$", "", g("jsx").strip())
        css = re.sub(r"^```\w*\n|\n```$", "", g("css").strip())
        out.append({"id": m.group(1), "plan": g("plan").strip(), "code": code, "css": css})
    return out


def _call(messages: list, effort: str = "high") -> tuple[str, list]:
    import anthropic
    from rubrick.baseline import load_key
    client = anthropic.Anthropic(api_key=load_key())
    with client.beta.messages.stream(
            model=SCENE_MODEL, max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            thinking={"type": "adaptive"}, output_config={"effort": effort},
            system=[{"type": "text", "text": _guide(), "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
            messages=messages) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("the model declined to draw these scenes")
    text = "".join(b.text for b in msg.content if b.type == "text")
    return text, msg.content


# ── rehearsal: Stageshow's own gate ──────────────────────────────────────────────────────

def _chrome() -> str | None:
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    return next((c for c in CHROME_CANDIDATES if pathlib.Path(c).exists()), shutil.which("google-chrome"))


def film_dir() -> pathlib.Path:
    """Rubrick's own filming folder: Stageshow's film scripts plus playwright-core, set up on
    first use — so rehearsal works for an installed Rubrick, not only a repo checkout."""
    return paths.config_dir() / "film"


_FILM_LOCK = threading.Lock()


def _film_ready() -> bool:
    d = film_dir()
    src = STAGESHOW / "scripts" / "film.mjs"
    return ((d / "node_modules" / "playwright-core").exists() and (d / "scripts" / "film.mjs").exists()
            and (d / "scripts" / "film.mjs").read_bytes() == src.read_bytes())


def rehearsal_available() -> str | None:
    """None when scenes can be filmed (or can be, once filming is set up), else why not."""
    if not shutil.which("node") or not shutil.which("npm"):
        return "Node isn't installed (it's needed to film scenes; https://nodejs.org)"
    if not _chrome():
        return "Chrome isn't installed (or set CHROME_PATH)"
    return None


def ensure_filming(log=print) -> str | None:
    """Set up the filming folder if it isn't ready: copy Stageshow's film scripts (refreshed
    when the vendored copy changes) and install playwright-core there. One time, ~10 seconds.
    Returns None when ready, else why filming isn't available."""
    if why := rehearsal_available():
        return why
    with _FILM_LOCK:
        if _film_ready():
            return None
        d = film_dir()
        log("Setting up filming (one time)…")
        d.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(d / "scripts", ignore_errors=True)
        shutil.copytree(STAGESHOW / "scripts", d / "scripts")
        (d / "package.json").write_text(json.dumps(
            {"name": "rubrick-film", "private": True, "type": "module",
             "dependencies": {"playwright-core": PLAYWRIGHT}}, indent=2))
        try:
            r = subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"],
                               cwd=str(d), capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return "setting up filming timed out (npm install)"
        if r.returncode != 0 or not _film_ready():
            return f"setting up filming failed: {(r.stderr or r.stdout).strip()[-300:]}"
    return None


class _RehearsalServer:
    """Serves scenes, the runtime and the product's fonts to the filming browser."""

    def __init__(self, repo: str | None):
        self.pages: dict[str, bytes] = {}
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                p = self.path.split("?")[0]
                body, ctype = None, "text/plain"
                if p in ("/kit/runtime.js", "/kit/runtime.css"):
                    body = (RUNTIME_DIR / p.split("/")[-1]).read_bytes()
                    ctype = "text/javascript" if p.endswith(".js") else "text/css"
                elif p in outer.pages:
                    body = outer.pages[p]
                    ctype = "text/css" if p.endswith(".css") else "text/html; charset=utf-8"
                elif p.startswith("/font/") and repo:
                    from urllib.parse import unquote
                    from rubrick.specimen import font_file
                    f = font_file(repo, unquote(p[len("/font/"):]))
                    if f:
                        body, ctype = f.read_bytes(), "font/" + f.suffix.lstrip(".")
                if body is None:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.origin = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


def _film(url: str, out_png: pathlib.Path, timeout: float = 150) -> tuple[bool | None, list[str], str]:
    """Run Stageshow's gate on one scene page: (passed, fault lines, raw output). passed is
    None when the gate never reached a verdict. The script can linger for minutes after it
    prints its verdict (shutting the browser down), so it's stopped once the verdict is in."""
    import time
    # FILM_CHILD skips film.mjs's re-film wrapper (it guards against a dev server reloading
    # mid-film, which can't happen here) — the wrapper holds all output until its child exits,
    # and the child lingers for minutes after the verdict.
    env = {**os.environ, "CHROME_PATH": _chrome() or "", "FILM_CHILD": "1"}
    proc = subprocess.Popen(["node", str(film_dir() / "scripts" / "film.mjs"), url, "--select", ".ss-stage",
                             "--gate", "--count", "12", "--every", "1300", "--out", str(out_png)],
                            cwd=str(film_dir()), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env, start_new_session=True)
    lines_out: list[str] = []
    done = threading.Event()

    def pump():
        for line in proc.stdout:
            lines_out.append(line.rstrip("\n"))
            if line.startswith(("rehearsal passed", "rehearsal failed")):
                done.set()
        done.set()
    threading.Thread(target=pump, daemon=True).start()
    done.wait(timeout)
    time.sleep(0.5)  # the last lines of the report
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, 15)
        except Exception:
            proc.kill()
    raw = "\n".join(lines_out)
    if not any(l.startswith("rehearsal ") for l in lines_out):
        return None, ["film: no verdict (the gate timed out)"], raw
    passed = "rehearsal passed" in raw
    lines = [l.strip() for l in raw.splitlines()
             if (l.strip().startswith(("[stage", "error", "clipped", "scene error"))
                 or "pageerror" in l or "Uncaught" in l)
             and "] manual:" not in l]  # "manual:" lines ask a person to watch; they're not faults
    if "no stage" in raw.lower() or "0 stages" in raw:
        lines.append("the scene did not mount a Stage (check the console errors above)")
    return passed, lines, raw


def rehearse(scenes: list[dict], *, look: str, fonts: list[dict], repo: str | None,
             workdir: pathlib.Path, log=print) -> list[dict]:
    """Film each scene with the gate. Adds rehearsal={passed, lines} and a contact-sheet path."""
    why = ensure_filming(log)
    if why:
        for s in scenes:
            s["rehearsal"] = {"passed": None, "lines": [], "note": f"not rehearsed: {why}"}
        return scenes
    srv = _RehearsalServer(repo)
    try:
        fonts_css = font_faces_css({"fonts": [{**f, "url": f"/font/{f['file']}"} for f in fonts if f.get("file")]})
        from concurrent.futures import ThreadPoolExecutor
        for s in scenes:
            base = f"/scene/{s['id']}"
            srv.pages[base + ".css"] = s.get("css", "").encode()
            srv.pages[base + ".html"] = scene_html(s, css_href=base + ".css", origin=srv.origin,
                                                   fonts_css=fonts_css, look=look).encode()

        def one(s):
            png = workdir / f"{s['id']}.png"
            passed, lines, _raw = _film(f"{srv.origin}/scene/{s['id']}.html", png)
            s["rehearsal"] = {"passed": passed, "lines": lines[:30]}
            if passed is None:
                s["rehearsal"]["note"] = "the gate didn't reach a verdict"
            s["_sheet"] = str(png) if png.exists() else None
        with ThreadPoolExecutor(max_workers=len(scenes) or 1) as ex:
            list(ex.map(one, scenes))
    finally:
        srv.close()
    return scenes


def _feedback(scenes: list[dict]) -> list:
    """A user turn carrying the failing scenes' gate lines and contact sheets, asking for fixes
    of those scenes only (a scene that passed is kept as it is)."""
    import base64
    ids = ", ".join(s["id"] for s in scenes)
    content: list = [{"type": "text", "text":
                      f"Rubrick filmed your scenes with `film.mjs --gate`. These need another pass: {ids}. "
                      "Fix every never-intentional line, the largest visible fault first (framing, then "
                      "hierarchy, then motion, then polish), and look hard at each contact sheet the way "
                      "the skill's most exacting designer would. Return ONLY these scenes, complete, in "
                      "the same form."}]
    for s in scenes:
        r = s.get("rehearsal") or {}
        verdict = "rehearsal passed" if r.get("passed") else "rehearsal failed"
        content.append({"type": "text", "text": f"\nScene {s['id']}: {verdict}\n" + "\n".join(r.get("lines", []))})
        sheet = s.get("_sheet")
        if sheet and pathlib.Path(sheet).exists():
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                        "data": base64.standard_b64encode(pathlib.Path(sheet).read_bytes()).decode()}})
    return content


def _score(s: dict) -> tuple:
    """Passed > failed with fewer faults > never judged."""
    r = s.get("rehearsal") or {}
    if r.get("passed"):
        return (2, 0)
    if r.get("passed") is False:
        return (1, -len(r.get("lines", [])))
    return (0, 0)


def draw(brief: str, context: str, *, look: str, fonts: list[dict], repo: str | None,
         want: list[str], log=print, effort: str = "high") -> list[dict]:
    """Generate → film → fix, keeping each scene's best attempt."""
    messages: list = [{"role": "user", "content": context + "\n\n" + brief}]
    best: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for round_ in range(FIX_ROUNDS + 1):
            log("drawing…" if round_ == 0 else f"fixing what the gate found (pass {round_ + 1})…")
            text, content = _call(messages, effort)
            pending = [w for w in want if not ((best.get(w) or {}).get("rehearsal") or {}).get("passed")]
            scenes = [s for s in _parse(text) if s["id"] in pending]
            if not scenes:
                if round_ == 0:
                    raise RuntimeError("the drawing came back without any scenes")
                break
            work = pathlib.Path(tmp) / f"r{round_}"
            work.mkdir()
            log("rehearsing with Stageshow's gate…")
            rehearse(scenes, look=look, fonts=fonts, repo=repo, workdir=work, log=log)
            for s in scenes:
                if s["id"] not in best or _score(s) >= _score(best[s["id"]]):
                    best[s["id"]] = s
            failing = [best[w] for w in want if w in best and (best[w].get("rehearsal") or {}).get("passed") is False]
            if not failing:
                break  # all passed, or they can't be filmed here
            if round_ < FIX_ROUNDS:
                messages += [{"role": "assistant", "content": content},
                             {"role": "user", "content": _feedback(failing)}]
    out = []
    for sid in want:
        if sid in best:
            s = best[sid]
            s.pop("_sheet", None)
            out.append(s)
    return out


# ── entry points ─────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _context(name: str, m: dict, items: list[dict], sp: dict, target: dict | None) -> str:
    src = _source_excerpt(target["repo"], target["globals_css"], target["components_dir"]) if target else \
        "(the product's source isn't recorded; draw from the system and materials)"
    return (f"# The product: {name}\n\n{_system_digest(m, items)}\n\n# Its materials (measured)\n"
            f"{_materials(sp)}\n\n# Its source\n{src}")


def make_bento(name: str, m: dict, items: list[dict], sp: dict, target: dict | None, log=print) -> dict:
    css, theme = look_css(sp)
    scenes = draw(_bento_brief(name, theme), _context(name, m, items, sp, target), look=css,
                  fonts=sp.get("fonts", []), repo=(target or {}).get("repo"), want=["hero", "part"], log=log)
    doc = {"made_at": _now(), "model": SCENE_MODEL, "theme": theme, "look": css,
           "scenes": [{**s, "width": 600 if s["id"] == "hero" else 300,
                       "height": 340 if s["id"] == "hero" else 220} for s in scenes]}
    _save(_dir(name) / "bento.json", doc)
    return doc


def drawing_fingerprint(item: dict, sp: dict) -> str:
    basis = json.dumps([item.get("key"), item.get("evidence"), item.get("against"), item.get("instead"),
                        sp.get("ground"), sp.get("accent"), sp.get("faces")], sort_keys=True, default=str)
    return hashlib.sha1(basis.encode()).hexdigest()[:12]


def make_drawing(name: str, m: dict, items: list[dict], item: dict, sp: dict, target: dict | None,
                 log=print) -> dict:
    css, theme = look_css(sp)
    scenes = draw(_drawing_brief(name, item, theme), _context(name, m, items, sp, target),
                  look=css + TYPICAL_LOOK, fonts=sp.get("fonts", []), repo=(target or {}).get("repo"),
                  want=["product", "typical"], log=log, effort="medium")
    doc = {"made_at": _now(), "model": SCENE_MODEL, "key": item["key"], "theme": theme,
           "look": css + TYPICAL_LOOK, "fingerprint": drawing_fingerprint(item, sp),
           "ref": _key_file(name, item["key"]).stem,
           "scenes": [{**s, "width": 320, "height": 180} for s in scenes]}
    _save(_key_file(name, item["key"]), doc)
    return doc
