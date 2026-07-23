"""Moment vocabulary (v0) — the interaction analog of the role vocab.

A moment is the abstract, feature-agnostic EVENT an interaction is — keyed to
what happens to state/arrangement, never to how it's animated. SELF-EXTENDING like
roles/treatments/type-features: the vocab below is the BASE, but inference may name
a moment outside it (a tear) which the designer can promote into `learned.promoted_
moments`. So the type is an OPEN str, never a closed Literal — a closed Literal would
force a genuinely novel moment to collapse into "other" and it could never round-trip.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from rubrick.interaction import Qualifiers

MOMENT_VOCAB = {
    "create": "bring a new persistent thing into being",
    "send": "commit that leaves local context — becomes externally visible",
    "edit": "change an existing thing's content",
    "remove": "take a persistent thing away",
    "restructure": "change the arrangement/order of things, not their content",
    "toggle": "flip a discrete binary state (mode, active side)",
    "enter": "go into a context (view, item, mode)",
    "exit": "leave a context (back, close, dismiss)",
    "traverse": "move laterally between peers",
    "reveal": "show more of something already present",
    "seek": "search / filter / find",
    "browse": "scan across a collection",
    "progress": "communicate async work in flight",
    "notify": "surface something unprompted",
    "confirm-gate": "a deliberate pause before a consequence",
    "enliven": "ambient reactive response to attention, with no state change",
    "presence": "ambient liveness (typing indicators, live cursors)",
    "rest": "the composed resting state",
    "other": "fits none above — a candidate new moment (a tear)",
}

# OPEN str (base vocab + promoted), NOT a closed Literal — see module docstring.
# The prompt (base vocab + learned.promoted_moments) is the source of valid names.
Moment = str


class InferredMoment(BaseModel):
    moment: str
    qualifiers: Qualifiers
    confidence: float
    runner_up: Optional[str]
    rationale: str
