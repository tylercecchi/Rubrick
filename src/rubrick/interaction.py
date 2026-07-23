"""Structural representation of BEHAVIOR — the interaction analog of MaterialStack.

A material was an ordered stack of layers; we diffed the set of material-roles.
An interaction is a moment (+ qualifiers) with a set of TREATMENT FEATURES; we
diff that set against the agent's default treatment for the same moment.

  moment + qualifiers  <->  role            (the structural channel; what the
                                              agent generates a default FOR)
  treatment_features   <->  material layers (the surface channel; the delta)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Frequency = Literal["once-ever", "rare", "occasional", "constant"]
Stakes = Literal["trivial", "recoverable", "costly", "irreversible"]
Reversibility = Literal["free-undo", "effortful-undo", "none"]
Blast = Literal["self-local", "self-global", "others", "external-world"]
Latency = Literal["instant", "async"]
Initiative = Literal["user", "system"]

# The closed vocabulary of "special" treatment features — the delta signal.
# Generic responses (a plain fade, a hover-highlight) are deliberately NOT here,
# so they never count as special. Delta = observed features - agent-default features.
TreatmentFeature = Literal[
    "optimistic",              # respond before the async work completes
    "motion-ack",              # animate the change rather than hard-swapping
    "multi-phase",             # exit -> commit -> enter choreography, not one transition
    "manufactured-latency",    # motion detached from real work — ceremony
    "symmetry",                # coordinated opposing motion of participants
    "interaction-lock",        # block input during the transition
    "progressive-enhancement", # real navigable fallback upgraded by JS
    "demote-not-remove",       # alternatives dimmed/kept, never hidden
    "streaming-reveal",        # progress shown as content, not a spinner
    "gate-insertion",          # an inserted confirm/threshold step (friction)
    "reactive-continuous",     # continuous pointer/attention tracking (enliven)
    "spring-physics",          # custom spring/decay motion vs a standard easing curve
    "cross-highlight",         # emphasize the counterpart entity elsewhere (correlate)
]

TREATMENT_DESCRIPTIONS = {
    "optimistic": "update the UI before the async work confirms",
    "motion-ack": "animate the change instead of a hard swap",
    "multi-phase": "a choreographed exit -> commit -> enter sequence",
    "manufactured-latency": "motion whose duration is detached from real work (ceremony)",
    "symmetry": "participants move in coordinated opposition",
    "interaction-lock": "block user input for the duration of the transition",
    "progressive-enhancement": "a real navigable link/form upgraded by JS into an in-place effect",
    "demote-not-remove": "the alternative is dimmed/kept in place, never removed",
    "streaming-reveal": "progress is shown as the content streaming in, not a spinner",
    "gate-insertion": "a confirmation/threshold step inserted before the consequence",
    "reactive-continuous": "an element continuously tracks the pointer/attention with no state change",
    "spring-physics": "custom spring or decay physics rather than a standard easing curve",
    "cross-highlight": "hovering/selecting one entity emphasizes its counterpart elsewhere",
}


class Qualifiers(BaseModel):
    frequency: Frequency
    stakes: Stakes
    reversibility: Reversibility
    blast: Blast
    latency: Latency
    initiative: Initiative

    def summary(self) -> str:
        return (f"{self.initiative}-driven, {self.frequency}, {self.stakes} stakes, "
                f"{self.reversibility}, {self.blast}, {self.latency}")


class InteractionSpec(BaseModel):
    moment: str
    qualifiers: Qualifiers
    treatment_features: set[str]
    params: dict[str, Any] = Field(default_factory=dict)

    def features(self) -> set[str]:
        return set(self.treatment_features)


class DefaultInteraction(BaseModel):
    model_config = {"extra": "forbid"}
    treatment_features: list[TreatmentFeature]

    def features(self) -> set[str]:
        return set(self.treatment_features)
