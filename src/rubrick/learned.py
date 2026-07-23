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
          "promoted_facets": {}, "discarded": {}, "moment_corrections": {}}


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


# --- rationale -> disposition prior (soft facets) ---
def record_rationale(disposition_id: str, prior: str) -> None:
    d = load()
    d["rationales"][disposition_id] = prior
    save(d)


def rationale(disposition_id: str) -> str | None:
    return load()["rationales"].get(disposition_id)


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


# --- moment corrections (designer fixes a mis-inferred interaction moment) ---
def record_moment_correction(stem: str, from_moment: str, to_moment: str) -> None:
    d = load()
    d["moment_corrections"][f"{stem}:{from_moment}"] = to_moment
    save(d)


def moment_correction(stem: str, moment: str) -> str | None:
    return load()["moment_corrections"].get(f"{stem}:{moment}")


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
