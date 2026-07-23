"""Mode B — extract a typed material from real repo source (static CSS parse).

Reads the actual gradient strings a component renders and parses them into the
same typed MaterialStack we previously hand-transcribed. Types params as it goes
(peak alpha per overlay), per the Phase 1.1 lesson — extraction must TYPE, not
just pull. The base is the entity's own color VARIABLE (hue-agnostic by design),
so we emit `entity.color`, never a literal hue.
"""

from __future__ import annotations

import pathlib
import re

from rubrick.material import Layer, MaterialStack

_GRAD = re.compile(r'"([^"]*gradient\([^"]*)"')
_RGBA = re.compile(r'rgba?\(([^)]*)\)')
_AT = re.compile(r'at\s+(-?[\d.]+)%\s+(-?[\d.]+)%')
# box-shadow value strings (CSS-in-JS `boxShadow: "..."` or CSS `box-shadow: ...;`)
_SHADOW = re.compile(r'(?:boxShadow|box-shadow)\s*[:=]\s*["\'`]([^"\'`]{1,400})["\'`]')


def gradient_strings(path: str) -> list[str]:
    return _GRAD.findall(pathlib.Path(path).read_text())


def _inset_bevels(text: str) -> list[str]:
    """Inset box-shadows — the canonical bevel/emboss (an inner highlight + inner shadow pair
    reading as a lit edge). Trial #3: four valid bevels (inset shadow pair, 1px rim, border
    shorthand, edge gradient) all failed because _classify only saw border-image gradients.
    box-shadow isn't a gradient at all, so it wasn't even gathered. This makes the commonest
    real bevel visible."""
    return [s for s in _SHADOW.findall(text) if "inset" in s.lower()]


def _alphas(css: str) -> list[float]:
    out = []
    for body in _RGBA.findall(css):
        parts = [p.strip() for p in body.split(",")]
        out.append(float(parts[3]) if len(parts) == 4 else 1.0)
    return out


def _neutral(css: str) -> bool:
    # neutral = carries no real HUE (chroma near zero), not literally pure white/black. A warm
    # near-black texture rgba(27,26,23) or an off-white is neutral — it transfers across entities;
    # only a saturated tint (the entity's own hue leaking into an overlay) should fail.
    for body in _RGBA.findall(css):
        parts = [p.strip() for p in body.split(",")[:3]]
        try:
            r, g, b = (int(round(float(x))) for x in parts)
        except ValueError:
            continue
        if max(r, g, b) - min(r, g, b) > 16:
            return False
    return True


def _classify(css: str) -> str:
    if "border-box" in css or "padding-box" in css:
        return "bevel"
    if "repeating-linear-gradient" in css:
        return "texture"
    if "radial-gradient" in css:
        return "lighting"
    return "sheen"


def _peak(css: str) -> float:
    a = _alphas(css)
    return round(max(a), 3) if a else 0.0


def extract_focal_surface(path: str) -> MaterialStack:
    text = pathlib.Path(path).read_text()
    grads = _GRAD.findall(text)
    by_role: dict[str, list[str]] = {}
    for g in grads:
        by_role.setdefault(_classify(g), []).append(g)
    # bevel can also be an inset box-shadow (not a gradient) — the classic emboss technique
    if "bevel" not in by_role:
        insets = _inset_bevels(text)
        if insets:
            by_role["bevel"] = insets

    layers = [Layer(role="base", kind="solid", neutral=False, params={"fill": "entity.color"})]

    if "sheen" in by_role:
        css = by_role["sheen"][0]
        layers.append(Layer(role="sheen", kind="linear-gradient",
                            neutral=_neutral(css), alpha=_peak(css)))
    if "lighting" in by_role:
        radials = by_role["lighting"]
        # top-keyed if any light is anchored at/above the top edge (y <= 0)
        lights = []
        for r in radials:
            m = _AT.search(r)
            y = float(m.group(2)) if m else 50.0
            lights.append({"role": "top-key" if y <= 0 else "fill"})
        peak = round(max(_peak(r) for r in radials), 3)
        neutral = all(_neutral(r) for r in radials)
        layers.append(Layer(role="lighting", kind="radial-set",
                            neutral=neutral, alpha=peak, params={"lights": lights}))
    if "texture" in by_role:
        css = by_role["texture"][0]
        layers.append(Layer(role="texture", kind="repeating-linear",
                            neutral=_neutral(css), alpha=_peak(css)))
    if "bevel" in by_role:
        css = by_role["bevel"][0]
        layers.append(Layer(role="bevel", kind="border-gradient",
                            neutral=_neutral(css), alpha=_peak(css)))

    return MaterialStack(role="focal-entity", layers=layers,
                         geometry={"radius": 12, "clip": "inset(0 round 12px)"})


def find_focal_surface(repo: str, comps: str, limit: int = 40):
    """Locate a repo's focal material surface deterministically: the component with
    the RICHEST material stack (most non-base layers). This is a cheap regex parse,
    so scanning every component and taking the max beats fuzzy LLM discovery for
    element targeting. Returns (path, MaterialStack) or None if the product is flat."""
    d = pathlib.Path(repo) / comps
    if not d.exists():
        return None
    best = None
    for cpath in sorted(d.rglob("*.tsx"))[:limit]:
        try:
            stack = extract_focal_surface(str(cpath))
        except Exception:
            continue
        n = len(stack.material_roles())
        if n > 0 and (best is None or n > len(best[1].material_roles())):
            best = (str(cpath), stack)
    return best
