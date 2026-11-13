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
    if spec.get("scope", "source") not in ("source", "element"):
        return "scope may only be 'source' or 'element'"
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


def element_units(source: str) -> list[str]:
    """The source split into ELEMENT units — each JSX/HTML opening tag (scanned with
    brace/quote depth, so `style={{...}}` and `onClick={() => …}` stay inside it) and each
    innermost CSS rule block. Deterministic; used by scope='element' specs."""
    units, spans, i, n = [], [], 0, len(source)
    while i < n:
        if source[i] == "<" and i + 1 < n and source[i + 1].isalpha():
            depth, j, quote = 0, i + 1, ""
            while j < n:
                c = source[j]
                if quote:
                    if c == quote and source[j - 1] != "\\":
                        quote = ""
                elif c in "\"'`":
                    quote = c
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                elif c == ">" and depth <= 0 and source[j - 1] != "=":
                    break
                j += 1
            units.append(source[i:j + 1])
            spans.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    rest, k = [], 0
    for a, b in spans:  # blank the scanned tags exactly, then take innermost CSS rules
        rest.append(source[k:a])
        k = b
    rest.append(source[k:])
    units += [m.strip() for m in re.findall(r"[^{};<>]*\{[^{}]*\}", " ".join(rest))
              if ":" in m]  # a rule has declarations; drops stray JS braces
    return units


def _match(spec: dict, text: str, flags: int) -> bool:
    return (all(re.search(p, text, flags) for p in spec.get("all", []))
            and not any(re.search(p, text, flags) for p in spec.get("none", [])))


def run_spec(spec: dict, source: str) -> bool:
    """Execute a detector spec — a pure function of (spec, source). scope='source'
    (default) needs the conjuncts anywhere in the source; scope='element' needs them
    together inside ONE element unit (a JSX tag or a CSS rule) — so three unrelated
    elements can't jointly satisfy a spec describing one element."""
    flags = re.I if "i" in spec.get("flags", "") else 0
    try:
        if spec.get("scope", "source") == "element":
            return any(_match(spec, u, flags) for u in element_units(source))
        return _match(spec, source, flags)
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
    all: list[str] = []
    none: list[str] = []
    flags: str = ""
    scope: str = "source"
    # absence detectors only: a MEASUREMENT instead of patterns (subtractions.MEASURES)
    measure: str = ""
    zeroed: str = ""
    added: str = ""
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


def _propose_loop(render, admit_fn) -> tuple[dict | None, str]:
    """Two proposal attempts — the second sees the first's rejection reason. `render`
    builds the prompt from the feedback text; `admit_fn` returns a rejection reason or
    None. Returns (spec, "active") on admission or (None, reason)."""
    client = anthropic.Anthropic(api_key=load_key())
    feedback = ""
    reason = "no attempt"
    for _ in range(2):
        try:
            resp = client.messages.parse(
                model="claude-opus-4-8", max_tokens=6000, thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": render(feedback)}],
                output_format=ProposedSpec)
            out = resp.parsed_output
        except Exception as e:
            reason = f"proposal call failed: {type(e).__name__}"
            continue
        if out is None:
            reason = "proposal returned no parsed output"
            continue
        if out.measure:
            spec = {"measure": out.measure, "zeroed": out.zeroed, "added": out.added}
        else:
            spec = {"all": out.all, "none": out.none, "flags": out.flags}
            if out.scope == "element":
                spec["scope"] = "element"
        reason = admit_fn(spec) or ""
        if not reason:
            return spec, "active"
        feedback = (f"\nYOUR PREVIOUS ATTEMPT WAS REJECTED: {reason}. Patterns were "
                    f"all={out.all} none={out.none}. Fix that specific problem.")
    return None, reason


def propose_detector(kind: str, name: str, description: str, evidence: str,
                     calibration_source: str) -> tuple[dict | None, str]:
    """Ask the model for a detector spec and ADMIT it mechanically. Returns (spec,
    "active") on admission or (None, reason) on failure; the caller records either way,
    and a failed proposal leaves the word at the instructed-not-gated stage."""
    return _propose_loop(
        lambda fb: _PROPOSE.format(
            kind=kind, name=name, description=description or name,
            evidence=evidence[:600], context=_context(calibration_source, evidence),
            maxlen=_MAX_PATTERN_LEN, maxn=_MAX_PATTERNS, feedback=fb),
        lambda spec: admit(spec, calibration_source))


# --- absence detectors: the SUBTRACTIVE gate's self-extension (inverted admission) ----

def _exemplar_repo(exemplars: list[str], gcss: str, comps: str) -> str:
    """The generic exemplars as a throwaway repo with the product's layout, so a MEASURE
    detector reads them through the same code path as the product."""
    import pathlib
    import tempfile
    root = pathlib.Path(tempfile.mkdtemp(prefix="rubrick-exemplars-"))
    (root / comps).mkdir(parents=True, exist_ok=True)
    (root / gcss).parent.mkdir(parents=True, exist_ok=True)
    blob = "\n".join(exemplars)
    (root / gcss).write_text(blob)
    (root / comps / "Exemplars.tsx").write_text(blob)
    return str(root)


def _admit_measure(spec: dict, calibration_repo: tuple | None,
                   exemplars: list[str]) -> str | None:
    from rubrick.subtractions import added, read, validate_measure, zeroed
    if problem := validate_measure(spec):
        return f"malformed: {problem}"
    if calibration_repo is None:
        return "a measure detector needs the calibration repo"
    if not exemplars:
        return "no generic exemplar to admit against"
    cv = read(spec, *calibration_repo)
    if not zeroed(spec, cv) or added(spec, cv):
        return (f"the calibration product reads {cv!r}, which is not 'zeroed' "
                f"({spec['zeroed']}) — the product does not omit this by that measure")
    ev = read(spec, _exemplar_repo(exemplars, calibration_repo[1], calibration_repo[2]),
              calibration_repo[1], calibration_repo[2])
    if not added(spec, ev):  # must POSITIVELY read as having it — "unknown" is not "has it"
        return (f"the generic exemplars read {ev!r}, which does not meet 'added' "
                f"({spec['added']}) — the measure does not see the thing in a generic build")
    return None


def admit_absence(spec: dict, calibration_source: str, exemplars: list[str],
                  near_misses: list[str], calibration_repo: tuple | None = None) -> str | None:
    """Admission for a PRESENCE detector guarding a deliberate omission — the additive
    check inverted. The spec detects the thing being PRESENT, so it must:
      1. be well-formed,
      2. NOT match the calibration product (it omits the thing; a match means the
         detector is too loose, or the product isn't actually omitting it),
      3. match EVERY generated generic exemplar (they differ in construct, so the spec
         must recognize WHAT the thing is, not one way of drawing it),
      4. match NO near-miss (code sharing a surface trait — a round avatar for a pill
         badge — so a spec policing the shared trait, not the thing, is rejected),
    plus the eval run, as always. A MEASURE spec ({"measure", "zeroed", "added"}) is
    admitted by reading: the calibration repo must be zeroed (and not added), the
    generic exemplars must NOT be zeroed. Near-misses don't apply to quantities."""
    if "measure" in spec:
        return _admit_measure(spec, calibration_repo, exemplars)
    if problem := validate_spec(spec):
        return f"malformed: {problem}"
    if not exemplars:
        return "no generic exemplar to admit against"
    if run_spec(spec, calibration_source):
        return ("matches the calibration product, which omits this — too loose, or the "
                "product is not actually omitting it")
    missed = [e for e in exemplars if not run_spec(spec, e)]
    if missed:
        return f"does not match the generic exemplar(s) {[m[:80] for m in missed]}"
    if not near_misses:
        return "no near-miss probe to admit against (can't tell the thing from a shared trait)"
    hit = [n for n in near_misses if run_spec(spec, n)]
    if hit:
        return (f"fires on near-miss(es) {[h[:80] for h in hit]} — it detects a trait the "
                f"thing shares with unrelated code, not the thing itself")
    return None


_PROPOSE_ABSENCE = """You are writing a PRESENCE detector for "{name}" ({description}) —
a default a generic build includes but this product DELIBERATELY OMITS. The detector
guards the omission: it fires when a build ADDS the thing back. Spec: `all` = regexes
that must EVERY match, `none` = regexes that must NOT match, `flags` = "" or "i".

THE DISCIPLINE:
- Detect WHAT the thing is (its role), not one visual trait of it. The exemplars below
  differ in construct on purpose — the spec must match all of them. Recognize every
  common spelling (CSS, inline style objects, Tailwind, component libraries) with
  alternations inside a signal (e.g. `box-shadow|boxShadow|\\bshadow-(sm|md|lg|xl)\\b`).
  Use one `all` signal when it is unambiguous; add a conjunct when one trait alone is
  shared with other things (e.g. a badge = a fill AND tight padding around short text).
- It must NOT match these near-misses — common code sharing a trait with the thing:
{near_misses}
- `scope`: "element" when every `all` signal is a trait of ONE element (a fill AND
  padding AND small text on the same tag/CSS rule) — then they must co-occur inside a
  single JSX tag or CSS rule, so unrelated elements can't jointly fire it (a false
  fire here FAILS an honest build). "source" only when signals legitimately span
  elements (an icon-library import + its usage). Prefer "element" for visual things.
- ALTERNATIVELY, when the omission is about AMOUNT rather than presence (one weight only,
  shadows never deeper than a hairline, a single hue), leave `all` empty and set
  `measure` to one of these deterministic primitives, with `zeroed` = the condition the
  product satisfies and `added` = the condition that means a build reintroduced it.
  Leave a GAP between them so borderline values don't flip-flop. Condition syntax: terms
  joined by "|", each "none" | "true" | "false" | "<op> <number>" (op: < <= > >= ==).
{measures}
- It must NOT fire on the product below, which omits the thing — so avoid anything the
  product legitimately uses for other purposes (e.g. `box-shadow: none`, inset focus
  rings). Use `none` sparingly.
- It MUST match each of these generic implementations:
{exemplars}
- Python `re` syntax, each pattern under {maxlen} chars, at most {maxn} per list.

Where the product would have used it, and what it does instead: {evidence}

PRODUCT SOURCE (must NOT match):
{context}
{feedback}"""


def propose_absence_detector(name: str, description: str, evidence: str,
                             calibration_source: str, exemplars: list[str],
                             near_misses: list[str], calibration_repo: tuple | None = None
                             ) -> tuple[dict | None, str]:
    """Propose + admit a presence detector for a promoted absence."""
    return _propose_loop(
        lambda fb: _PROPOSE_ABSENCE.format(
            name=name, description=description or name, evidence=evidence[:600],
            exemplars="\n".join(f"  {e}" for e in exemplars) or "  (none)",
            near_misses="\n".join(f"  {n}" for n in near_misses) or "  (none)",
            measures="\n".join(f"    {k}: {v}" for k, v in sorted(_measure_docs().items())),
            context=calibration_source[:6000], maxlen=_MAX_PATTERN_LEN, maxn=_MAX_PATTERNS,
            feedback=fb),
        lambda spec: admit_absence(spec, calibration_source, exemplars, near_misses,
                                   calibration_repo))


def _measure_docs() -> dict:
    from rubrick.subtractions import MEASURE_DESCRIPTIONS
    return MEASURE_DESCRIPTIONS


def record_detector(kind: str, name: str, spec: dict | None, status: str,
                    calibrated_on: str, reason: str = "") -> None:
    """Persist a proposal's outcome in learned.json. Only status='active' ever gates."""
    d = learned.load()
    d.setdefault("learned_detectors", {})[f"{kind}:{name}"] = {
        "spec": spec, "status": status, "calibrated_on": calibrated_on,
        **({"reason": reason} if reason else {})}
    learned.save(d)
