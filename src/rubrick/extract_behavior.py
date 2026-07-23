"""Mode B for BEHAVIOR — extract an interaction from real repo source.

Unlike CSS, behavior is scattered: an event handler + state-driven JSX styles +
CSS keyframes. The semantic parts (what the state change *does*) can't be regex'd,
so this is LLM-assisted extraction GROUNDED in the actual gathered source: the
agent must cite specific code for every treatment feature it reports, which guards
against inventing features that aren't there.

Gathering (which code to read) is mechanical; interpretation is the agent's.
"""

from __future__ import annotations

import json
import pathlib
from rubrick import paths
from typing import Optional

import hashlib

import anthropic
from pydantic import BaseModel

from rubrick import learned
from rubrick.baseline import _load_key
from rubrick.interaction import TREATMENT_DESCRIPTIONS
from rubrick.moment_context import (Affects, FreqCue, PersistentEffect, RevCue, Trigger,
                            ViewEffect)

_CACHE = paths.cache_dir() / "behavior_cache.json"


def _braced(text: str, anchor: str) -> str:
    i = text.find(anchor)
    if i < 0:
        return ""
    j = text.find("{", i)
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return text[i:k + 1]
    return text[i:]


def gather_swap_source(tsx_path: str, css_path: str) -> str:
    tsx = pathlib.Path(tsx_path).read_text()
    css = pathlib.Path(css_path).read_text()
    handler = _braced(tsx, "function handleSwap")
    marks = ("swapping", "scalingIn", "swap-exit", "swap-enter", "handleSwap", "pointerEvents")
    usage = "\n".join(l.strip() for l in tsx.splitlines()
                      if any(m in l for m in marks) and "function handleSwap" not in l)
    kf = "\n\n".join(_braced(css, f"@keyframes {n}")
                     for n in ("swap-exit-down", "swap-exit-up", "swap-enter-scale-up"))
    return f"// handler\n{handler}\n\n// JSX usage (state-driven styles)\n{usage}\n\n/* keyframes */\n{kf}"


class GroundedFeature(BaseModel):
    """A treatment feature is inseparable from the code that grounds it — this
    makes the anti-hallucination evidence STRUCTURALLY REQUIRED, not optional."""
    # OPEN str, not the closed TreatmentFeature Literal — same lesson as roles:
    # opening the prompt vocab isn't enough, the OUTPUT schema must be open too, or
    # a promoted treatment (camera-fly) has no valid slot and stays "novel" forever.
    # The prompt (base vocab + promoted) is the source of valid names.
    feature: str
    evidence: str  # the specific code that grounds this feature


class NovelTreatment(BaseModel):
    """The tear-escape: a real, grounded treatment that fits NO vocabulary feature.
    Without this the vocab silently drops it (the camera-fly gap). Kept as a
    candidate primitive the designer can promote."""
    name: str
    evidence: str


class ExtractedBehavior(BaseModel):
    trigger: Trigger
    view_effect: ViewEffect
    persistent_effect: PersistentEffect
    affects: Affects
    frequency_cue: FreqCue
    reversibility_cue: RevCue
    treatment_features: list[GroundedFeature]
    novel_treatments: list[NovelTreatment] = []  # tear-escape
    exit_ms: Optional[int]
    enter_ms: Optional[int]
    disorientation: Optional[float]   # 0-1, how much the view reorganizes

    def feature_set(self) -> set[str]:
        return ({g.feature for g in self.treatment_features}
                | {n.name for n in self.novel_treatments})

    def grounded_set(self) -> set[str]:
        """Known-vocab treatments only — excludes novel_treatments (unpromoted,
        run-variant). Required conformance deltas use this; novel = pending-promotion."""
        return {g.feature for g in self.treatment_features}


_PROMPT = """Here is the complete source for ONE UI interaction — the event \
handler, its state-driven JSX styles, and the CSS keyframes it references.

Extract its structure, GROUNDED IN THE CODE. Report treatment_features as a list \
of {{feature, evidence}} objects — each feature paired with the specific code line \
that grounds it. Do NOT report a feature you cannot cite code for.

If a real, grounded behavior does NOT match ANY feature in the vocabulary, put it \
in `novel_treatments` as {{name, evidence}} — invent a short name for it. Do NOT \
force it into a listed feature and do NOT drop it. Novelty must be captured, not \
silently missed.

Treatment features (closed vocabulary):
{features}

Also extract: trigger; view_effect (reorders-peers | flips-binary-state | \
changes-subject | highlights-item | reveals-panel | none); persistent_effect \
(creates | edits | removes | none — 'none' if no API/mutation, only view state); \
affects (one-element | two-peers | a-collection | whole-view); frequency_cue \
(once | rare | occasional | constant); reversibility_cue (free | effortful | \
none); the exit and enter timings in ms; and disorientation 0-1 (how much the \
view reorganizes).

SOURCE:
{source}"""


def extract_behavior(source: str, key_id: str = "swap", *, use_cache: bool = True) -> ExtractedBehavior:
    promoted = learned.promoted_treatments()
    # promoted treatments become KNOWN features; they also bust the cache
    cache_key = key_id
    if promoted:
        h = hashlib.sha1(json.dumps(promoted, sort_keys=True).encode()).hexdigest()[:8]
        cache_key = f"{key_id}::{h}"

    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    if use_cache and cache_key in cache:
        return ExtractedBehavior.model_validate(cache[cache_key])

    api_key = _load_key()
    if not api_key:
        raise RuntimeError("No ANTHROPIC_API_KEY — behavior extraction needs a real generation.")

    vocab = {**TREATMENT_DESCRIPTIONS, **promoted}
    features = "\n".join(f"- {k}: {v}" for k, v in vocab.items())
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=2500,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _PROMPT.format(features=features, source=source)}],
        output_format=ExtractedBehavior,
    )
    result = resp.parsed_output
    if result is None:
        raise RuntimeError("Behavior extraction returned nothing")
    cache[cache_key] = result.model_dump()
    _CACHE.write_text(json.dumps(cache, indent=2))
    return result


class ExtractedInteractions(BaseModel):
    """A component can hold SEVERAL distinct interactions (a discrete action AND a
    continuous reactive behavior). Each is its own event with its own moment — so we
    enumerate them separately rather than blending them into one extraction."""
    interactions: list[ExtractedBehavior]


_MULTI_PROMPT = """Here is a UI component's source — event handlers, state-driven \
JSX styles, and the CSS keyframes it references. It may contain SEVERAL DISTINCT \
interactions (for example: a discrete triggered action like a swap or open, AND a \
separate continuous/reactive behavior like a cursor-driven tilt).

ENUMERATE EACH DISTINCT INTERACTION SEPARATELY — do NOT merge a discrete action \
with a continuous reactive behavior into one. Two interactions are distinct if they \
have different triggers OR different effects on state/arrangement. Skip purely \
generic wrappers.

For EACH interaction, extract its structure GROUNDED IN THE CODE:
- treatment_features: {{feature, evidence}} objects — each cited to specific code. \
Do NOT report a feature you cannot cite. A feature that matches NO vocabulary entry \
goes in `novel_treatments` as {{name, evidence}} — name it, don't force-fit or drop.
- trigger; view_effect (reorders-peers | flips-binary-state | changes-subject | \
highlights-item | reveals-panel | none); persistent_effect (creates | edits | \
removes | none); affects (one-element | two-peers | a-collection | whole-view); \
frequency_cue (once | rare | occasional | constant); reversibility_cue (free | \
effortful | none); exit and enter timings in ms; disorientation 0-1.

Treatment features (base vocabulary):
{features}

SOURCE:
{source}"""


def extract_interactions(source: str, key_id: str, *, use_cache: bool = True) -> list[ExtractedBehavior]:
    """Enumerate the DISTINCT interactions in a component (see ExtractedInteractions).
    Fixes the multi-interaction-per-component blend: one component with a swap AND a
    reactive hover yields TWO interactions with two moments, not one blended moment."""
    promoted = learned.promoted_treatments()
    cache_key = f"multi:{key_id}"
    if promoted:
        h = hashlib.sha1(json.dumps(promoted, sort_keys=True).encode()).hexdigest()[:8]
        cache_key = f"multi:{key_id}::{h}"

    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    if use_cache and cache_key in cache:
        return ExtractedInteractions.model_validate(cache[cache_key]).interactions

    api_key = _load_key()
    if not api_key:
        raise RuntimeError("No ANTHROPIC_API_KEY — behavior extraction needs a real generation.")

    vocab = {**TREATMENT_DESCRIPTIONS, **promoted}
    features = "\n".join(f"- {k}: {v}" for k, v in vocab.items())
    resp = anthropic.Anthropic(api_key=api_key).messages.parse(
        model="claude-opus-4-8", max_tokens=4000, thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _MULTI_PROMPT.format(features=features, source=source)}],
        output_format=ExtractedInteractions,
    )
    result = resp.parsed_output
    if result is None:
        raise RuntimeError("Multi-interaction extraction returned nothing")
    cache[cache_key] = result.model_dump()
    _CACHE.write_text(json.dumps(cache, indent=2))
    return result.interactions
