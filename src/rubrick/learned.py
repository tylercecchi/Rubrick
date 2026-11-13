"""The capture store: designer answers become reusable structure.

Turns human assistance from consumed-once into confidence-that-compounds. Holds
all four assistance kinds:
  - disambiguation_rules : clarifications appended to role-inference prompts
  - role_exemplars       : confirmed (element -> role) labels
  - intent_decisions     : resolved ELICIT verdicts (subject -> CAPTURE|DISCARD)
  - rationales           : the soft-facet "why" (disposition_id -> prior text)
"""

from __future__ import annotations

import json
import pathlib
from rubrick import paths

_F = paths.home() / "learned.json"
_EMPTY = {"disambiguation_rules": [], "role_exemplars": {},
          "intent_decisions": {}, "rationales": {}, "moment_rules": [],
          "promoted_roles": {}, "promoted_treatments": {}, "promoted_moments": {},
          "promoted_facets": {}, "discarded": {}, "moment_corrections": {},
          "locality_overrides": {}, "promoted_patterns": {}, "learned_detectors": {},
          "promoted_absences": {}, "job_overrides": {}, "switches": {}}


def load() -> dict:
    if _F.exists():
        return {**_EMPTY, **json.loads(_F.read_text())}
    return dict(_EMPTY)


def save(d: dict) -> None:
    _F.write_text(json.dumps(d, indent=2))


def reset() -> None:
    save(dict(_EMPTY))


# --- disambiguation (role) ---
def record_rule(rule: str) -> None:
    d = load()
    if rule not in d["disambiguation_rules"]:
        d["disambiguation_rules"].append(rule)
    save(d)


def guidance_block() -> str:
    return "\n".join(f"- {r}" for r in load()["disambiguation_rules"])


# --- exemplars ---
def record_exemplar(element_id: str, role: str) -> None:
    d = load()
    d["role_exemplars"][element_id] = role
    save(d)


# --- intent-confirmation ---
def record_intent(subject: str, decision: str) -> None:
    d = load()
    d["intent_decisions"][subject] = decision
    save(d)


def intent_decision(subject: str) -> str | None:
    return load()["intent_decisions"].get(subject)


# --- switches: every item in a product's system is ACTIVE or INACTIVE, per product ---
# The scope rule: a product's own decisions (switch states, confirmations, principle
# wording, description overrides, interaction-purpose corrections) are stored PER PRODUCT;
# learned KNOWLEDGE (promoted vocabulary, detectors, effect locality) stays global. A
# drifting ticker can be one product's identity and a mistake in another.
def record_switch(product: str, key: str, state: str) -> None:
    """state = 'on' (active) | 'off' (inactive), set by the designer. Recording the item's
    current state is how a designer CONFIRMS Rubrick's default ('keep inactive')."""
    assert state in ("on", "off"), state
    d = load()
    d["switches"].setdefault(product, {})[key] = {"state": state, "by": "you"}
    save(d)


def switch(product: str, key: str) -> str | None:
    """The designer's state for this item in this product: 'on' | 'off' | None (not set).
    Legacy global intent decisions (CAPTURE/DISCARD) still apply as a fallback."""
    d = load()
    ent = d.get("switches", {}).get(product, {}).get(key)
    if ent:
        return ent["state"]
    legacy = d["intent_decisions"].get(key)
    return {"CAPTURE": "on", "DISCARD": "off"}.get(legacy) if legacy else None


# --- rationale -> disposition prior (soft facets) ---
def record_rationale(disposition_id: str, prior: str, product: str = "") -> None:
    """A designer's wording for a principle — scoped to `product` ("<product>::<id>") so a
    rewording for one product never leaks into another that generated the same id."""
    d = load()
    d["rationales"][f"{product}::{disposition_id}" if product else disposition_id] = prior
    save(d)


def rationale(disposition_id: str, product: str = "") -> str | None:
    """Product-scoped wording first; a legacy unscoped entry still applies as fallback."""
    r = load()["rationales"]
    return (r.get(f"{product}::{disposition_id}") if product else None) or r.get(disposition_id)


# --- promoted roles (vocab self-extension: a tear becomes a new primitive) ---
def record_promoted_role(name: str, description: str) -> None:
    d = load()
    d["promoted_roles"][name] = description
    save(d)


def promoted_roles() -> dict:
    return load()["promoted_roles"]


# --- promoted treatment features (tear-escape for the interaction surface channel) ---
def record_promoted_treatment(name: str, description: str) -> None:
    d = load()
    d["promoted_treatments"][name] = description
    save(d)


def promoted_treatments() -> dict:
    return load()["promoted_treatments"]


# --- promoted STYLE-facet features (novel facet move -> recognized vocab) ---
def record_promoted_facet(facet: str, name: str, description: str) -> None:
    d = load()
    d["promoted_facets"].setdefault(facet, {})[name] = description
    save(d)


def promoted_facets(facet: str) -> dict:
    return load()["promoted_facets"].get(facet, {})


# --- promoted interaction patterns (tear-escape for the response-pattern channel) ---
def record_promoted_pattern(name: str, description: str) -> None:
    d = load()
    d["promoted_patterns"][name] = description
    save(d)


def promoted_patterns() -> dict:
    return load()["promoted_patterns"]


# --- promoted absences (the open subtractive channel: a deliberate omission -> vocab) ---
def record_promoted_absence(name: str, description: str) -> None:
    d = load()
    d["promoted_absences"][name] = description
    save(d)


def promoted_absences() -> dict:
    return load()["promoted_absences"]


# --- job overrides (designer corrects the twin's jobs, per product repo) ---
def record_job_override(repo_key: str, original: str, value: str) -> None:
    """value = 'STRIKE' (drop the job) or replacement text. Keyed per product: a job
    that is a design choice in one product is a core need in another."""
    d = load()
    d["job_overrides"].setdefault(repo_key, {})[original.strip().lower()] = value
    save(d)


# --- locality overrides (designer corrects a generated effect-locality classification) ---
def record_locality(subject: str, locality: str) -> None:
    """subject = 'facet:move'; locality = 'element-local' | 'page-global'. Overrides the
    generated classification (rubrick.scoping) — same pattern as rationales."""
    d = load()
    d["locality_overrides"][subject] = locality
    save(d)


def locality_override(subject: str) -> str | None:
    return load()["locality_overrides"].get(subject)


# --- moment corrections (designer fixes a mis-inferred interaction moment) ---
def record_moment_correction(stem: str, from_moment: str, to_moment: str, product: str = "") -> None:
    d = load()
    key = f"{product}::{stem}:{from_moment}" if product else f"{stem}:{from_moment}"
    d["moment_corrections"][key] = to_moment
    save(d)


def moment_correction(stem: str, moment: str, product: str = "") -> str | None:
    """Product-scoped correction first (component names collide across products); a
    legacy unscoped one still applies as fallback."""
    m = load()["moment_corrections"]
    return (m.get(f"{product}::{stem}:{moment}") if product else None) or m.get(f"{stem}:{moment}")


# --- discards (a novel move the designer rejected — stop re-surfacing it) ---
def record_discard(kind: str, name: str) -> None:
    d = load()
    lst = d["discarded"].setdefault(kind, [])
    if name not in lst:
        lst.append(name)
    save(d)


def discarded(kind: str) -> list:
    return load()["discarded"].get(kind, [])


# --- promoted moments (vocab self-extension: a novel moment becomes a primitive) ---
def record_promoted_moment(name: str, description: str) -> None:
    d = load()
    d["promoted_moments"][name] = description
    save(d)


def promoted_moments() -> dict:
    return load()["promoted_moments"]


# --- moment-disambiguation (interaction observation) ---
def record_moment_rule(rule: str) -> None:
    d = load()
    if rule not in d["moment_rules"]:
        d["moment_rules"].append(rule)
    save(d)


def moment_guidance_block() -> str:
    return "\n".join(f"- {r}" for r in load()["moment_rules"])
