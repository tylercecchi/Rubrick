"""The SUBTRACTIVE axis — identity by deliberate omission (negative space).

A huge amount of identity is what a product deliberately REFUSES — one accent and no more,
no drop shadows, no ambient motion, no status badges. An additive-only reader is blind to
it: a deliberately shadowless product looks the same as one that just forgot shadows.

ONE mechanism for every omission. An ABSENCE DETECTOR is data, in one of two forms:

  pattern  {"all": [regex…], "none": […], "flags": "", "scope": "source"|"element"}
           — present when the spec matches (rubrick.detectors.run_spec);
  measure  {"measure": <primitive>, "zeroed": "<cond>", "added": "<cond>"}
           — a deterministic MEASUREMENT (counts, thresholds) a regex can't express:
             "the product has one hue family", "no shadow deeper than 8px". The gap
             between `zeroed` and `added` keeps borderline values from flip-flopping.

The REGISTRY is the built-ins below (pre-admitted starter entries, revocable/overridable
via learned.json like anything learned) plus every ACTIVE learned `absence:*` detector
(promoted through the open channel, rubrick.absences). There are no privileged "seeds":
everything is captured by the SAME rule and checked by the SAME path.

  CAPTURE (compile) — the true diff: the product ZEROES the thing AND the generated
    generic twin of this product HAS it. Zeroed-but-the-twin-lacks-it is uncertain (a
    refusal, or just never needed?) — only the designer can say, so it goes to review
    (confirm_intent) and is NOT captured unless confirmed.
  CHECK — violation by EXCESS: the candidate shows the thing (`added`). Detectors are
    embedded in the records, so the check is deterministic, self-contained, LLM-free.
"""

from __future__ import annotations

import pathlib
import re

from rubrick.style_facets import _all_colors, _hex_hue, max_shadow_blur, palette_max_chroma

_GENERIC_FALLBACK_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "inherit",
                           "-apple-system", "blinkmacsystemfont", "ui-sans-serif", "ui-monospace"}


# --- the measurement source: one reading of the product, every spelling ---------------
# A measure must read the SAME styling the same way however it is written: literal CSS,
# design tokens (`border-radius: var(--radius)`), inline React styles (`borderRadius: 12`)
# or Tailwind utilities (`rounded-xl`). A literal-only reader made a token-based product
# read as "no rounding" — a false refusal at capture, and a missed add-back at check (a
# flat system can't see `shadow-lg`). So every measure reads one normalized source: the
# product's full source with custom properties / numeric constants resolved
# (rubrick.resolve) plus Tailwind utilities translated into the equivalent CSS.

_TW_RADIUS = {"none": 0, "sm": 2, "": 4, "md": 6, "lg": 8, "xl": 12, "2xl": 16, "3xl": 24, "full": 100}
_TW_SHADOW = {"sm": 2, "": 3, "md": 6, "lg": 15, "xl": 25, "2xl": 50}
_TW_WEIGHT = {"thin": 100, "extralight": 200, "light": 300, "normal": 400, "medium": 500,
              "semibold": 600, "bold": 700, "extrabold": 800, "black": 900}
_TW_HUE = {"red": "#ef4444", "orange": "#f97316", "amber": "#f59e0b", "yellow": "#eab308",
           "lime": "#84cc16", "green": "#22c55e", "emerald": "#10b981", "teal": "#14b8a6",
           "cyan": "#06b6d4", "sky": "#0ea5e9", "blue": "#3b82f6", "indigo": "#6366f1",
           "violet": "#8b5cf6", "purple": "#a855f7", "fuchsia": "#d946ef", "pink": "#ec4899",
           "rose": "#f43f5e"}
_TW_PREFIX = r"(?<![\w-])(?:[a-z0-9]+:)*"   # variants like hover: md: dark:


def tailwind_as_css(source: str) -> str:
    """Synthetic CSS declarations for the Tailwind utilities in `source`, so the literal
    measures read them. Deterministic; unknown utilities are ignored."""
    out = []
    for side, size in re.findall(_TW_PREFIX + r"rounded(-[trblse]{1,2})?(?:-(none|sm|md|lg|xl|2xl|3xl|full))?(?![\w-])", source):
        out.append(f"border-radius: {_TW_RADIUS[size]}px;")
    out += [f"border-radius: {n}px;" for n in re.findall(_TW_PREFIX + r"rounded(?:-[trblse]{1,2})?-\[(\d+(?:\.\d+)?)px\]", source)]
    for size in re.findall(_TW_PREFIX + r"shadow(?:-(sm|md|lg|xl|2xl))?(?![\w-])", source):
        out.append(f"box-shadow: 0 0 {_TW_SHADOW[size]}px rgba(0,0,0,.1);")
    if re.search(_TW_PREFIX + r"bg-(?:gradient|linear|radial|conic)-", source):
        out.append("background-image: linear-gradient(tw);")
    out += [f"font-weight: {_TW_WEIGHT[w]};" for w in
            re.findall(_TW_PREFIX + r"font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)(?![\w-])", source)]
    out += [f"font-family: {f.strip()};" for f in re.findall(r"font-\[['\"]?([A-Za-z][\w ]+?)['\"]?[,\]]", source)]
    for hue, shade in re.findall(_TW_PREFIX + r"(?:bg|text|border|ring|from|via|to|fill|stroke|outline|decoration|accent)"
                                 r"-(" + "|".join(_TW_HUE) + r")-(\d{2,3})(?![\w-])", source):
        if int(shade) >= 300:  # 50-200 are tints of the family, not a use of the hue
            out.append(f"color: {_TW_HUE[hue]};")
    if re.search(_TW_PREFIX + r"animate-(spin|ping|pulse|bounce)(?![\w-])", source):
        out.append("animation: tw 1s infinite;")
    return "\n".join(out)


_STYLE_SUFFIXES = {".tsx", ".ts", ".jsx", ".js", ".css", ".scss"}
_TW_CONFIGS = ("tailwind.config.ts", "tailwind.config.js", "tailwind.config.mjs", "tailwind.config.cjs")


def _style_files(repo: str, gcss: str, comps: str) -> list[pathlib.Path]:
    """Every style-bearing file the product reads from: the global stylesheet, ALL
    source files under the shared source dirs (theme constants live in .ts files, not
    only .tsx), and a Tailwind config — sorted, deterministic, uncapped."""
    from rubrick.style_facets import source_dirs
    r = pathlib.Path(repo)
    files = [r / gcss] if (r / gcss).exists() else []
    seen = {f.resolve() for f in files}
    for d in source_dirs(repo, comps):
        for f in sorted(pathlib.Path(d).rglob("*")):
            if f.suffix in _STYLE_SUFFIXES and f.is_file() and "node_modules" not in f.parts \
                    and f.resolve() not in seen:
                seen.add(f.resolve())
                files.append(f)
    files += [r / c for c in _TW_CONFIGS if (r / c).exists()]
    return files


def measure_source(repo: str, gcss: str, comps: str) -> str:
    """The normalized source every measure reads (compile, twin and check alike)."""
    from rubrick.resolve import resolve_values
    parts = []
    for f in _style_files(repo, gcss, comps):
        try:
            parts.append(f.read_text())
        except Exception:
            continue
    src = resolve_values("\n".join(parts))
    return src + "\n/* tailwind */\n" + tailwind_as_css(src)


def _ambient_motion(source: str) -> bool:
    return bool(re.search(r"@keyframes|animation\s*:|animation-name|\binfinite\b|"
                          r"repeat\s*:\s*Infinity", source, re.I))


def _saturated_hue_families(source: str) -> set:
    fams = set()
    for h in _all_colors(source):
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        if max(r, g, b) - min(r, g, b) >= 32:  # saturated
            fams.add(int(_hex_hue(h) // 30))
    return fams


def _radius(src: str):
    vals = []
    for v in re.findall(r"(?:border-radius|borderRadius)\s*:\s*([^;,}\n]+)", src, re.I):
        vals += [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)", v)]
    vals = [v for v in vals if v <= 200]
    return max(vals) if vals else None


def _families(src: str):
    """Distinct NAMED typefaces — CSS/inline font-family (first family of each stack),
    @font-face names, next/font imports. None when none is named: unknown, never a
    silent 'one face' (that read every token-defined product as single-face)."""
    fams = set()
    for m in re.findall(r"font-?family\s*:\s*([^;}\n]+)", src, re.I):
        first = m.split(",")[0].strip().strip("\"'` ")
        if first:
            fams.add(first.lower())
    for imp in re.findall(r"import\s*\{([^}]*)\}\s*from\s*['\"]next/font/google['\"]", src):
        fams |= {n.strip().replace("_", " ").lower() for n in imp.split(",") if n.strip()}
    fams = {f for f in fams if f and f not in _GENERIC_FALLBACK_FONTS and not f.startswith("var(")}
    return len(fams) if fams else None


def _weights(src: str) -> int:
    ws = {w.lower() for w in re.findall(r"font-?weight\s*:\s*[\"']?(\d{3}|bold|normal)", src, re.I)}
    return len(ws)


def _has_transition(src: str) -> bool:
    return bool(re.search(r"transition(-property)?\s*:(?!\s*['\"]?none)|"
                          r"\btransition(-all|-colors|-opacity|-transform)?(?=[\s\"'])|"
                          r"<motion\.|AnimatePresence", src))


def _m(fn):
    return lambda r, g, c: fn(measure_source(r, g, c))


MEASURES = {
    "shadow_blur": _m(max_shadow_blur),
    "palette_chroma": _m(palette_max_chroma),
    "hue_families": _m(lambda s: len(_saturated_hue_families(s))),
    "has_gradient": _m(lambda s: bool(re.search(r"gradient\(", s, re.I))),
    "max_radius": _m(_radius),
    "font_families": _m(_families),
    "font_weights": _m(_weights),
    "has_ambient_motion": _m(_ambient_motion),
    "has_transition": _m(_has_transition),
}
MEASURE_DESCRIPTIONS = {
    "shadow_blur": "deepest drop-shadow blur in px (none = no shadows)",
    "palette_chroma": "the boldest color's chroma 0-255 (none = neutrals only)",
    "hue_families": "number of distinct saturated hue families (30° bins)",
    "has_gradient": "true if any gradient() fill exists",
    "max_radius": "largest border-radius in px (none = no rounding declared)",
    "font_families": "number of distinct named typefaces (none = no named face found: unknown)",
    "font_weights": "number of distinct font weights used",
    "has_ambient_motion": "true if any perpetual/keyframe animation exists",
    "has_transition": "true if any state-change transition is declared",
}

_COND = re.compile(r"^(<=|>=|==|<|>)\s*(-?\d+(?:\.\d+)?)$")


def valid_cond(expr) -> bool:
    return isinstance(expr, str) and bool(expr.strip()) and all(
        t.strip() in ("none", "true", "false") or _COND.match(t.strip())
        for t in expr.split("|"))


def cond(expr: str, v) -> bool:
    """A tiny, closed condition language: terms joined by '|' (any holds) — 'none'
    (no reading), 'true'/'false' (booleans), or '<op> <number>'."""
    for t in (t.strip() for t in expr.split("|")):
        if t == "none":
            if v is None:
                return True
        elif t in ("true", "false"):
            if isinstance(v, bool) and v == (t == "true"):
                return True
        elif (m := _COND.match(t)) and v is not None and not isinstance(v, bool):
            op, n = m.group(1), float(m.group(2))
            if {"<": v < n, "<=": v <= n, ">": v > n, ">=": v >= n, "==": v == n}[op]:
                return True
    return False


def validate_measure(det: dict) -> str | None:
    if det.get("measure") not in MEASURES:
        return f"unknown measure {det.get('measure')!r} (known: {sorted(MEASURES)})"
    for k in ("zeroed", "added"):
        if not valid_cond(det.get(k, "")):
            return f"invalid '{k}' condition {det.get(k)!r}"
    return None


# --- the built-in absence detectors (the starter set — not privileged) ----------------
# name -> {detector, note, violation}. `violation` is optional prose for the check report.
BUILTINS = {
    "elevation-shadow": {
        "detector": {"measure": "shadow_blur", "zeroed": "none | < 8", "added": ">= 12"},
        "note": "deliberately FLAT — no drop-shadow depth (separation by hairlines, not elevation)",
        "violation": "the system is deliberately flat (no drop-shadow depth), but the build adds "
                     "{v}px shadows — elevation the identity refuses (violation by excess)",
    },
    "saturated-color": {
        "detector": {"measure": "palette_chroma", "zeroed": "none", "added": ">= 60"},
        "note": "MONOCHROMATIC — neutrals only, no saturated accent",
        "violation": "the system is monochromatic (neutrals only), but the build adds saturated "
                     "color (chroma {v}) — color the identity refuses",
    },
    "single-hue": {
        "detector": {"measure": "hue_families", "zeroed": "== 1", "added": ">= 2"},
        "note": "SINGLE-HUE — one accent hue family only, no multi-color palette",
        "violation": "the system is single-hue (one accent family), but the build uses {v} hue "
                     "families — a second color the identity refuses",
    },
    "flat-color": {
        "detector": {"measure": "has_gradient", "zeroed": "false", "added": "true"},
        "note": "FLAT-COLOR — solid fills only, no gradients",
        "violation": "the system uses flat color (no gradients), but the build adds gradient fills "
                     "— decoration the identity refuses",
    },
    "sharp-corners": {
        "detector": {"measure": "max_radius", "zeroed": "none | <= 2", "added": ">= 8"},
        "note": "SHARP-CORNERS — square/precise edges, no border-radius",
        "violation": "the system has sharp corners (no radius), but the build rounds to {v}px — "
                     "softening the identity refuses",
    },
    "single-face": {
        "detector": {"measure": "font_families", "zeroed": "== 1", "added": ">= 2"},
        "note": "SINGLE-FACE — one typeface, no display/body pairing",
        "violation": "the system commits to a single typeface, but the build introduces {v} faces "
                     "— type-pairing the identity refuses",
    },
    "ambient-motion": {
        "detector": {"measure": "has_ambient_motion", "zeroed": "false", "added": "true"},
        "note": "STATIC — no ambient / perpetual motion",
        "violation": "the system is static (no ambient motion), but the build adds ambient "
                     "animation — motion the identity refuses",
    },
}


def registry() -> dict:
    """name -> {detector, note, builtin, violation?} — every absence detector that may
    capture/gate. Learned entries (learned.json `absence:<name>`) OVERRIDE a built-in of
    the same name when active, and REVOKE it with status 'revoked'."""
    from rubrick import learned
    reg = {k: {**v, "builtin": True} for k, v in BUILTINS.items()}
    promoted = learned.promoted_absences()
    for key, ent in learned.load().get("learned_detectors", {}).items():
        if not key.startswith("absence:"):
            continue
        name = key.split(":", 1)[1]
        if ent.get("status") == "revoked":
            reg.pop(name, None)
        elif ent.get("status") == "active" and isinstance(ent.get("spec"), dict):
            desc = promoted.get(name, "")
            reg[name] = {"detector": ent["spec"], "builtin": False,
                         "note": f"deliberately WITHOUT {name}" + (f" — {desc}" if desc else "")}
    return reg


# --- evaluation: one reading for capture (product, twin) and check (candidate) ----------

def read(detector: dict, repo: str, gcss: str, comps: str, _src_cache: dict | None = None):
    """The detector's reading of a repo: the measured value, or a bool for patterns."""
    if "measure" in detector:
        return MEASURES[detector["measure"]](repo, gcss, comps)
    from rubrick.detectors import run_spec
    from rubrick.facet_signatures import raw_source
    cache = _src_cache if _src_cache is not None else {}
    if repo not in cache:
        cache[repo] = raw_source(repo, gcss, comps)
    return run_spec(detector, cache[repo])


def zeroed(detector: dict, value) -> bool:
    return cond(detector["zeroed"], value) if "measure" in detector else not value


def added(detector: dict, value) -> bool:
    return cond(detector["added"], value) if "measure" in detector else bool(value)


def _amount(v) -> float:
    """A reading as an ordered amount: no reading < false < true; numbers as-is."""
    if v is None:
        return float("-inf")
    return float(v)


def _twin_has(det: dict, pv, twin: tuple, cache: dict) -> bool:
    """The twin HAS it = outside the zeroed range AND more of it than the product. (Every
    omission measure is "less of something", so more = has it; without the direction, a
    twin with ZERO hue families would count as having a second hue.)"""
    tv = read(det, *twin, cache)
    return not zeroed(det, tv) and _amount(tv) > _amount(pv)


def classify(repo: str, gcss: str, comps: str, twins, *,
             designed: bool, extra_baseline: list[str] | None = None) -> dict:
    """The one capture rule, for every registered absence, voted across the generic twins.
    Returns {"captured", "uncertain", "log", "representative"}.

      product zeroes it AND a MAJORITY of twins have it  -> captured (a real refusal)
      product zeroes it, but only a minority (or none)   -> uncertain (designer decides)
      no twins (no API key)                               -> captured, marked unbaselined
    `twins` = a list of (repo, gcss, comps) — or a single tuple, or None. `representative`
    = the index of the twin agreeing most with the majority (the survey reads that one)."""
    if not designed:
        return {"captured": [], "uncertain": [], "log": [], "representative": None}
    if isinstance(twins, tuple):
        twins = [twins]
    twins = list(twins or [])
    from rubrick.detectors import run_spec
    cache: dict = {}
    captured, uncertain, log = [], [], []
    agree = [0] * len(twins)
    for name, ent in sorted(registry().items()):
        det = ent["detector"]
        try:
            pv = read(det, repo, gcss, comps, cache)
        except Exception as e:
            log.append(f"absence {name}: unreadable ({type(e).__name__})")
            continue
        if not zeroed(det, pv):
            continue
        rec = {"omits": name, "note": ent["note"], "detector": det, "builtin": ent["builtin"],
               **({"violation": ent["violation"]} if ent.get("violation") else {})}
        if not twins:
            rec["baseline"] = "unavailable"
            captured.append(rec)
            continue
        votes = [_twin_has(det, pv, t, cache) for t in twins]
        if not any(votes) and "measure" not in det and extra_baseline:
            votes = [any(run_spec(det, e) for e in extra_baseline)] * len(twins)
        k, n = sum(votes), len(votes)
        majority = 2 * k > n
        for i, v in enumerate(votes):
            agree[i] += v == majority
        rec["baseline"] = f"{k}/{n} generic twin{'s' if n > 1 else ''} have it"
        (captured if majority else uncertain).append(rec)
    rep = max(range(len(twins)), key=lambda i: (agree[i], -i)) if twins else None
    return {"captured": captured, "uncertain": uncertain, "log": log, "representative": rep}


def detect_subtractions(repo: str, gcss: str, comps: str, *, designed: bool) -> list[dict]:
    """Every zeroed registered absence, with no baseline (the no-key fallback)."""
    return classify(repo, gcss, comps, None, designed=designed)["captured"]


def _record_detector(s: dict) -> dict | None:
    """The record's embedded detector — or, for manifests from before the unification
    (built-ins stored by name only), the built-in's."""
    if isinstance(s.get("detector"), dict):
        return s["detector"]
    b = BUILTINS.get(s.get("omits", ""))
    return b["detector"] if b else None


def check_subtractions(subs: list[dict], repo: str, gcss: str, comps: str) -> list[str]:
    """Violation by EXCESS — the build shows a thing the system deliberately omits. The
    detector is read from the record itself, so this needs no learned store or model."""
    v, cache = [], {}
    for s in subs:
        det = _record_detector(s)
        if det is None:
            continue  # an unknown name with no detector — never gate blind
        val = read(det, repo, gcss, comps, cache)
        if not added(det, val):
            continue
        tmpl = s.get("violation") or BUILTINS.get(s["omits"], {}).get("violation")
        if tmpl:
            v.append("subtraction: " + tmpl.format(v=val))
        else:
            v.append(f"subtraction: the system is {s['note']}, but the build adds "
                     f"{s['omits']} back — an omission the identity keeps (violation by excess)")
    return v
