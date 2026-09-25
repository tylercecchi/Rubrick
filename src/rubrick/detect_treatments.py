"""Deterministic behavior-treatment detection — the analog of extract_css for material.

Behavior conformance was the one unreliable modality because it was LLM-all-the-way
(extract-and-cite treatments -> infer moment -> judge disorientation), each a fresh sample
on every edit: lossy recall (missed treatments that were present) and non-determinism
(PASS then FAIL on the same code during iteration). Color and surface conform reliably
because they are deterministic regex. This closes the gap for behavior: treatment features
and timings are read by CODE SIGNATURE, so compile and check produce the SAME set for the
SAME source — a treatment PASS means verified, not "the model happened to notice."

Signatures target the structural treatments (the choreography). Precision over recall: a
false treatment in the SYSTEM would force every candidate to reproduce it, so a signature
only fires on clear evidence. Determinism is guaranteed regardless (same regex, same input).
"""

from __future__ import annotations

import re

# duration literals: 480ms, 0.48s, .3s
_MS = re.compile(r"(\d+(?:\.\d+)?)\s*ms\b")
_S = re.compile(r"(?<![\d.])(\d*\.?\d+)\s*s\b")


def _durations_ms(text: str) -> list[float]:
    out = [float(m) for m in _MS.findall(text)]
    out += [float(m) * 1000 for m in _S.findall(text)]
    # motion-library durations are UNITLESS: framer/GSAP in seconds (duration: 0.4),
    # anime.js in ms (duration: 400). Disambiguate by magnitude — <=10 can only be seconds
    # (a 10ms CSS value would carry a unit), larger reads as ms. The (?!\s*m?s) guard keeps
    # unit-carrying CSS values (animation-duration: 2s / 300ms) on the branches above.
    for m in re.findall(r"duration\s*[=:]\s*(\d*\.?\d+)(?!\s*m?s)", text):
        v = float(m)
        out.append(v * 1000 if v <= 10 else v)
    return [d for d in out if 20 <= d <= 5000]  # plausible transition band


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.I) is not None


# Idiomatic code names its durations (`const HELD_MS = 160; await sleep(HELD_MS)`), so
# literal-only signatures miss them (trial: manufactured-latency, symmetry, and the real
# timings all invisible because the values live behind constants). Resolve numeric consts
# so the signatures see through them — the deterministic form of "dynamic-value resolution".
# REQUIRES const/let/var — otherwise it mistook a CSS/JSX `property: value` (opacity: 1) for a
# constant and clobbered the property name everywhere, destroying e.g. `opacity: … 0.22` before
# the demote signature could read it.
_CONST = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(-?\d+(?:\.\d+)?)(?:px|rem|em|ms|s)?\b")
_EXIT_CUE = re.compile(r"exit|release|leave|\bout\b|unseat|close|hide|dismiss|collapse|retract", re.I)
_ENTER_CUE = re.compile(r"enter|seat|arrive|\bin\b|reseat|\bopen\b|reveal|expand|settle|deploy", re.I)


def _const_map(source: str) -> dict:
    out: dict[str, float] = {}
    for name, val in _CONST.findall(source):
        v = float(val)
        if 1 <= v <= 100000:
            out.setdefault(name, v)
    return out


def _resolve_consts(source: str) -> str:
    consts = _const_map(source)
    if not consts:
        return source
    pat = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(consts, key=len, reverse=True)) + r")\b")
    return pat.sub(lambda m: str(int(consts[m.group(1)])), source)


# Each signature: name -> (regex-or-callable, human evidence). A callable takes the source
# and returns True/False for the multi-condition ones.
#
# LIBRARY-AWARE branches: much of real React choreography is declared through motion
# libraries (framer-motion / react-spring / GSAP / lottie), not CSS — AnimatePresence with
# exit variants IS multi-phase, staggerChildren IS orchestration, type:"spring" IS spring
# physics. Each library branch is a PURE ADDITION (OR on tokens CSS-built products don't
# contain), so existing systems' observations are unchanged — a product that never imports
# these libraries detects exactly as before.
def _multi_phase(s: str) -> bool:
    # a choreographed exit -> (commit) -> enter: both an exit AND an enter stage, OR >=2
    # sequenced timed stages (chained setTimeout / await sleep), OR >=2 transient phase states.
    exit_enter = _has(s, r"-exit\b") and _has(s, r"-enter\b")
    sequenced = len(re.findall(r"setTimeout\(|await\s+sleep\(|await\s+new\s+Promise", s)) >= 2
    phases = len(re.findall(r"\b(?:phase|stage|step)\b\s*[:=]", s, re.I)) >= 2
    transient_states = len(re.findall(r"set(?:Swapping|ScalingIn|Exiting|Entering|Phase|Stage)\(", s)) >= 2
    # framer-motion: unmount choreography (AnimatePresence + an exit spec) or a variants
    # graph with distinct enter/exit poses; GSAP: a timeline sequencing >=2 tweens.
    presence_exit = _has(s, r"<AnimatePresence") and _has(s, r"\bexit\s*[=:]")
    variant_stages = _has(s, r"\bvariants\s*[=:]") and \
        len(re.findall(r"\b(?:initial|animate|exit|enter|hidden|visible|show)\b\s*[=:]", s)) >= 2
    gsap_timeline = _has(s, r"gsap\.timeline|\btimeline\(\)") and len(re.findall(r"\.(?:to|from|fromTo)\(", s)) >= 2
    return exit_enter or sequenced or phases or transient_states \
        or presence_exit or variant_stages or gsap_timeline


def _manufactured_latency(s: str) -> bool:
    # a deliberate delay detached from real work: a hardcoded ms delay driving a phase
    # transition (not an awaited fetch). setTimeout/sleep with a numeric literal, or a long
    # hold between exit and enter.
    return _has(s, r"setTimeout\([^,]+,\s*\d{2,4}\s*\)") or _has(s, r"sleep\(\s*\d{2,4}\s*\)") \
        or _has(s, r"new\s+Promise\([^)]*setTimeout[^,]*,\s*\d{2,4}")


def _symmetry(s: str) -> bool:
    # participants move in coordinated opposition: mirrored up/down variants, or opposite
    # translate signs, or a two-peer exchange with mirrored durations.
    up_down = _has(s, r"-up\b") and _has(s, r"-down\b")
    opposite_translate = bool(re.search(r"translateY?\(\s*-\d", s)) and bool(re.search(r"translateY?\(\s*\d", s))
    return up_down or opposite_translate


def _demote_not_remove(s: str) -> bool:
    # the alternative is DIMMED in place (partial opacity), never unmounted. A fractional
    # opacity inside a conditional (EITHER ternary branch — `demoted ? 0.22 : 1` as well as
    # `open ? 1 : 0.22`), or a fractional opacity near a demote/inactive cue, or an explicit
    # demote helper paired with a dimming property.
    for m in re.finditer(r"opacity\s*:\s*([^,;}\n]+)", s):
        val = m.group(1)
        if re.search(r"0?\.\d", val) and ("?" in val
                or re.search(r"demot|dim|inactive|faded|muted|selected|active|match", s, re.I)):
            return True
    return bool(re.search(r"\bdemot(?:e|ed|es|ing)\b", s, re.I)) and _has(s, r"opacity|filter|grayscale")


def _motion_ack(s: str) -> bool:
    # the change is animated, not a hard swap: a transition/animation with a real duration —
    # CSS, or a motion-library animate/tween (framer <motion.*> with a transition prop, a
    # GSAP/anime tween, a react-spring animated element).
    css = (_has(s, r"transition:\s*(?!none)") or _has(s, r"animation:\s*(?!none)")) and bool(_durations_ms(s))
    lib = (_has(s, r"<motion\.") and _has(s, r"\btransition\s*[=:]")) \
        or _has(s, r"gsap\.(?:to|from|fromTo|timeline)|anime\(\{|<animated\.")
    return css or lib


def _interaction_lock(s: str) -> bool:
    # pointer-events:none in ANY form — static, or a ternary/dynamic value
    # (`pointerEvents: isBusy ? "none" : "auto"`) which the literal-only reader missed —
    # plus setPointerCapture, and disabled/aria-disabled BOUND to an interaction state
    # (disabled={isBusy}), the other idiomatic way to block input during a transition.
    return bool(re.search(r"pointer-?events\s*:[^,;}\n]*\bnone\b", s, re.I)) \
        or _has(s, r"setPointerCapture\(") \
        or bool(re.search(r"(?:disabled|aria-disabled)\s*[=:]\s*\{?[^}\n]*"
                          r"\b(?:lock|busy|swap|swapping|transition|transitioning|animating|phase|pending)\b",
                          s, re.I))


def _reactive_continuous(s: str) -> bool:
    # continuously tracks pointer/attention with no committed state change — raw pointer
    # listeners driving transforms, or the library form: framer motion-values/pan gestures,
    # @use-gesture handlers bound to springs/transforms.
    raw = (_has(s, r"onPointerMove|onMouseMove|mousemove|pointermove")
           and _has(s, r"transform|translate|--[a-z-]*x|--[a-z-]*y|rotate|style\.setProperty"))
    lib = _has(s, r"useMotionValue|useTransform\(|onPan\s*[=:]|useGesture\(|\buseDrag\(|\buseMove\(")
    return raw or lib


def _spring_physics(s: str) -> bool:
    # custom spring/decay, or an overshoot cubic-bezier (a control point outside [0,1]).
    # `spring|stiffness|damping|...` already covers framer's type:"spring" configs and
    # react-spring; add framer's shorthand bounce/mass params and inertia (momentum) tweens.
    if _has(s, r"\b(?:spring|stiffness|damping|useSpring|decay|velocity)\b") \
            or _has(s, r"\btype\s*[=:]\s*[\"']inertia|\bbounce\s*[=:]\s*0?\.\d|\bmass\s*[=:]\s*\d"):
        return True
    for m in re.findall(r"cubic-bezier\(([^)]*)\)", s):
        vals = [float(x) for x in re.findall(r"-?\d*\.?\d+", m)]
        if any(v > 1 or v < 0 for v in vals):  # overshoot / anticipation
            return True
    return False


def _streaming_reveal(s: str) -> bool:
    return _has(s, r"ReadableStream|getReader\(|EventSource|text/event-stream|\bstream(?:ing)?\b")


def _cross_highlight(s: str) -> bool:
    # hovering/selecting one entity emphasizes its COUNTERPART elsewhere — needs a shared
    # hovered/active id that a different element reads, or an explicit cross-emphasis term.
    # (The loose "hover + Context/sentiment" version fired on every card; those are too common.)
    return _has(s, r"counterpart|cross-?highlight|paired|mirror(?:ed)?\b") \
        or (_has(s, r"onMouseEnter|onPointerEnter|setHovered|hovered(?:Id|Key|Index)|activeId")
            and _has(s, r"hovered(?:Id|Key|Index)|activeId|highlightedId"))


def _progressive_enhancement(s: str) -> bool:
    return _has(s, r"preventDefault\(") and _has(s, r"<a\b|href=|<form\b|<Link\b")


def _gate_insertion(s: str) -> bool:
    return _has(s, r"window\.confirm\(|\bconfirm\(|areYouSure|confirmation|requireConfirm|\bthreshold\b")


def _optimistic(s: str) -> bool:
    # UI updated before the async confirms: a setState that precedes the awaited mutation,
    # or an explicit rollback on error (the tell of an optimistic update).
    return _has(s, r"optimistic|rollback|revert(?:On)?Error") \
        or bool(re.search(r"set[A-Z]\w+\([^)]*\)[\s\S]{0,200}?await\s+(?:fetch|mutate|post|put|delete)", s))


_SIGNATURES = {
    "multi-phase": _multi_phase,
    "manufactured-latency": _manufactured_latency,
    "symmetry": _symmetry,
    "demote-not-remove": _demote_not_remove,
    "motion-ack": _motion_ack,
    "interaction-lock": _interaction_lock,
    "reactive-continuous": _reactive_continuous,
    "spring-physics": _spring_physics,
    "streaming-reveal": _streaming_reveal,
    "cross-highlight": _cross_highlight,
    "progressive-enhancement": _progressive_enhancement,
    "gate-insertion": _gate_insertion,
    "optimistic": _optimistic,
}


_DUR_NAME = re.compile(r"MS\b|_MS|DURATION|DELAY|\bDUR|TIMING|SPEED|_TIME\b", re.I)


def _duration_consts(source: str) -> dict:
    """Only constants whose NAME marks them as durations (RELEASE_MS, HOLD_DURATION) — not
    every number. A stray `SEASON = 2025` must never be read as a 2025ms exit timing."""
    return {n: v for n, v in _const_map(source).items() if 20 <= v <= 5000 and _DUR_NAME.search(n)}


def _phase_durations(source: str) -> tuple[set[float], set[float]]:
    """Durations grouped by phase — from duration-named constants (RELEASE_MS=400 → exit) and
    from inline literals on phase-cued lines (a `swap-enter` keyframe → enter)."""
    ex, en = set(), set()
    for name, v in _duration_consts(source).items():
        if _EXIT_CUE.search(name):
            ex.add(v)
        elif _ENTER_CUE.search(name):
            en.add(v)
    for line in source.splitlines():
        ds = set(_durations_ms(line))
        if not ds:
            continue
        if _EXIT_CUE.search(line):
            ex |= ds
        elif _ENTER_CUE.search(line):
            en |= ds
    return ex, en


def _temporal_symmetry(source: str) -> bool:
    """Coordinated opposition as MIRRORED timing — the idiomatic form the spatial up/down
    signature misses. Two duration constants sharing a value (RELEASE_MS===SEAT_MS, or
    WIND_MS===LET_DOWN_MS) is a mirror pair; or an exit-phase duration equal to an enter one."""
    vals = list(_duration_consts(source).values())
    if len(vals) != len(set(vals)):  # a repeated duration value = a symmetric pair
        return True
    ex, en = _phase_durations(source)
    return bool(ex & en)


def detect_treatments(source: str) -> set[str]:
    """The set of treatment features present in an interaction's source — deterministic, by
    code signature. Constants are resolved first (`sleep(HELD_MS)` → `sleep(160)`) so named
    durations aren't invisible. Same source -> same set (compile and check agree exactly)."""
    rsrc = _resolve_consts(source)
    found = {name for name, sig in _SIGNATURES.items() if sig(rsrc)}
    if _temporal_symmetry(source):  # needs the original names for phase cues
        found.add("symmetry")
    # ACTIVE learned detectors (model-proposed at promotion, mechanically admitted) — a
    # promoted treatment can now actually gate, instead of staying vocab-only forever.
    from rubrick.detectors import learned_hits
    return found | learned_hits("treatment", rsrc)


def detect_timings(source: str) -> dict:
    """Exit / enter durations in ms, deterministic. Phase-cued named constants and inline
    literals both count; fall back to the dominant resolved durations."""
    ex, en = _phase_durations(source)
    exit_ms = max(ex) if ex else None
    enter_ms = max(en) if en else None
    alld = sorted(set(_duration_consts(source).values()) | set(_durations_ms(source)), reverse=True)
    if exit_ms is None and alld:
        exit_ms = alld[0]
    if enter_ms is None:
        enter_ms = alld[1] if len(alld) > 1 else exit_ms
    return {"exit_ms": round(exit_ms) if exit_ms else None,
            "enter_ms": round(enter_ms) if enter_ms else None}


def interaction_richness(source: str) -> int:
    """How choreographed an interaction is — the count of detected treatments plus a small
    bonus for distinct timings. Deterministic; used to rank which components are the identity
    interactions (replacing the old regex-count heuristic with the same signatures we check)."""
    rsrc = _resolve_consts(source)
    return len(detect_treatments(source)) + min(len(set(_durations_ms(rsrc))), 4)
