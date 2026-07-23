"""Typography extraction (Mode B) + baseline, for the type facet.

Gathers a product's real type facts — the font files it ships, its global font
setup, and sample family/size/weight/case usages — and the agent extracts the
faces + non-generic type features, grounded. Baseline = the generic default type
a competent build would use with no special direction.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from rubrick import paths
import subprocess

import anthropic

from rubrick import learned
from rubrick.baseline import _load_key
from rubrick.typography import TYPE_FEATURE_DESCRIPTIONS, DefaultType, TypeObservation

_CACHE = paths.cache_dir() / "type_cache.json"


def gather_type_source(root: str, globals_css: str, components_glob: str) -> str:
    r = pathlib.Path(root)
    fonts = sorted(p.name for p in (r / "public" / "fonts").glob("*")
                   if p.suffix in {".otf", ".woff", ".woff2", ".ttf"})
    css = ""
    cp = r / globals_css
    if cp.exists():
        # keep any line whose declaration is type-defining — NOT just "font". The old
        # "font"-only filter dropped letter-spacing / text-transform / line-height, so
        # treated-microtype (uppercase + wide tracking, defined in a CSS class) was
        # invisible and had to be inlined to be seen (trial #2). These are the moves.
        css = "\n".join(l for l in cp.read_text().splitlines()
                        if any(k in l for k in (
                            "font", "@theme", "@font-face", "--type", "--track", "--weight",
                            "letter-spacing", "text-transform", "line-height",
                            "text-decoration", "text-align")))
    # sample type usages via ripgrep-ish grep (inline style props)
    try:
        from rubrick.style_facets import source_dirs
        usages = subprocess.run(
            ["grep", "-rhoE",
             r"(fontFamily|fontSize|fontWeight|fontStyle|letterSpacing|textTransform"
             r"|lineHeight|textDecoration|fontVariant|fontFeatureSettings):[^,}]*",
             *source_dirs(root, components_glob)],
            capture_output=True, text=True, timeout=20).stdout
    except Exception:
        usages = ""
    usage_lines = sorted(set(usages.splitlines()))[:50]
    from rubrick.tailwind import gather_tailwind  # Tailwind theme + utility classes (no-op if not TW)
    tw = gather_tailwind(root, components_glob, "typography")
    return (f"// font files shipped:\n{fonts}\n\n"
            f"// global font setup:\n{css}\n\n"
            f"// sample type usages:\n" + "\n".join(usage_lines) + tw)


_EXTRACT = """Here are a product's TYPOGRAPHY facts — the font files it ships, its \
global font setup, sample type usages, and (if a Tailwind app) its tailwind.config \
theme + utility classes. Interpret ALL of these — a Tailwind product expresses type \
through `font-*` / `text-*` / `tracking-*` / `uppercase` utilities and a config \
`fontFamily`/`fontSize` theme, not CSS declarations. Custom faces named in the config \
are real faces.

Extract, GROUNDED in the facts:
- faces: each typeface, its kind (system-font | custom), role (display | body | \
label), with evidence.
- features: the non-generic, identity-bearing type moves present, each as \
{{feature, evidence}}. Vocabulary:
{vocab}
- novel_features: any distinctive type move that fits NO vocabulary feature \
(name + evidence) — do not force-fit or drop.

Focus on what is DISTINCTIVE / non-generic (a product-system identity signal), \
NOT a full type scale. Facts:
{source}"""

_DEFAULT = """For a general web/app UI with no special design direction, what \
DEFAULT typography would a competent engineer use? List which of these features \
a plain default has (usually none or few — system face, simple scale, regular \
weights):
{vocab}
Do not add expressive faces, extreme contrast, graphic type, or detailed faces \
unless they are genuinely the obvious default."""


def _client():
    key = _load_key()
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY — typography extraction needs a real generation.")
    return anthropic.Anthropic(api_key=key)


def _vocab():
    return "\n".join(f"- {k}: {v}" for k, v in TYPE_FEATURE_DESCRIPTIONS.items())


def extract_typography(source: str, key_id: str, *, use_cache: bool = True) -> TypeObservation:
    promoted = learned.promoted_facets("typography")  # promoted type moves -> known vocab
    ck = f"obs:{key_id}"
    if promoted:
        ck += "::" + hashlib.sha1(json.dumps(promoted, sort_keys=True).encode()).hexdigest()[:8]
    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    if use_cache and ck in cache:
        return TypeObservation.model_validate(cache[ck])
    vocab = "\n".join(f"- {k}: {v}" for k, v in {**TYPE_FEATURE_DESCRIPTIONS, **promoted}.items())
    resp = _client().messages.parse(
        model="claude-opus-4-8", max_tokens=2500, thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _EXTRACT.format(vocab=vocab, source=source)}],
        output_format=TypeObservation)
    result = resp.parsed_output
    cache[ck] = result.model_dump()
    _CACHE.write_text(json.dumps(cache, indent=2))
    return result


import re

# default Tailwind text-* scale in px — resolves named size utilities to numbers.
# (custom tailwind.config fontSize overrides are a smaller follow-on; usage via these
# standard classes + px/rem literals + arbitrary text-[Npx] covers the common cases.)
_TW_TEXT = {"text-xs": 12, "text-sm": 14, "text-base": 16, "text-lg": 18, "text-xl": 20,
            "text-2xl": 24, "text-3xl": 30, "text-4xl": 36, "text-5xl": 48, "text-6xl": 60,
            "text-7xl": 72, "text-8xl": 96, "text-9xl": 128}
_FS = re.compile(r'font-?size"?\s*[:=]\s*"?\s*([\d.]+)\s*(px|rem|em)?', re.I)
_TW_ARB = re.compile(r'text-\[([\d.]+)(px|rem)\]')
_LS = re.compile(r'letter-?spacing"?\s*[:=]\s*"?\s*(-?[\d.]+)\s*(em|px|rem)?', re.I)
_TW_TRACK = {"tracking-tighter": -0.05, "tracking-tight": -0.025, "tracking-normal": 0.0,
             "tracking-wide": 0.025, "tracking-wider": 0.05, "tracking-widest": 0.1}


_FW = re.compile(r'font-?weight"?\s*[:=]\s*"?\s*(\d{3})', re.I)
_TW_WEIGHT = {"font-thin": 100, "font-extralight": 200, "font-light": 300,
              "font-normal": 400, "font-medium": 500, "font-semibold": 600,
              "font-bold": 700, "font-extrabold": 800, "font-black": 900}


def max_weight(source: str) -> int | None:
    """The heaviest font-weight in the source — the magnitude behind `expressive-weight`.
    A product that ships/uses 900 black is a different identity from one that tops out at
    600 semibold, even though both 'have weight'."""
    vals = [int(m) for m in _FW.findall(source)]
    for name, w in _TW_WEIGHT.items():
        if re.search(r"\b" + name + r"\b", source):
            vals.append(w)
    if re.search(r'font-?weight"?\s*[:=]\s*"?\s*bold\b', source, re.I):
        vals.append(700)
    vals = [v for v in vals if 100 <= v <= 900]
    return max(vals) if vals else None


def max_tracking(source: str) -> float | None:
    """The widest letter-spacing in the source, in em — the magnitude behind
    `treated-microtype`. From CSS/inline `letter-spacing` (px→em approx) and Tailwind
    tracking-* utilities. Wide tracking is the 'treated' signature; normal tracking
    means the labels aren't actually treated even if small."""
    vals = []
    for v, unit in _LS.findall(source):
        x = float(v)
        vals.append(x / 16 if unit and unit.lower() == "px" else x)  # em (px≈/16)
    for name, em in _TW_TRACK.items():
        if re.search(r"\b" + name + r"\b", source):
            vals.append(em)
    pos = [v for v in vals if v > 0]
    return round(max(pos), 3) if pos else None


def extract_font_sizes(source: str) -> list[float]:
    """All intentional font sizes in the gathered type source, normalized to px —
    from CSS `font-size`, inline `fontSize`, `clamp()` bounds, and Tailwind text-*
    (named scale + arbitrary `text-[Npx]`). Filtered to a plausible font-size range."""
    sizes: list[float] = []
    for val, unit in _FS.findall(source):
        v = float(val)
        sizes.append(v * 16 if unit and unit.lower() in ("rem", "em") else v)
    for val, unit in _TW_ARB.findall(source):
        sizes.append(float(val) * 16 if unit == "rem" else float(val))
    for name, px in _TW_TEXT.items():
        if re.search(r"\b" + name + r"\b", source):
            sizes.append(px)
    for clamp in re.findall(r"clamp\([^)]*\)", source):
        sizes += [float(r) * 16 for r in re.findall(r"([\d.]+)rem", clamp)]
        sizes += [float(p) for p in re.findall(r"([\d.]+)px", clamp)]
    return [s for s in sizes if 5 <= s <= 400]  # drop junk (0, huge non-type values)


def facet_metrics(facet: str, features: set[str], source: str) -> dict:
    """Calibrated QUANTITATIVE magnitudes for a facet (Phase 2 depth), computed
    deterministically from source. Only for moves actually present. Typography today:
    the scale-contrast ratio when `extreme-scale-contrast` is captured."""
    m: dict = {}
    if facet == "typography":
        if "extreme-scale-contrast" in features:
            r = scale_contrast_ratio(source)
            if r:
                m["scale_contrast_ratio"] = r
        if "treated-microtype" in features:
            t = max_tracking(source)
            if t:
                m["micro_tracking_em"] = t
        if "expressive-weight" in features:
            w = max_weight(source)
            if w:
                m["max_weight"] = w
    elif facet == "color":
        from rubrick.style_facets import background_tonality, palette_coherence, palette_max_chroma
        if "expressive-accent" in features:
            c = palette_max_chroma(source)
            if c:
                m["accent_chroma"] = c
        pc = palette_coherence(source)  # DISCIPLINE axis — computed regardless of moves
        if pc is not None:
            m["palette_coherence"] = pc
        bt = background_tonality(source)  # mode polarity (light vs dark ground) — posture trait
        if bt is not None:
            m["background_tonality"] = bt
    elif facet == "density":
        from rubrick.style_facets import median_spacing, spacing_discipline
        if "information-dense" in features:
            sp = median_spacing(source)
            if sp:
                m["density_spacing_px"] = sp
        d = spacing_discipline(source)  # DISCIPLINE axis — computed regardless of moves
        if d is not None:
            m["spacing_discipline"] = d
    elif facet == "elevation" and ({"soft-floating-shadows", "dramatic-shadow"} & features):
        from rubrick.style_facets import max_shadow_blur
        b = max_shadow_blur(source)
        if b:
            m["shadow_depth_px"] = b
    return m


def scale_contrast_ratio(source: str) -> float | None:
    """The type system's scale-contrast MAGNITUDE: largest display size / smallest
    label size. The quantitative character behind `extreme-scale-contrast` — a 15x
    ratio and a 1.3x ratio both 'have contrast' but are utterly different type."""
    sizes = extract_font_sizes(source)
    if len(sizes) < 2:
        return None
    return round(max(sizes) / min(sizes), 1)


def type_aesthetic(obs: TypeObservation) -> dict:
    """The CONCRETE typographic identity, retained from the same observation we
    already make (faces + per-move evidence) — the aesthetic layer for native-feature
    mode. `anchors` are the identity-critical values a native feature MUST reuse: the
    product's CUSTOM faces (system faces aren't identity anchors — anyone has those)."""
    faces = {f.role: f.name for f in obs.faces}
    anchors = [f.name for f in obs.faces if f.kind != "system-font"]
    moves = {f.feature: f.evidence for f in obs.features}
    return {"values": {"faces": faces}, "anchors": anchors, "moves": moves}


def candidate_type_concrete(obs: TypeObservation) -> dict:
    """A candidate's concrete typography, shaped to compare against a record's
    `concrete` via StyleRecord.check_native (anchors = its custom faces)."""
    return {"anchors": [f.name for f in obs.faces if f.kind != "system-font"],
            "values": {"faces": {f.role: f.name for f in obs.faces}}}


def generate_type_default(*, use_cache: bool = True) -> DefaultType:
    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    if use_cache and "default" in cache:
        return DefaultType.model_validate(cache["default"])
    resp = _client().messages.parse(
        model="claude-opus-4-8", max_tokens=1000, thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _DEFAULT.format(vocab=_vocab())}],
        output_format=DefaultType)
    result = resp.parsed_output
    cache["default"] = result.model_dump()
    _CACHE.write_text(json.dumps(cache, indent=2))
    return result
