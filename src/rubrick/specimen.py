"""Specimen — the product's real materials, read for display (the app's header bento).

Not a measurement: nothing here is checked or feeds a compile. It pulls the concrete
tokens a person would recognize (ground and text colors, the palette, the faces and their
font files, the type extremes, corner radius, the deepest shadow, blur, motion timing) from
the product's own source, so the app can draw tiles in the product's actual materials.
When no repo is recorded it falls back to what the manifest carries (palette anchors, face
names, metrics), and says so in `source`.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re

FONT_SUFFIXES = {".woff2", ".woff", ".ttf", ".otf"}
_COLOR = r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|oklch\([^)]*\)"
_GENERIC_FAMILIES = {"sans-serif", "serif", "monospace", "system-ui", "ui-monospace", "ui-sans-serif",
                     "ui-serif", "inherit", "initial", "-apple-system", "blinkmacsystemfont", "cursive"}


def _num(x: str) -> float | None:
    try:
        return float(x)
    except ValueError:
        return None


def _vars(src: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, val in re.findall(r"--([\w-]+)\s*:\s*([^;{}]+)", src):
        out.setdefault(name, val.strip())
    return out


def _resolve(val: str, vs: dict, depth: int = 0) -> str:
    m = re.search(r"var\(\s*--([\w-]+)\s*(?:,\s*([^)]+))?\)", val)
    if not m or depth > 6:
        return val
    rep = vs.get(m.group(1)) or (m.group(2) or "")
    return _resolve(val[:m.start()] + rep + val[m.end():], vs, depth + 1)


def _pick_var(vs: dict, patterns: tuple[str, ...]) -> str | None:
    for pat in patterns:
        for name, val in vs.items():
            if re.fullmatch(pat, name):
                v = _resolve(val, vs)
                if re.fullmatch(_COLOR, v.strip()):
                    return v.strip()
    return None


def _font_faces(repo: pathlib.Path, files: list[pathlib.Path]) -> list[dict]:
    faces = []
    for f in files:
        if f.suffix not in {".css", ".scss"}:
            continue
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for block in re.findall(r"@font-face\s*{([^}]*)}", text):
            fam = re.search(r"font-family\s*:\s*['\"]?([^;'\"]+)", block)
            url = re.search(r"url\(\s*['\"]?([^'\")]+)", block)
            if not (fam and url) or url.group(1).startswith(("http:", "https:", "data:")):
                continue
            u = url.group(1).split("?")[0].split("#")[0]
            cands = ([repo / "public" / u.lstrip("/"), repo / u.lstrip("/")] if u.startswith("/")
                     else [f.parent / u])
            path = next((c.resolve() for c in cands if c.is_file()), None)
            if path is None or path.suffix.lower() not in FONT_SUFFIXES:
                continue
            try:
                path.relative_to(repo.resolve())
            except ValueError:
                continue  # never serve a file from outside the product's folder
            w = re.search(r"font-weight\s*:\s*(\d+)", block)
            st = re.search(r"font-style\s*:\s*(\w+)", block)
            faces.append({"family": fam.group(1).strip(), "weight": int(w.group(1)) if w else 400,
                          "style": st.group(1) if st else "normal",
                          "file": str(path.relative_to(repo.resolve()))})
    return faces


def _families(src: str) -> list[str]:
    """Named font families in use, most-used first (generic fallbacks dropped)."""
    seen = collections.Counter()
    vs = _vars(src)
    for decl in re.findall(r"font-?[fF]amily\s*:\s*([^;}\n]+)", src):
        first = _resolve(decl, vs).split(",")[0].strip().strip("'\"` ")
        if first and first.lower() not in _GENERIC_FAMILIES and not first.startswith("var("):
            seen[first] += 1
    return [f for f, _ in seen.most_common()]


def _shadow_depth(s: str) -> float:
    total = 0.0
    for part in re.split(r",(?![^(]*\))", s):
        if "inset" in part:
            continue
        nums = [_num(n) for n in re.findall(r"(-?\d+(?:\.\d+)?)px", part)]
        nums = [n for n in nums if n is not None]
        if len(nums) >= 3:
            total = max(total, abs(nums[1]) + nums[2])
    return total


def specimen(manifest: dict, repo: str | None = None, gcss: str = "", comps: str = "") -> dict:
    styles = {s["facet"]: s for s in manifest.get("styles", [])}
    typo, color = styles.get("typography", {}), styles.get("color", {})
    tm = typo.get("metrics", {}) or {}
    anchors = (color.get("concrete") or {}).get("anchors", []) or []
    ramp = (color.get("concrete") or {}).get("neutral_ramp", []) or []
    faces_named = ((typo.get("concrete") or {}).get("values") or {}).get("faces", {}) or {}
    out: dict = {"source": "manifest", "ground": None, "text": None, "surface": None, "edge": None,
                 "accent": anchors[0] if anchors else None,
                 "palette": [{"name": "", "value": c, "marks": True} for c in anchors] +
                            [{"name": "", "value": c, "marks": False} for c in ramp],
                 "faces": {k: v for k, v in faces_named.items() if isinstance(v, str)},
                 "fonts": [], "type": {"max_px": None, "min_px": None,
                                       "ratio": tm.get("scale_contrast_ratio"),
                                       "tracking_em": tm.get("micro_tracking_em"),
                                       "max_weight": tm.get("max_weight"), "upper": False},
                 "radius_px": None, "shadow": None, "blur_px": None,
                 "motion": {"duration": None, "easing": None,
                            "ambient": list((styles.get("ambient") or {}).get("identity_moves", []))},
                 "elevation": list((styles.get("elevation") or {}).get("identity_moves", []))}
    tone = (color.get("metrics") or {}).get("background_tonality")
    hexes = [c for c in ramp if re.fullmatch(r"#[0-9a-fA-F]{6}", c)]
    if hexes and tone is not None:  # darkest or lightest neutral, by the measured tonality
        light = lambda c: sum(int(c[i:i + 2], 16) for i in (1, 3, 5))
        out["ground"] = min(hexes, key=light) if tone < 0.5 else max(hexes, key=light)
    if not repo or not pathlib.Path(repo).is_dir():
        return out

    from rubrick.subtractions import _style_files
    r = pathlib.Path(repo)
    files = _style_files(repo, gcss, comps)
    raw = []
    for f in files:
        try:
            raw.append(f.read_text(errors="ignore"))
        except OSError:
            pass
    src = "\n".join(raw)
    vs = _vars(src)
    out["source"] = "code"

    # colors: the declared custom properties, in declaration order; the manifest's anchors
    # (the colors that mark meaning) flagged so the tile can give them room
    marks = {a.lower() for a in anchors}
    pal, seen = [], set()
    for name, val in vs.items():
        v = _resolve(val, vs).strip()
        if re.fullmatch(_COLOR, v) and v.lower() not in seen:
            seen.add(v.lower())
            pal.append({"name": name, "value": v, "marks": v.lower() in marks})
    if pal:
        out["palette"] = pal[:18]
    def body(prop: str) -> str | None:  # what the page's body actually paints
        m = re.search(r"(?:^|[\s}])(?:html,\s*)?body\s*{([^}]*)}", src)
        d = m and re.search(rf"(?:^|[;\s]){prop}\s*:\s*([^;]+)", m.group(1))
        v = d and _resolve(d.group(1), vs).strip()
        named = {"white": "#ffffff", "black": "#000000"}
        v = named.get(v, v) if v else None
        return v if v and re.fullmatch(_COLOR, v) else None
    out["ground"] = body("background(?:-color)?") or _pick_var(
        vs, (r"ground", r"(page-)?bg", r"background", r"canvas", r"surface-?0?", r"gray-?0",
             r"neutral-?0")) or out["ground"]
    out["text"] = body("color") or _pick_var(
        vs, (r"text(-hi|-primary|-1)?", r"fg", r"foreground", r"ink", r"gray-?8"))
    out["surface"] = _pick_var(vs, (r"surface-?[12]", r"surface", r"panel", r"card", r"gray-?[12]"))
    out["edge"] = _pick_var(vs, (r"edge", r"border", r"line", r"gray-?3"))
    out["accent"] = _pick_var(vs, (r"accent", r"primary", r"brand")) or out["accent"]

    # type: faces by role (manifest names first, else the most-used families), real font
    # files when the source ships them, and the extremes of the size scale
    fams = _families(src)
    if not out["faces"] and fams:
        out["faces"] = {"display": fams[0], **({"body": fams[1]} if len(fams) > 1 else {})}
    out["fonts"] = _font_faces(r, files)
    sizes = [float(x) for x in re.findall(r"font-?[sS]ize\s*:\s*['\"]?(\d+(?:\.\d+)?)(?:px)?\b", src)]
    sizes += [float(x) * 16 for x in re.findall(r"font-?[sS]ize\s*:\s*['\"]?(\d+(?:\.\d+)?)rem", src)]
    sizes = [s for s in sizes if 6 <= s <= 400]
    if sizes:
        out["type"]["max_px"], out["type"]["min_px"] = max(sizes), min(sizes)
        out["type"]["ratio"] = out["type"]["ratio"] or round(max(sizes) / min(sizes), 1)
    out["type"]["upper"] = bool(re.search(r"text-?[tT]ransform\s*:\s*['\"]?uppercase|\buppercase\b", src))
    if out["type"]["tracking_em"] is None:
        tr = [float(x) for x in re.findall(r"letter-?[sS]pacing\s*:\s*['\"]?(\d*\.\d+)em", src)]
        out["type"]["tracking_em"] = max(tr) if tr else None

    # form: the most-used corner radius, the deepest drop shadow, any backdrop blur
    radii = [float(x) for x in re.findall(r"(?:border-?[rR]adius|rounded)\s*:\s*['\"]?(\d+(?:\.\d+)?)(?:px)?(?![\d.%])", src)]
    radii = [x for x in radii if 0 < x < 100]
    if radii:
        out["radius_px"] = collections.Counter(radii).most_common(1)[0][0]
    shadows = [_resolve(s, vs).strip() for s in
               re.findall(r"box-?[sS]hadow\s*:\s*['\"]?([^;'\"}]+)", src)]
    shadows = [s for s in shadows if "px" in s and _shadow_depth(s) > 0]
    if shadows:
        out["shadow"] = max(shadows, key=_shadow_depth)
    blur = re.findall(r"backdrop-?[fF]ilter\s*:\s*['\"]?blur\((\d+(?:\.\d+)?)px", src)
    out["blur_px"] = max(float(b) for b in blur) if blur else None

    # motion: the product's own timing and easing, when it names them
    ease = None
    for k, v in vs.items():
        if re.search(r"ease|easing|curve", k) and "cubic-bezier" in v:
            ease = v.strip()
            break
    out["motion"]["easing"] = ease
    for k, v in vs.items():
        if re.search(r"beat|duration|dur|speed|tempo", k) and re.fullmatch(r"\d+(?:\.\d+)?m?s", v.strip()):
            out["motion"]["duration"] = v.strip()
            break
    return out


def font_file(repo: str, rel: str) -> pathlib.Path | None:
    """A font file inside the product's folder, or None — the only files the app serves."""
    root = pathlib.Path(repo).resolve()
    p = (root / rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p if p.is_file() and p.suffix.lower() in FONT_SUFFIXES else None


if __name__ == "__main__":
    import sys
    print(json.dumps(specimen(json.load(open(sys.argv[1])), *sys.argv[2:5]), indent=2))
