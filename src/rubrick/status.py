"""How each item in a product system is VERIFIED — read at request time, because detector
status changes after compile (a promotion proposes a check; a designer revokes one).

    gated     — checked by code: a deterministic signature, measurement or learned detector.
                Same build in, same verdict out.
    semantic  — checked by a model read (color meaning, layout archetype). Re-reads meaning,
                so a verdict can shift between edits.
    instructed— builders are told to carry it, but no check exists yet (promoted vocabulary
                whose detector hasn't been written, or one that failed admission).
    rejected  — a proposed check failed admission; the reason says why. Still instructed.
    none      — a new find that isn't active yet: no check until it's named and made active.
"""

from __future__ import annotations

from rubrick import learned

_LABEL = {
    "gated": "Checked by code",
    "semantic": "Checked by a model read",
    "instructed": "Instructed only — no check yet",
    "rejected": "Check rejected — instructed only",
    "none": "No check yet",
}


def _learned_detector(kind: str, name: str) -> dict | None:
    return learned.load().get("learned_detectors", {}).get(f"{kind}:{name}")


def verification(key: str) -> dict:
    """{state, label, detail} for a catalog key (see the module doc for the states)."""
    from rubrick.facet_signatures import DETERMINISTIC_FACETS, TYPOGRAPHY_SEMANTIC
    from rubrick.subtractions import BUILTINS, registry

    def out(state: str, detail: str) -> dict:
        return {"state": state, "label": _LABEL[state], "detail": detail}

    head, _, rest = key.partition(":")
    if head == "new":
        if rest.startswith("behavior:"):          # new:behavior:treatment:<name>
            _, kind, name = rest.split(":", 2)
            kind = {"treatment": "treatment"}.get(kind, kind)
        else:
            kind, _, name = rest.partition(":")
        det = _learned_detector(kind, name)
        if det and det.get("status") == "rejected":
            return out("rejected", det.get("reason", "the proposed check failed admission"))
        return out("none", "Name it and make it active, and Rubrick proposes a check for it.")
    if head == "absence":
        reg = registry()
        if rest in BUILTINS and rest in reg:
            return out("gated", "A built-in measurement reads the build for it.")
        det = _learned_detector("absence", rest)
        if det and det.get("status") == "active":
            return out("gated", "A learned detector reads the build for it.")
        if det and det.get("status") == "rejected":
            return out("rejected", det.get("reason", "the proposed check failed admission"))
        return out("instructed", "Builders are told to leave it out; no detector exists yet.")
    if head in ("component", "surface", "rule"):
        return out("gated", "Read from the build's code by deterministic signatures.")
    if key == "composition":
        return out("semantic", "The layout archetype is read by a model; it can shift between edits.")
    if head == "color":
        return out("semantic", "Color meaning (marking vs decorating) is read by a model; it can "
                               "shift between edits — trust a stable verdict on unchanged code.")
    if head == "typography" and rest in TYPOGRAPHY_SEMANTIC:
        return out("semantic", "Whether a face reads as 'detailed' is a model read.")
    if head in DETERMINISTIC_FACETS or head == "typography":
        det = _learned_detector(head, rest)
        if det and det.get("status") == "rejected":
            return out("rejected", det.get("reason", "the proposed check failed admission"))
        if rest in learned.promoted_facets(head) and not (det and det.get("status") == "active"):
            return out("instructed", "Promoted vocabulary without an admitted detector yet.")
        return out("gated", "Read from the build's code by deterministic signatures.")
    return out("instructed", "No check is known for this item.")
