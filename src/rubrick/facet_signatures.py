"""Deterministic facet-move detection — phase 1: density + elevation.

Facet MOVES are the last thing still on the LLM (Mechanism A): the model reads the source and
matches to a vocab. Content-keying makes a fixed source stable, but a candidate re-observation
after an edit re-extracts and can flap (the agent saw density/floating-overlays flip run to
run). Density and elevation are FULLY mechanical — every move has a clean code signature and
none are semantic — so they migrate to Mechanism B: same regex/metric at compile and check,
so a facet PASS means verified, not "the model happened to notice." (Typography/color/ambient
keep the LLM: they carry genuinely-semantic moves — entity-driven color, detailed faces — where
a signature would only guess at intent.)
"""

from __future__ import annotations

import pathlib
import re

from rubrick.style_facets import _all_colors, _rgb, _spacing_values, max_shadow_blur, median_spacing


def raw_source(repo: str, gcss: str, comps: str) -> str:
    """The RAW globals + component source — signatures need the actual tokens (100vh, flex-grow,
    colored shadows), which the LLM-tuned gather summarizes away. Deterministic (sorted files),
    so compile and check read the same text."""
    from rubrick.style_facets import source_dirs
    parts = []
    g = pathlib.Path(repo) / gcss
    if g.exists():
        parts.append(g.read_text())
    seen: set[str] = set()
    for d in source_dirs(repo, comps):  # src/components + src/app + src/lib — same reach as the gather
        for f in sorted(pathlib.Path(d).rglob("*.tsx"))[:60]:
            if str(f) in seen:
                continue
            seen.add(str(f))
            try:
                parts.append(f.read_text())
            except Exception:
                continue
    return "\n".join(parts)


def _has(s: str, p: str) -> bool:
    return re.search(p, s, re.I) is not None


def capture_face_roles(source: str) -> dict:
    """DETERMINISTIC face->role split for the native value->ROLE gate. Native mode's flat
    anchor check verifies the faces are PRESENT but not that they're in the SAME ROLES — a
    build using Geigy for display and RuderPlakat for body passes it, yet reads foreign. The
    LLM role extraction (concrete.values.faces) can't gate this: it's noisy (it read the
    calendar's display as FTLambert). This is the robust signal instead: the BODY/reading voice
    is the family on the body/root selector; DISPLAY faces are the identity (@font-face) faces
    that aren't the body voice. Returns {'body': str|None, 'display': [str]}."""
    ff = set(re.findall(r"@font-face\s*\{[^}]*?font-family:\s*[\"']([^\"';]+)", source, re.I))
    body = None
    for sel in (r"body\s*\{[^}]*?font-family:\s*[\"']?([^\"';,}]+)",
                r":root\s*\{[^}]*?font-family:\s*[\"']?([^\"';,}]+)"):
        m = re.search(sel, source, re.I)
        if m:
            body = m.group(1).strip().strip("\"'")
            break
    display = sorted(f for f in ff if f != body)
    return {"body": body, "display": display}


def _shadow_lines(s: str) -> list[str]:
    return [l for l in s.splitlines() if "shadow" in l.lower()]


# --- DENSITY ---
def _full_bleed(s):        return _has(s, r"100vw|100dvh|100svh|100vh|width:\s*[\"']?100%|inset:\s*0")
def _floating_overlays(s): return len(re.findall(r"position:\s*[\"']?(?:fixed|absolute)", s, re.I)) >= 2
def _generous_hero(s):     vals = _spacing_values(s); return bool(vals) and max(vals) >= 48
def _information_dense(s):  m = median_spacing(s); return m is not None and m <= 12
def _dynamic_density(s):
    # The DISPOSITION is "content/mode determines spatial rhythm" — recognize it however it's
    # honestly built, not only one product's flex-grow construct (that overfit dropped an honest
    # build that carried the move five other ways). Each branch is a STRONG density-responsiveness signal;
    # bare @media / minmax responsiveness is deliberately NOT enough (every responsive app has it
    # — generic must stay below), so the query-driven branches also require ANIMATED spacing.
    _spacing_txn = r"transition:[^;{}]*(?:gap|padding|height|width|max-height)"
    return (
        (_has(s, r"flex-?grow") and _has(s, r"transition"))                 # content-flex that animates
        or _has(s, r"density-(?:packed|roomy|compact|comfortable|dense)"    # an explicit density/compactness MODE
                r"|--(?:cell-gap|cell-pad|cell-h|row-h|density)\b")
        or (_has(s, r"grid-auto-rows") and _has(s, _spacing_txn))           # rows auto-size to content + animate
        or (_has(s, r"@container|container-type|ResizeObserver|matchMedia")  # responsiveness that DRIVES
            and _has(s, _spacing_txn))                                       #   animated spacing (not mere reflow)
    )
def _safe_area(s):         return _has(s, r"safe-area-inset|env\(\s*safe-area")


# --- ELEVATION ---
def _dramatic_shadow(s):   b = max_shadow_blur(s); return b is not None and b >= 32
def _soft_floating(s):
    for line in _shadow_lines(s):  # a NON-inset drop shadow with real blur (per-shadow, not whole-source)
        if "inset" in line.lower():
            continue
        nums = [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)px", line)]
        if nums and max(nums) >= 6:
            return True
    return False
def _flat_bordered(s):
    b = max_shadow_blur(s)
    return _has(s, r"border(?!-radius)|1px\s+solid|hairline") and (b is None or b < 8)
def _backdrop_blur(s):     return _has(s, r"backdrop-?filter[^;{}]*blur|backdropFilter[^,}]*blur")
def _layered_overlays(s):
    zs = {int(m) for m in re.findall(r"z-?index:\s*[\"']?(\d{1,4})", s, re.I)}
    return len([z for z in zs if z >= 10]) >= 2
def _inset_depth(s):       return _has(s, r"box-?shadow[^;{}]*\binset\b|inset[^;{}]*rgba")
def _colored_shadow(s):
    # a shadow tinted with hue — box-shadow OR filter:drop-shadow, via a literal hued color OR a
    # color VARIABLE (entity/team/accent color, or a var(--…color)), which is how a colored glow
    # is usually keyed to the subject.
    for line in _shadow_lines(s) + [l for l in s.splitlines() if "drop-shadow" in l.lower()]:
        for h in _all_colors(line):
            r, g, b = _rgb(h)
            if max(r, g, b) - min(r, g, b) >= 40:
                return True
        if re.search(r"drop-shadow|box-?shadow|boxShadow", line, re.I) \
                and re.search(r"\b\w*(?:team|entity|accent)\w*[Cc]olor\b|var\(--[^)]*color|\$\{[^}]*[Cc]olor", line):
            return True
    return False


# --- AMBIENT (perpetual motion) ---
def _infinite(s):          return _has(s, r"\binfinite\b|iteration-count:\s*infinite")
def _perpetual_loop(s):    return _infinite(s)
def _breathing_pulse(s):
    return _infinite(s) and (_has(s, r"@keyframes[^{]*(?:pulse|breath|glow|throb|beat)")
                             or _has(s, r"animation[^;{}]*(?:pulse|breath|glow|throb)")
                             or (_has(s, r"@keyframes") and _has(s, r"scale\(|opacity")
                                 and not _has(s, r"rotate\(|background-position")))
def _rotation_spin(s):
    return _infinite(s) and (_has(s, r"@keyframes[^{]*(?:spin|rotat)")
                             or _has(s, r"animation[^;{}]*(?:spin|rotat)")
                             or (_has(s, r"@keyframes") and _has(s, r"rotate\(")))
def _drift_scroll(s):
    return _infinite(s) and (_has(s, r"@keyframes[^{]*(?:drift|scroll|marquee|pan|ticker)")
                             or _has(s, r"background-position")
                             or _has(s, r"animation[^;{}]*(?:drift|scroll|marquee)"))
def _physics_loop(s):
    if _has(s, r"useSpring|\bspring\b|stiffness|damping|\bdecay\b"):
        return True
    for m in re.findall(r"cubic-bezier\(([^)]*)\)", s):
        vals = [float(x) for x in re.findall(r"-?\d*\.?\d+", m)]
        if any(v > 1 or v < 0 for v in vals):
            return True
    return False
def _orchestrated_stagger(s):
    delays = set(re.findall(r"animation-delay:\s*(-?[\d.]+m?s)", s))
    return len(delays) >= 2 or _has(s, r"nth-child[^}]*animation-delay|index\s*\*\s*\d|\bi\s*\*\s*\d+\s*\+?\s*[\"']?m?s|delay.{0,20}index")
def _ambient_restraint(s):
    if not _infinite(s):
        return False
    big = bool(re.search(r"translate[XY]?\(\s*-?\d{2,}", s)) \
        or bool(re.search(r"rotate\(\s*-?\d{2,}", s)) \
        or bool(re.search(r"scale\(\s*(?:[2-9]|1\.[3-9])", s))
    return not big
def _presence_signal(s):
    return _infinite(s) and _has(s, r"\b(?:live|online|active|status|signal|pulse|ping|heartbeat"
                                    r"|real-?time|streaming|presence)\b")


# DETECTOR DISCIPLINE — signatures recognize a DISPOSITION, not one product's construct.
# A signature calibrated on a single product's specific code (e.g. dynamic-density was once just
# `flex-grow + transition`, learned from one product's zoom canvas) is a FALSE-NEGATIVE waiting to
# happen: it drops honest alternative implementations of the same disposition (a calendar carried
# dynamic-density five other ways — packed⇄roomy modes, content-sized rows, container queries —
# and failed). The disposition is general; the signature must be too. Single-construct = suspect.
#
# When broadening or adding a signature, verify it FOUR ways (the guard the eval harness enforces):
#   1. the calibration product STILL matches (self-conformance holds),
#   2. a fresh build that honestly carries the disposition NOW matches (the false-negative is gone),
#   3. GENERIC does NOT match (stay discriminating — require strong signals, not bare responsiveness),
#   4. the eval harness stays green (elevation-above-generic preserved).
# Full contributor guide to the detection layer (deterministic vs LLM, the move vocabulary): DETECTORS.md.
_MOVE_SIGNATURES = {
    "ambient": {
        "perpetual-loop": _perpetual_loop, "breathing-pulse": _breathing_pulse,
        "rotation-spin": _rotation_spin, "drift-scroll": _drift_scroll,
        "physics-loop": _physics_loop, "orchestrated-stagger": _orchestrated_stagger,
        "ambient-restraint": _ambient_restraint, "presence-signal": _presence_signal,
    },
    "density": {
        "full-bleed-canvas": _full_bleed, "floating-overlays": _floating_overlays,
        "generous-hero-space": _generous_hero, "information-dense": _information_dense,
        "dynamic-density": _dynamic_density, "safe-area-mobile": _safe_area,
    },
    "elevation": {
        "soft-floating-shadows": _soft_floating, "flat-bordered": _flat_bordered,
        "backdrop-blur": _backdrop_blur, "layered-overlays": _layered_overlays,
        "dramatic-shadow": _dramatic_shadow, "inset-depth": _inset_depth,
        "colored-shadow": _colored_shadow,
    },
}

DETERMINISTIC_FACETS = set(_MOVE_SIGNATURES)

# --- TYPOGRAPHY (HYBRID: 6 mechanical moves by signature; `detailed-face` stays LLM, and the
# faces themselves stay LLM — a typeface's role/character isn't a code signature) ---
_GENERIC_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "inherit", "-apple-system",
                  "blinkmacsystemfont", "ui-sans-serif", "ui-monospace", "arial", "helvetica"}
TYPOGRAPHY_SEMANTIC = {"detailed-face"}


def _custom_faces(s):
    fams = {m.strip().lower() for m in re.findall(r"font-?family\s*:\s*[\"'`]?([^;,\"'`\n}]+)", s, re.I)}
    return {f for f in fams if f and f not in _GENERIC_FONTS}


def _type_moves(s: str) -> set[str]:
    from rubrick.type_extract import extract_font_sizes, max_tracking, max_weight, scale_contrast_ratio
    out = set()
    r = scale_contrast_ratio(s)
    if r is not None and r >= 4:
        out.add("extreme-scale-contrast")
    w = max_weight(s)
    if w is not None and w >= 700:
        out.add("expressive-weight")
    t = max_tracking(s)
    if t is not None and t >= 0.05 and _has(s, r"text-transform:\s*uppercase|textTransform:\s*[\"']uppercase|\buppercase\b"):
        out.add("treated-microtype")
    sizes = extract_font_sizes(s) or [0]
    faces = _custom_faces(s)
    if faces and max(sizes) >= 40:
        out.add("custom-display-face")
    if len(faces) >= 2:
        out.add("distinct-body-face")
    if max(sizes) >= 72 and _has(s, r"rotate\(|overflow:\s*hidden|background-clip:\s*text|WebkitBackgroundClip"
                                   r"|-webkit-text-stroke|WebkitTextStroke|mix-blend|clip-path"):
        out.add("type-as-graphic")
    return out


def hybrid_type_obs(repo: str, gcss: str, comps: str, gathered: str, key_id: str):
    """TypeObservation with mechanical moves from signatures + faces & detailed-face from the LLM.
    The LLM still runs (faces and detailed-face are irreducibly semantic), but the moves that
    flapped come from code signatures — deterministic where it counts, LLM only where it must."""
    from rubrick.typography import GroundedTypeFeature, TypeObservation
    from rubrick.type_extract import extract_typography
    llm = extract_typography(gathered, key_id)
    moves = _type_moves(raw_source(repo, gcss, comps)) \
        | {f for f in llm.grounded_set() if f in TYPOGRAPHY_SEMANTIC}
    return TypeObservation(
        faces=llm.faces,
        features=[GroundedTypeFeature(feature=m,
                  evidence="LLM (semantic)" if m in TYPOGRAPHY_SEMANTIC else "code signature")
                  for m in sorted(moves)],
        novel_features=llm.novel_features)


def detect_facet_moves(facet: str, source: str) -> set[str]:
    """The identity moves present in a facet's source — deterministic, by code signature."""
    return {m for m, sig in _MOVE_SIGNATURES[facet].items() if sig(source)}


def signature_facet_obs(facet: str, source: str):
    """A FacetObs built from signatures (drop-in for the LLM extract_facet on mechanical facets).
    No novel_features — signatures find known vocab only; a mechanical facet's vocab is complete."""
    from rubrick.style_facets import FacetFeature, FacetObs
    moves = detect_facet_moves(facet, source)
    return FacetObs(
        features=[FacetFeature(feature=m, evidence="detected by code signature") for m in sorted(moves)],
        novel_features=[], identity_summary=f"{facet}: {sorted(moves)} (deterministic)")
