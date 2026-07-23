"""The human loop — file-based review -> apply over pending promotions.

A compile surfaces novel identity moves the model found but the vocabulary has no word
for yet (`ps._pending`). `emit_review` writes an editable review file; the designer marks
each item promote/discard (+ a vocab name & one-line description for promotions);
`apply_review` writes the resolutions into learned.json, where a promoted move becomes
RECOGNIZED VOCABULARY that compounds across every future compile (and is no longer
surfaced as pending). The review file + learned.json are git-diffable — the audit trail.
"""

from __future__ import annotations

import json
import pathlib

from rubrick import learned

_FACETS = {"typography", "color", "density", "ambient", "elevation"}


def emit_review(ps, name: str, path: str) -> int:
    """Write <system>.review.json with the compile's designer-elicitations:
      - pending_promotions: novel moves to promote/discard.
      - refine_dispositions: the generated 'why' behind each captured move, for the
        designer to sharpen (a refined prior overrides the generated one and drives
        generate/check + is what the consuming agent reads).
    Returns the pending-promotion count. The designer edits only the blank fields."""
    pending = getattr(ps, "_pending", [])
    promotions = [{"name": p["name"], "modality": p["modality"], "evidence": p["evidence"],
                   "decision": "", "as": "", "description": ""} for p in pending]
    dispositions = [{"id": d.id, "prior": d.prior, "refined": ""}
                    for d in ps.dispositions.values()]
    intent = [{"subject": i["subject"], "captured": i["captured"], "decision": ""}
              for i in getattr(ps, "_intent", [])]
    moments = [{"interaction": m["interaction"], "moment": m["moment"],
                "confidence": m["confidence"], "correct_to": ""}
               for m in getattr(ps, "_moments", [])]
    pathlib.Path(path).write_text(json.dumps(
        {"system": name,
         "pending_promotions": promotions,
         "refine_dispositions": dispositions,
         "confirm_intent": intent,
         "confirm_moments": moments,
         "_how": "promotions: decision='promote'|'discard' (+'as'/'description'). dispositions: "
                 "'refined'=sharper why (blank keeps generated). confirm_intent: decision="
                 "'discard' to drop a captured move, 'capture' to rescue a thin one (blank keeps). "
                 "confirm_moments: 'correct_to'=the right moment if mis-inferred (blank keeps)."},
        indent=2))
    return len(promotions)


def apply_review(path: str) -> dict:
    """Read a resolved review file and write resolutions into learned.json:
    promote -> recognized vocab (record_promoted_*); discard -> record_discard (stop
    re-surfacing). Returns a summary of what was applied."""
    data = json.loads(pathlib.Path(path).read_text())
    promoted, discarded, unresolved, refined = [], [], [], []
    intent_set, moments_fixed = [], []
    for it in data.get("refine_dispositions", []):
        r = (it.get("refined") or "").strip()
        if r:
            learned.record_rationale(it["id"], r)
            refined.append(it["id"])
    for it in data.get("confirm_intent", []):
        dec = (it.get("decision") or "").strip().lower()
        if dec == "discard":
            learned.record_intent(it["subject"], "DISCARD")
            intent_set.append(f"DISCARD {it['subject']}")
        elif dec == "capture":
            learned.record_intent(it["subject"], "CAPTURE")
            intent_set.append(f"CAPTURE {it['subject']}")
    for it in data.get("confirm_moments", []):
        to = (it.get("correct_to") or "").strip()
        if to:
            learned.record_moment_correction(it["interaction"], it["moment"], to)
            moments_fixed.append(f"{it['interaction']}: {it['moment']}->{to}")
    for it in data.get("pending_promotions", []):
        dec = (it.get("decision") or "").strip().lower()
        mod = it["modality"]
        if dec == "promote":
            vocab_name = (it.get("as") or it["name"]).strip()
            desc = (it.get("description") or "").strip()
            if mod in _FACETS:
                learned.record_promoted_facet(mod, vocab_name, desc)
            elif mod == "behavior:treatment":
                learned.record_promoted_treatment(vocab_name, desc)
            elif mod == "behavior:moment":
                learned.record_promoted_moment(vocab_name, desc)
            promoted.append(f"{mod}:{vocab_name}")
        elif dec == "discard":
            kind = "treatment" if mod.startswith("behavior:") else mod
            learned.record_discard(kind, it["name"])
            discarded.append(f"{mod}:{it['name']}")
        else:
            unresolved.append(it["name"])
    return {"promoted": promoted, "discarded": discarded, "refined_dispositions": refined,
            "intent": intent_set, "moment_corrections": moments_fixed, "unresolved": unresolved}


def inspect_learned() -> dict:
    """What the tool has learned so far — the managed-store view. Everything here is
    global and compounds across every product; it all lives in git-tracked learned.json."""
    d = learned.load()
    return {
        "promoted_facets": d["promoted_facets"],
        "promoted_treatments": d["promoted_treatments"],
        "promoted_moments": d["promoted_moments"],
        "promoted_roles": d["promoted_roles"],
        "rationales": d["rationales"],
        "intent_decisions": d["intent_decisions"],
        "moment_corrections": d["moment_corrections"],
        "discarded": d["discarded"],
    }
