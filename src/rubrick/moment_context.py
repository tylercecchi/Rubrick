"""Structural context for interactions — the ONLY input to moment inference.

Strictly treatment-free (no timing, easing, choreography, spring physics): what
triggers it, what it does to view/state, what it affects, frequency/reversibility
cues. The independent structural channel that must not leak the surface channel.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Trigger = Literal["user-action", "user-hover", "pointer-track", "system"]
ViewEffect = Literal["reorders-peers", "flips-binary-state", "changes-subject",
                     "highlights-item", "reveals-panel", "none"]
PersistentEffect = Literal["creates", "edits", "removes", "none"]
Affects = Literal["one-element", "two-peers", "a-collection", "whole-view"]
FreqCue = Literal["once", "rare", "occasional", "constant"]
RevCue = Literal["free", "effortful", "none"]


class MomentContext(BaseModel):
    trigger: Trigger
    view_effect: ViewEffect
    persistent_effect: PersistentEffect
    affects: Affects
    frequency_cue: FreqCue
    reversibility_cue: RevCue


# id, context, true abstract moment (label used ONLY to score, never fed in)
CONTEXTS: list[tuple[str, MomentContext, str]] = [
    ("swap", MomentContext(
        trigger="user-action", view_effect="reorders-peers", persistent_effect="none",
        affects="two-peers", frequency_cue="rare", reversibility_cue="free"), "restructure"),
    ("side-toggle", MomentContext(
        trigger="user-action", view_effect="flips-binary-state", persistent_effect="none",
        affects="whole-view", frequency_cue="constant", reversibility_cue="free"), "toggle"),
    ("schedule-hover", MomentContext(
        trigger="user-hover", view_effect="highlights-item", persistent_effect="none",
        affects="a-collection", frequency_cue="constant", reversibility_cue="free"), "browse"),
    ("parallax-shadow", MomentContext(
        trigger="pointer-track", view_effect="none", persistent_effect="none",
        affects="one-element", frequency_cue="occasional", reversibility_cue="free"), "enliven"),
]
