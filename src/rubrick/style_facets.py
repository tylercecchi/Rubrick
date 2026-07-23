"""Generic static-style facet machinery — color-as-posture and density/spacing,
built on the pattern typography just proved. Same observe→baseline→diff→route,
same tear-escape (novel_features). Captures DELTAS + DISPOSITION, never token
values / palettes / spacing scales (that would be a design system).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from rubrick import paths
import re
import subprocess

import anthropic
from pydantic import BaseModel

from rubrick import learned
from rubrick.baseline import _load_key

_CACHE = paths.cache_dir() / "style_cache.json"

# --- facet registry: vocab + what source to read -------------------------------
FACETS = {
    "color": {
        "desc": "color-as-POSTURE — the ROLE color plays, not the palette",
        "vocab": {
            "entity-driven-color": "core colors derived from the subject/entity, not a fixed brand palette",
            "semantic-status-color": "color encodes state / status / category",
            "sentiment-coding": "color maps to sentiment (positive / negative / neutral)",
            "environmental-tint": "a global filter/tint applied over the whole canvas",
            "restrained-neutral-chrome": "calm neutral grounds/chrome around expressive accents",
            "expressive-accent": "bold / saturated accent usage as identity",
        },
        "css_keys": ["color", "background", "--", "filter", "fill", "theme",
                     "border", "gradient", "shadow", "rgb", "hsl", "outline", "stroke", "#"],
        "grep": ["background", "backgroundColor", "color", "fill", "stroke", "filter",
                 "border", "borderColor", "boxShadow", "outline", "WebkitTextStroke"],
    },
    "ambient": {
        "desc": ("AMBIENT MOTION — untriggered, PERPETUAL life (infinite loops that run "
                 "with no user action); NOT one-shot user-triggered transitions, which "
                 "belong to the behavior modality"),
        "vocab": {
            "perpetual-loop": "an infinite animation that runs continuously with no trigger",
            "breathing-pulse": "scale/opacity pulsing in and out to feel alive",
            "rotation-spin": "continuous rotation",
            "drift-scroll": "a texture/pattern perpetually scrolling or drifting",
            "orchestrated-stagger": "multiple ambient elements animating in phased/offset timing",
            "physics-loop": "an ambient loop with spring/overshoot easing rather than linear",
            "presence-signal": "ambient motion that signals liveness / real-time activity",
            "ambient-restraint": "low-amplitude, subtle, background-level ambient motion",
        },
        "css_keys": ["keyframes", "animation", "infinite", "--motion", "transform"],
        "grep": ["animation", "transform"],
    },
    "density": {
        "desc": "density/spacing POSTURE — the spatial strategy, not the spacing scale",
        "vocab": {
            "full-bleed-canvas": "content fills the viewport edge-to-edge, no frame",
            "floating-overlays": "panels/sheets/bars float over a base layer",
            "generous-hero-space": "large breathing room around hero elements",
            "information-dense": "tightly packed information",
            "dynamic-density": "content or mode determines spatial rhythm — density/compactness "
                               "shifts (packed⇄roomy modes, content-sized rows, container/observer-driven animated spacing)",
            "safe-area-mobile": "mobile safe-area / inset-aware chrome",
        },
        "css_keys": ["padding", "margin", "height", "width", "dvh", "vh", "inset",
                     "overscroll", "overflow", "gap", "grid", "flex", "display",
                     "column", "aspect", "justify", "align", "place", "min-", "max-"],
        "grep": ["padding", "margin", "gap", "height", "width", "inset", "position",
                 "flex", "flexDirection", "display", "gridTemplateColumns", "gridTemplateRows",
                 "justifyContent", "alignItems", "overflow", "aspectRatio"],
    },
    "elevation": {
        "desc": ("ELEVATION / depth POSTURE — how the product expresses z-axis hierarchy "
                 "(shadow, blur, layering, separation), NOT the specific shadow values"),
        "vocab": {
            "soft-floating-shadows": "elements float on soft, diffuse drop shadows",
            "flat-bordered": "separation via borders / hairline rules with minimal or no shadow — a flat aesthetic",
            "backdrop-blur": "translucent blurred layers (glassmorphism / frosted panels)",
            "layered-overlays": "strong z-stacking — sheets/overlays float above a base layer",
            "dramatic-shadow": "deep, high-contrast shadows for strong emphasis",
            "inset-depth": "inner / pressed shadows — recessed or engraved surfaces",
            "colored-shadow": "shadows tinted with hue/accent rather than neutral black",
        },
        "css_keys": ["box-shadow", "shadow", "backdrop", "blur", "filter", "z-index",
                     "--shadow", "--elevation", "drop-shadow", "inset", "border"],
        "grep": ["boxShadow", "backdropFilter", "WebkitBackdropFilter", "filter",
                 "zIndex", "dropShadow"],
    },
}


class FacetFeature(BaseModel):
    feature: str  # OPEN str (base vocab + promoted)
    evidence: str


class FacetNovel(BaseModel):
    name: str
    evidence: str


class FacetObs(BaseModel):
    features: list[FacetFeature]
    novel_features: list[FacetNovel] = []
    identity_summary: str

    def feature_set(self) -> set[str]:
        return {f.feature for f in self.features} | {n.name for n in self.novel_features}

    def grounded_set(self) -> set[str]:
        """Known-vocab features only — excludes novel_features (unpromoted, run-variant).
        Required conformance deltas use this; novel features are pending-promotion."""
        return {f.feature for f in self.features}


class FacetDefault(BaseModel):
    model_config = {"extra": "forbid"}
    features: list[str]

    def feature_set(self) -> set[str]:
        return set(self.features)


# --- color APPLICATION: how colors are deployed (not just which exist) ----------
# A product system must capture how facets are APPLIED, not only what they are — that
# application discipline is what makes a palette read as one mind. Captured as kind→role
# BINDINGS with a reservation flag (a transferable disposition), never a hex→component map
# (that would be a design system). Reserved bindings are the delta from a generic app, which
# sprays one blue across links + headings + borders ad-hoc.
COLOR_KINDS = {
    "accent": "the saturated signature color(s) — the identity hue",
    "semantic": "status / category colors (encode kind or state)",
    "sentiment": "positive / negative / neutral sentiment colors",
    "neutral": "greys / chrome / structural neutrals",
}
COLOR_ROLES = {
    "ground": "the page / app background — the base canvas",
    "surface": "panels, cards, sheets, raised containers",
    "text": "foreground — body copy, headings, labels",
    "edge": "borders, outlines, dividers, focus rings",
    "interactive": "buttons, links, controls, hover / active / focus affordances",
    "data": "information encoding — charts, badges, status dots, tags, meters",
    "decoration": "purely decorative fills / gradients with no semantic load",
}


class ColorBinding(BaseModel):
    kind: str  # accent | semantic | sentiment | neutral (open)
    role: str  # ground | surface | text | edge | interactive | data | decoration (open)
    reserved: bool  # True = this kind appears essentially ONLY in this role (deliberate discipline)
    evidence: str


class ColorApplication(BaseModel):
    bindings: list[ColorBinding] = []
    application_summary: str = ""

    def reserved_bindings(self) -> set[tuple[str, str]]:
        return {(b.kind, b.role) for b in self.bindings if b.reserved}

    def roles_of(self, kind: str) -> set[str]:
        return {b.role for b in self.bindings if b.kind == kind}


def source_dirs(root: str, comps: str) -> list[str]:
    """Directories to scan for a product's real style usages. Beyond src/components,
    identity lives in the app shell (src/app — layout/page composition styles) and shared
    style modules (src/lib, src/styles). Trial #3 had to RELOCATE its shell and palette into
    src/components to be seen, which is a gate artifact, not a real requirement. Existing,
    de-duped, deterministic order."""
    r = pathlib.Path(root)
    out, seen = [], set()
    for c in (comps, "src/app", "src/lib", "src/styles", "app", "components", "lib"):
        p = r / c
        if p.exists() and str(p) not in seen:
            seen.add(str(p))
            out.append(str(p))
    return out


def gather_facet_source(root: str, gcss: str, comps: str, facet: str) -> str:
    cfg = FACETS[facet]
    r = pathlib.Path(root)
    css = ""
    if (r / gcss).exists():
        raw = (r / gcss).read_text()
        css = "\n".join(l for l in raw.splitlines()
                        if any(k in l.lower() for k in cfg["css_keys"]))
        # design-token declarations (--x: value) so var() usages resolve for any facet, even
        # when the declaration line itself carries no facet keyword.
        tokens = "\n".join(l for l in raw.splitlines() if re.search(r"--[\w-]+\s*:\s*\S", l))
        if tokens:
            css = tokens + "\n" + css
        if facet == "color":  # tag the authoritative page ground so tonality isn't diluted
            g = page_ground(raw)
            if g:
                css = f"--bg-ground: {g};\n" + css
    pattern = r"(" + "|".join(cfg["grep"]) + r"):[^,;}]*"
    try:
        usages = subprocess.run(["grep", "-rhoE", pattern, *source_dirs(root, comps)],
                                capture_output=True, text=True, timeout=20).stdout
    except Exception:
        usages = ""
    lines = sorted(set(usages.splitlines()))[:60]
    from rubrick.tailwind import gather_tailwind  # Tailwind theme + utility classes (no-op if not TW)
    tw = gather_tailwind(root, comps, facet)
    return f"// {gcss} (relevant):\n{css}\n\n// usages:\n" + "\n".join(lines) + tw


_COLOR_PROPS = (r"(background|backgroundColor|color|fill|stroke|border|borderColor"
                r"|boxShadow|outline|WebkitTextStroke|accent-color|caret-color)")


def gather_color_application(root: str, gcss: str, comps: str) -> str:
    """Color-bearing declarations GROUPED BY component file — so component NAMES carry the
    role signal (Button/Link → interactive, Badge/Tag/Status → data, Card/Panel → surface,
    Nav/Header → chrome) that a flat property:value list loses. Plus the page ground. This is
    what lets the model infer color→role BINDINGS (how color is applied), not just which
    colors exist."""
    r = pathlib.Path(root)
    css = ""
    if (r / gcss).exists():
        raw = (r / gcss).read_text()
        keep = [l for l in raw.splitlines()
                if any(k in l.lower() for k in FACETS["color"]["css_keys"])]
        g = page_ground(raw)
        css = (f"// page ground: {g}\n" if g else "") + "\n".join(keep[:40])
    pattern = _COLOR_PROPS + r":[^,;}]*"
    by_file: dict[str, list[str]] = {}
    try:
        out = subprocess.run(["grep", "-rHoE", pattern, *source_dirs(root, comps)],
                             capture_output=True, text=True, timeout=20).stdout
        for line in out.splitlines():
            path, _, decl = line.partition(":")
            name = pathlib.Path(path).name
            if decl:
                by_file.setdefault(name, [])
                if decl not in by_file[name] and len(by_file[name]) < 12:
                    by_file[name].append(decl)
    except Exception:
        pass
    blocks = [f"// {name}:\n" + "\n".join(decls)
              for name, decls in sorted(by_file.items())[:40]]
    from rubrick.tailwind import gather_tailwind
    tw = gather_tailwind(root, comps, "color")
    return f"// {gcss} (relevant):\n{css}\n\n// color usage by component:\n" + "\n\n".join(blocks) + tw


_JSX_OPEN = re.compile(r"<[A-Za-z][\w.]*[\s/>]")


def content_density(root: str, comps: str) -> float | None:
    """MAGNITUDE / felt density — how MUCH the product renders, per component. The spacing
    metric captures how TIGHT the layout is; this captures how PACKED it is. Two trials showed
    the gate passing an airy build (empty center) against a dense source because presence-of-
    density-moves ≠ felt density. Content per component (JSX elements + list-renders, which
    each render many rows) separates dense sources (rich products run ~60–110) from sparse builds
    (13-26) even per-component, so it's domain-fair — it demands packed components, not a
    specific data volume."""
    d = pathlib.Path(root) / comps
    if not d.exists():
        return None
    files = list(d.rglob("*.tsx"))
    if not files:
        return None
    jsx = maps = 0
    for f in files:
        try:
            t = f.read_text()
        except Exception:
            continue
        jsx += len(_JSX_OPEN.findall(t))
        maps += t.count(".map(")
    return round((jsx + maps * 10) / len(files), 1)


def _client():
    key = _load_key()
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY — style facet extraction needs a real generation.")
    return anthropic.Anthropic(api_key=key)


def _vocab(facet: str) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in FACETS[facet]["vocab"].items())


_EXTRACT = """Here are a product's {desc} facts (relevant CSS + usages, and — if a \
Tailwind app — its tailwind.config theme + utility classes). Interpret ALL of these: a \
Tailwind product expresses this facet through utility classes and a config theme, not \
CSS declarations. The config's custom palette / scale IS the product's identity.

Extract, GROUNDED in the facts:
- features: the non-generic, identity-bearing moves present, each {{feature, evidence}}. Vocabulary:
{vocab}
- novel_features: any distinctive move that fits NO vocabulary feature (name + evidence) — do not force-fit or drop.
- identity_summary: one line naming this product's {facet} posture.

Focus on what is DISTINCTIVE / non-generic (a product-system identity signal), NOT token values. Facts:
{source}"""

_DEFAULT = """For a general web/app UI with no special design direction, which of \
these {facet} features does a competent DEFAULT have (usually none or few)?
{vocab}
Do not add distinctive moves unless genuinely the obvious default."""


import re

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_RGB_FN = re.compile(r"rgba?\(\s*([\d.]+)\s*[, ]\s*([\d.]+)\s*[, ]\s*([\d.]+)")
_HSL_FN = re.compile(r"hsla?\(\s*([\d.]+)\s*[, ]\s*([\d.]+)%\s*[, ]\s*([\d.]+)%")


def _norm_hex(h: str) -> str:
    h = h.lower().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return "#" + "".join(f"{max(0, min(255, c)):02x}" for c in (r, g, b))


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    h, s, l = h % 360 / 360, s / 100, l / 100
    if s == 0:
        v = round(l * 255)
        return v, v, v
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def ch(t: float) -> int:
        t %= 1
        if t < 1 / 6:
            c = p + (q - p) * 6 * t
        elif t < 1 / 2:
            c = q
        elif t < 2 / 3:
            c = p + (q - p) * (2 / 3 - t) * 6
        else:
            c = p
        return round(c * 255)

    return ch(h + 1 / 3), ch(h), ch(h - 1 / 3)


def _all_colors(source: str) -> list[str]:
    """Every color as a normalized #rrggbb, parsed from hex, rgb()/rgba(), AND hsl()/hsla().
    Alpha is dropped (identity is hue/tone, not opacity). Trial #3: an alpha-based palette
    written as rgba()/hsl() was invisible to the hex-only reader, so palette_coherence fell
    to a false 0.0 regardless of how disciplined the palette actually was. De-dup, ordered.
    Custom-property colors (var(--accent)) are resolved first, same as spacing tokens."""
    from rubrick.resolve import resolve_values
    source = resolve_values(source)
    out = [_norm_hex(h) for h in _HEX.findall(source)]
    for r, g, b in _RGB_FN.findall(source):
        out.append(_rgb_to_hex(round(float(r)), round(float(g)), round(float(b))))
    for h, s, l in _HSL_FN.findall(source):
        out.append(_rgb_to_hex(*_hsl_to_rgb(float(h), float(s), float(l))))
    return list(dict.fromkeys(out))


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _luminance(h: str) -> float:
    r, g, b = (c / 255 for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


_GROUND_SELECTORS = ("body", ":root", "html", "main", "#root", "#__next", "#app", ".app")
_GROUND_TOKENS = ("--bg", "--background", "--ground", "--canvas", "--page", "--surface", "--base")


def page_ground(css_text: str) -> str | None:
    """The authoritative page GROUND color — the background on body / :root / html / the app
    root, or a --background-style var. This is the mode signal; the mean of every panel's
    background is diluted (a light UI with dark cards averages to ~mid). Reads real selector
    blocks, so it survives dark panels sitting on a light page."""
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css_text):
        sel = m.group(1).lower()
        if any(s in sel for s in _GROUND_SELECTORS):
            for decl in m.group(2).split(";"):
                if "background" in decl.lower():
                    cols = _all_colors(decl)
                    if cols:
                        return cols[0]
    return None


def background_tonality(source: str) -> float | None:
    """Luminance (0=black … 1=white) of the product's GROUND. A light product (~>0.6) and a
    dark product (~<0.4) are categorically different identities even with identical accent
    logic (a dark build checked against a light system — posture must push back on the polarity flip).
    Mode polarity is a posture-checked trait, not a free value. Ground tokens (--background,
    an injected --bg-ground) win over incidental panel backgrounds so a light page with dark
    cards still reads light; foreground text tone is excluded (background lines only)."""
    ground, panels = [], []
    for line in source.splitlines():
        low = line.lower()
        is_ground = any(t in low for t in _GROUND_TOKENS)
        if not (is_ground or "background" in low):
            continue
        lums = [_luminance(h) for h in _all_colors(line)]
        (ground if is_ground else panels).extend(lums)
    use = ground or panels
    return round(sum(use) / len(use), 2) if use else None


def _palette_anchors(source: str, chroma_min: int = 32) -> list[str]:
    """The SIGNATURE palette — the distinctive (saturated) hexes a native feature must
    reuse. Neutrals (greys / near-black / near-white) are EXCLUDED: everyone has chrome;
    identity lives in the saturated accents/status/sentiment colors. Deterministic regex,
    no model call — so a candidate's palette is free to re-observe."""
    out = []
    for h in _all_colors(source):
        r, g, b = _rgb(h)
        if max(r, g, b) - min(r, g, b) >= chroma_min:  # saturated → identity-bearing
            out.append(h)
    return out


def palette_max_chroma(source: str) -> int | None:
    """The boldest accent's chroma (max-min RGB) — the magnitude behind `expressive-accent`.
    A hot #ff7411 (chroma ~238) vs a muted slate (chroma ~40) are utterly different color
    identities even though both 'have an accent'. Deterministic, reuses the anchor chroma."""
    chromas = []
    for h in _all_colors(source):
        r, g, b = _rgb(h)
        c = max(r, g, b) - min(r, g, b)
        if c >= 32:  # skip neutrals
            chromas.append(c)
    return max(chromas) if chromas else None


_PX = re.compile(r"(\d+(?:\.\d+)?)px")
_TW_SPACE = re.compile(r"\b(?:p[xytblr]?|m[xytblr]?|gap|space-[xy])-(\d+(?:\.\d+)?)\b")
_TW_SPACE_ARB = re.compile(r"\b(?:p[xytblr]?|m[xytblr]?|gap)-\[(\d+(?:\.\d+)?)px\]")


_SPACE_PROP = re.compile(r"(?:padding|margin|gap|rowGap|columnGap|row-gap|column-gap)"
                         r"[A-Za-z]*\s*:\s*([^,;}\n]+)", re.I)
_NUM = re.compile(r"(\d{1,3}(?:\.\d+)?)")


def _spacing_values(source: str) -> list[float]:
    from rubrick.resolve import resolve_values
    source = resolve_values(source)  # var(--space-4) / GAP → literals (token scales are the discipline)
    vals = []
    for mt in _SPACE_PROP.finditer(source):
        # every number in the value — matches `10px`, quoted `"6px 10px"`, AND React bare
        # numbers (`gap: 10` == 10px), which the px-only reader missed → empty density metrics.
        vals += [float(n) for n in _NUM.findall(mt.group(1))]
    vals += [float(m) * 4 for m in _TW_SPACE.findall(source)]
    vals += [float(m) for m in _TW_SPACE_ARB.findall(source)]
    return [v for v in vals if 2 <= v <= 80]


def median_spacing(source: str) -> float | None:
    """Median gap/padding in px — a (soft) proxy for `information-dense`: tight products
    pack at ~4-10px, airy ones at ~24-48px."""
    vals = sorted(_spacing_values(source))
    if not vals:
        return None
    n = len(vals)
    return round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2, 1)


def spacing_discipline(source: str) -> float | None:
    """DISCIPLINE axis (systematicity, not expression): how rigorously the product applies
    a spacing SYSTEM. High = few distinct values on a clean grid (a disciplined scale, the
    mark of intentional restraint); low = many ad-hoc values (undesigned/generic). This is
    how a restrained product earns identity at low delta-from-generic, and how a candidate
    that copies the loud moves but spaces sloppily gets caught."""
    distinct = sorted(set(round(v) for v in _spacing_values(source) if v >= 4))
    if len(distinct) < 3:
        return None
    # coherence to a grid — the tell of ad-hoc spacing is odd/off-scale values (5,9,11,17…).
    # base 2/4/8 so a strict Tailwind scale (with its 1.5/2.5 half-steps → 6,10) still reads
    # disciplined; a generic app's arbitrary paddings drag it down.
    return round(max(sum(1 for v in distinct if v % b == 0) / len(distinct) for b in (2, 4, 8)), 2)


_TW_SHADOW = {"shadow-md": 6, "shadow-lg": 15, "shadow-xl": 25, "shadow-2xl": 50}


def max_shadow_blur(source: str) -> float | None:
    """Max shadow depth in px — the magnitude behind soft-floating / dramatic shadows.
    Largest px in box-shadow lines + Tailwind shadow-lg/xl/2xl scale. Deep elevation
    (40px+) vs a subtle 2-4px lift are different depth languages."""
    vals = []
    for line in source.splitlines():
        if "shadow" in line.lower():
            vals += [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)px", line)]
    for name, px in _TW_SHADOW.items():
        if re.search(r"\b" + name + r"\b", source):
            vals.append(px)
    vals = [v for v in vals if 0 <= v <= 200]
    return max(vals) if vals else None


def _all_hexes(source: str) -> list[str]:
    return _all_colors(source)


def _hex_hue(h: str) -> float:
    r, g, b = (int(h[1:3], 16) / 255, int(h[3:5], 16) / 255, int(h[5:7], 16) / 255)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0.0
    d = mx - mn
    hh = ((g - b) / d) % 6 if mx == r else (b - r) / d + 2 if mx == g else (r - g) / d + 4
    return hh * 60


def neutral_ramp(source: str) -> list[str]:
    """The specific NEUTRAL hexes — the greys/slates `_palette_anchors` discards (chroma<32).
    For a RESTRAINED product the neutral ramp IS the identity (a warm-grey vs a cool-slate are
    different products); needed for native reproduction. Excludes pure black/white."""
    out = []
    for h in _all_hexes(source):
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        if max(r, g, b) - min(r, g, b) < 32 and 8 < max(r, g, b) < 248:
            out.append(h)
    return out


def palette_coherence(source: str) -> float | None:
    """DISCIPLINE axis for color: are the SATURATED colors organized into hue FAMILIES
    (systematic scales/roles — an accent with steps, semantic status colors) vs scattered
    unrelated singletons (a lone blue + green + red = ad-hoc)? Fraction of saturated colors
    that belong to a hue family of ≥2. (Neutrals judged separately via the neutral ramp;
    a single-accent product returns None — too few to judge.)"""
    sat = []
    for h in _all_hexes(source):
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        if max(r, g, b) - min(r, g, b) >= 32:
            sat.append(h)
    if len(sat) < 2:
        return None
    fam: dict = {}
    for h in sat:
        fam.setdefault(int(_hex_hue(h) // 30), []).append(h)
    in_family = sum(len(m) for m in fam.values() if len(m) >= 2)
    return round(in_family / len(sat), 2)


def facet_aesthetic(facet: str, obs: FacetObs, source: str) -> dict:
    """The CONCRETE aesthetics for a facet (native mode): per-move grounded evidence
    (free, every facet) + value anchors where exact reuse is meaningful (color palette).
    For color we ALSO retain the neutral ramp — a restrained product's identity is its
    specific greys/slates, which the saturated-only anchors would otherwise discard."""
    moves = {f.feature: f.evidence for f in obs.features}
    out = {"anchors": _palette_anchors(source) if facet == "color" else [], "moves": moves}
    if facet == "color":
        nr = neutral_ramp(source)
        if nr:
            out["neutral_ramp"] = nr
    return out


def candidate_facet_concrete(facet: str, source: str) -> dict:
    """A candidate's concrete for a facet, shaped for StyleRecord.check_native."""
    return {"anchors": _palette_anchors(source) if facet == "color" else []}


def extract_facet(facet: str, source: str, key_id: str, *, use_cache: bool = True) -> FacetObs:
    # promoted facet moves become KNOWN vocab (so they're grounded, not novel) and salt
    # the cache so a promotion takes effect on the next extraction.
    promoted = learned.promoted_facets(facet)
    ck = f"{facet}:{key_id}"
    if promoted:
        h = hashlib.sha1(json.dumps(promoted, sort_keys=True).encode()).hexdigest()[:8]
        ck = f"{facet}:{key_id}::{h}"
    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    if use_cache and ck in cache:
        return FacetObs.model_validate(cache[ck])
    vocab = {**FACETS[facet]["vocab"], **promoted}
    vocab_str = "\n".join(f"- {k}: {v}" for k, v in vocab.items())
    resp = _client().messages.parse(
        model="claude-opus-4-8", max_tokens=2500, thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _EXTRACT.format(
            desc=FACETS[facet]["desc"], vocab=vocab_str, facet=facet, source=source)}],
        output_format=FacetObs)
    cache[ck] = resp.parsed_output.model_dump()
    _CACHE.write_text(json.dumps(cache, indent=2))
    return resp.parsed_output


_APPLY_EXTRACT = """Here is how a product applies COLOR across its components — color-bearing \
declarations grouped by file (a file's NAME signals its role: Button/Link/Menu → interactive, \
Badge/Tag/Status/Chart → data, Card/Panel/Sheet → surface, Nav/Header/Sidebar → chrome/surface), \
plus its page ground and (if Tailwind) its theme.

Determine, GROUNDED in these facts, the product's color APPLICATION — how each KIND of color is \
DEPLOYED onto ROLES. This is the disposition that makes a palette feel like one product (e.g. \
"the accent is reserved for interaction, never decoration; neutrals carry all structure"), NOT a \
palette listing and NOT a hex→component map.

Color kinds:
{kinds}
Roles (where a color lands):
{roles}

Output:
- bindings: each meaningful kind→role deployment as {{kind, role, reserved, evidence}}. Set \
reserved=true ONLY when that kind appears essentially in that ONE role — a deliberate discipline. \
A generic app spreads its accent across links, headings, AND borders ad-hoc (reserved=false \
everywhere); a product with identity RESERVES (accent only on interaction; saturated color only \
ever marks state). Be conservative: reserved=true is a strong claim about restraint.
- application_summary: one line naming how this product deploys color.

Facts:
{source}"""


def extract_color_application(source: str, key_id: str, *, use_cache: bool = True) -> ColorApplication:
    """The color-application disposition (kind→role bindings + reservation). Content-keyed
    cache (key_id carries the source hash) so a candidate re-observes deterministically, same
    as the facet moves."""
    ck = f"color-application:{key_id}"
    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    if use_cache and ck in cache:
        return ColorApplication.model_validate(cache[ck])
    kinds = "\n".join(f"- {k}: {v}" for k, v in COLOR_KINDS.items())
    roles = "\n".join(f"- {k}: {v}" for k, v in COLOR_ROLES.items())
    resp = _client().messages.parse(
        model="claude-opus-4-8", max_tokens=4500, thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _APPLY_EXTRACT.format(
            kinds=kinds, roles=roles, source=source)}],
        output_format=ColorApplication)
    cache[ck] = resp.parsed_output.model_dump()
    _CACHE.write_text(json.dumps(cache, indent=2))
    return resp.parsed_output


def generate_facet_default(facet: str, *, use_cache: bool = True) -> FacetDefault:
    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    ck = f"{facet}:__default__"
    if use_cache and ck in cache:
        return FacetDefault.model_validate(cache[ck])
    resp = _client().messages.parse(
        model="claude-opus-4-8", max_tokens=800, thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _DEFAULT.format(facet=facet, vocab=_vocab(facet))}],
        output_format=FacetDefault)
    cache[ck] = resp.parsed_output.model_dump()
    _CACHE.write_text(json.dumps(cache, indent=2))
    return resp.parsed_output
