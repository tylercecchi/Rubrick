"""Learned detectors — the gate's self-extension mechanism.

The hand-written signatures (facet_signatures, detect_treatments, components) are the
SEED corpus of the deterministic gate, not its ceiling. When a designer promotes a novel
move/pattern/treatment surfaced by open observation, the model PROPOSES a detector for
it and the proposal is ADMITTED mechanically before it ever gates — the same
generate-then-validate shape as effect locality and dispositions.

A learned detector is DATA, not code: a declarative conjunctive spec

    {"all": [regex, ...], "none": [regex, ...], "flags": "i"}

meaning every `all` pattern must match the source and no `none` pattern may. Specs live
in learned.json (`learned_detectors`, keyed "kind:name") — git-diffable, reviewable, and
revocable (delete the entry, the gate shrinks back). Executing a spec is a pure function
of (spec, source), so everything the gate promises still holds: same input, same verdict,
exact self-conformance.

ADMISSION (the mechanical four-way check, per the detector discipline in DETECTORS.md):
  1. the spec is well-formed (schema, regex compile, size caps),
  2. it MATCHES the calibration product's source (it detects the thing it names),
  3. it does NOT match the vendored generic floor (stays discriminating),
  4. the eval harness stays green (guarded by the repo's regression run, as always).
A proposal that fails admission is recorded but NEVER gates — the promoted word stays
at the "instructed" stage (checklist + guide) until a valid detector exists.
"""

from __future__ import annotations

import json
import re

import anthropic
from pydantic import BaseModel

from rubrick import learned
from rubrick.baseline import load_key

_MAX_PATTERNS = 6      # per list — a detector is a few strong signals, not a program
_MAX_PATTERN_LEN = 300


# --- the generic floor (admission check #3) ---------------------------------------
# A compact copy of the tests/fixtures/rubrick-generic source, embedded so admission is
# self-contained in an installed package (the fixtures don't ship). Kept in sync by the
# eval assertion that runs admission against the real fixture. A valid detector must
# recognize a DISPOSITION the generic build lacks — matching this text = too loose.
_GENERIC_FLOOR = """
body { color: #333333; background: #f8f9fa; font-family: -apple-system, sans-serif; }
.header { padding: 13px 17px; background: #007bff; color: #ffffff; }
.card { margin: 22px; padding: 9px 15px; border: 1px solid #cccccc; background: #ffffff; }
.tag-ok { color: #28a745; padding: 3px 7px; }
.note { margin-top: 19px; gap: 6px; color: #6c757d; }
export function Card({ title }: { title: string }) {
  return (
    <div style={{ padding: "13px 17px", margin: 22, border: "1px solid #cccccc", background: "#f8f9fa" }}>
      <h2 style={{ fontSize: 19, fontWeight: 700, color: "#333333" }}>{title}</h2>
      <p style={{ marginTop: 9, fontSize: 15, color: "#007bff" }}>An undesigned card.</p>
      <span style={{ padding: "5px 11px", background: "#28a745", color: "#fff", fontSize: 13 }}>OK</span>
    </div>
  );
}
"""


def validate_spec(spec: dict) -> str | None:
    """A human-readable problem with the spec, or None if well-formed."""
    if not isinstance(spec, dict) or not spec.get("all"):
        return "spec must be a dict with a non-empty 'all' list"
    flags = spec.get("flags", "")
    if not isinstance(flags, str) or set(flags) - {"i"}:
        return "flags may only be '' or 'i'"
    for key in ("all", "none"):
        pats = spec.get(key, [])
        if not isinstance(pats, list) or len(pats) > _MAX_PATTERNS:
            return f"'{key}' must be a list of at most {_MAX_PATTERNS} patterns"
        for p in pats:
            if not isinstance(p, str) or not p or len(p) > _MAX_PATTERN_LEN:
                return f"'{key}' pattern too long/empty (max {_MAX_PATTERN_LEN} chars)"
            try:
                re.compile(p)
            except re.error as e:
                return f"invalid regex in '{key}': {p!r} ({e})"
    return None


def run_spec(spec: dict, source: str) -> bool:
    """Execute a detector spec — a pure function of (spec, source)."""
    flags = re.I if "i" in spec.get("flags", "") else 0
    try:
        return (all(re.search(p, source, flags) for p in spec.get("all", []))
                and not any(re.search(p, source, flags) for p in spec.get("none", [])))
    except re.error:
        return False


def admit(spec: dict, calibration_source: str) -> str | None:
    """The mechanical admission check — a reason the spec is REJECTED, or None if it
    may gate. (The repo's eval run remains the fourth guard, as for every detector.)"""
    if problem := validate_spec(spec):
        return f"malformed: {problem}"
    if not run_spec(spec, calibration_source):
        return "does not match the calibration product it was proposed for"
    if run_spec(spec, _GENERIC_FLOOR):
        return "matches the generic floor — too loose to be an identity detector"
    return None


# --- the learned store ------------------------------------------------------------

_memo: dict = {"mtime": None, "detectors": {}}


def _active_detectors() -> dict:
    """kind:name -> spec, for status=active entries. Memoized on learned.json's mtime —
    detection runs per-file in tight loops."""
    try:
        mtime = learned._F.stat().st_mtime if learned._F.exists() else None
    except OSError:
        mtime = None
    if _memo["mtime"] != mtime:
        d = learned.load().get("learned_detectors", {})
        _memo["detectors"] = {k: v["spec"] for k, v in d.items()
                              if v.get("status") == "active" and isinstance(v.get("spec"), dict)}
        _memo["mtime"] = mtime
    return _memo["detectors"]


def learned_hits(kind: str, source: str) -> set[str]:
    """Names of the ACTIVE learned detectors of this kind that match the source —
    deterministic, unioned with the built-in signatures at every detection site."""
    prefix = kind + ":"
    return {k[len(prefix):] for k, spec in _active_detectors().items()
            if k.startswith(prefix) and run_spec(spec, source)}


def learned_names(kind: str) -> set[str]:
    """Names of all ACTIVE learned detectors of a kind (e.g. to extend the measurable-move
    universe for deployment prevalence)."""
    prefix = kind + ":"
    return {k[len(prefix):] for k in _active_detectors() if k.startswith(prefix)}


# --- proposal: the model writes the detector --------------------------------------

class ProposedSpec(BaseModel):
    model_config = {"extra": "forbid"}
    all: list[str]
    none: list[str] = []
    flags: str = ""
    rationale: str


_PROPOSE = """You are writing a DETECTOR for a product-identity {kind} named "{name}"
({description}). A detector is a conjunctive spec: `all` = regexes that must EVERY match
the source, `none` = regexes that must NOT match, `flags` = "" or "i".

THE DETECTOR DISCIPLINE — it must recognize the DISPOSITION, not one product's construct:
- General: an honest ALTERNATIVE implementation of the same idea should still match. Do
  not anchor on this product's variable names, class names, or literal values, and inside
  each signal enumerate the common alternative APIs/spellings of the same idea as
  alternations (e.g. `scrollTop\\s*=|scrollTo\\(`, `setTimeout|requestAnimationFrame`).
- Conjunctive and discriminating: require the FEWEST signals that together are
  unambiguous — usually 2, at most 3. A generic, undesigned build must NEVER match, but
  every extra conjunct is a way to wrongly fail an honest alternative build; drop any
  signal that polices HOW the idea is coded rather than THAT it is present.
- Python `re` syntax, each pattern under {maxlen} chars, at most {maxn} per list.

It was observed here (the calibration evidence — your spec MUST match source containing
this construct, but generalize beyond its spelling):

EVIDENCE: {evidence}

SOURCE CONTEXT:
{context}
{feedback}"""


def _context(source: str, evidence: str, radius: int = 1500) -> str:
    """Source text around the evidence (or the head of the source if not found)."""
    probe = evidence.strip()[:80]
    i = source.find(probe) if probe else -1
    if i < 0:  # try a shorter probe — evidence is often paraphrased
        for tok in re.findall(r"[A-Za-z_-]{6,}", probe)[:5]:
            i = source.find(tok)
            if i >= 0:
                break
    if i < 0:
        return source[:2 * radius]
    return source[max(0, i - radius):i + radius]


def propose_detector(kind: str, name: str, description: str, evidence: str,
                     calibration_source: str) -> tuple[dict | None, str]:
    """Ask the model for a detector spec and ADMIT it mechanically. Two attempts — the
    second sees the first's rejection reason. Returns (spec, "active") on admission or
    (None, reason) on failure; the caller records either way, and a failed proposal
    leaves the word at the instructed-not-gated stage."""
    client = anthropic.Anthropic(api_key=load_key())
    feedback = ""
    reason = "no attempt"
    for _ in range(2):
        try:
            resp = client.messages.parse(
                model="claude-opus-4-8", max_tokens=6000, thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": _PROPOSE.format(
                    kind=kind, name=name, description=description or name,
                    evidence=evidence[:600], context=_context(calibration_source, evidence),
                    maxlen=_MAX_PATTERN_LEN, maxn=_MAX_PATTERNS, feedback=feedback)}],
                output_format=ProposedSpec)
            out = resp.parsed_output
        except Exception as e:
            reason = f"proposal call failed: {type(e).__name__}"
            continue
        if out is None:
            reason = "proposal returned no parsed output"
            continue
        spec = {"all": out.all, "none": out.none, "flags": out.flags}
        reason = admit(spec, calibration_source) or ""
        if not reason:
            return spec, "active"
        feedback = (f"\nYOUR PREVIOUS ATTEMPT WAS REJECTED: {reason}. Patterns were "
                    f"all={out.all} none={out.none}. Fix that specific problem.")
    return None, reason


def record_detector(kind: str, name: str, spec: dict | None, status: str,
                    calibrated_on: str, reason: str = "") -> None:
    """Persist a proposal's outcome in learned.json. Only status='active' ever gates."""
    d = learned.load()
    d.setdefault("learned_detectors", {})[f"{kind}:{name}"] = {
        "spec": spec, "status": status, "calibrated_on": calibrated_on,
        **({"reason": reason} if reason else {})}
    learned.save(d)
