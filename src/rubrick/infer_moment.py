"""Moment inference: structural interaction facts -> moment + qualifiers, via the
consumer agent. Mirrors infer.py (role inference), one level over.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from rubrick import paths

import anthropic

from rubrick import learned
from rubrick.baseline import _load_key
from rubrick.moment_context import MomentContext
from rubrick.moment_vocab import MOMENT_VOCAB, InferredMoment

_CACHE = paths.cache_dir() / "moment_cache.json"

_PROMPT = """You are analyzing a UI interaction to determine its abstract, \
feature-agnostic MOMENT (the event it is) and its context qualifiers.

You are given ONLY structural facts (trigger, effect on view/state, what it \
affects, frequency/reversibility cues). You deliberately have NO information \
about how it is animated (no timing, easing, choreography). Classify by \
structural function alone.

Moment vocabulary (the base set — extensible):
{vocab}
{guidance}

Also infer the qualifiers:
- frequency: once-ever | rare | occasional | constant
- stakes: trivial | recoverable | costly | irreversible
- reversibility: free-undo | effortful-undo | none
- blast: self-local | self-global | others | external-world
- latency: instant | async
- initiative: user | system

Structural context:
{context}

Return the single best moment, the qualifiers, your confidence (0-1), the \
runner-up moment (or null), and a one-line rationale. If the interaction is a \
genuinely distinct EVENT that no listed moment captures, NAME a new short \
kebab-case moment for it (don't force-fit, and prefer a real name over "other") — \
it becomes a candidate the designer can promote into the vocabulary."""


def _vocab_block() -> str:
    vocab = {**MOMENT_VOCAB, **learned.promoted_moments()}
    return "\n".join(f"- {k}: {v}" for k, v in vocab.items())


def _read_cache() -> dict:
    return json.loads(_CACHE.read_text()) if _CACHE.exists() else {}


def _write_cache(c: dict) -> None:
    _CACHE.write_text(json.dumps(c, indent=2))


def infer_moment(element_id: str, ctx: MomentContext, *,
                 guidance: str = "", use_cache: bool = True) -> InferredMoment:
    # promoted moments extend the vocab, so they must bust the cache (a stale entry
    # would never surface a newly-promoted moment) — same discipline as guidance.
    promoted = learned.promoted_moments()
    salt = guidance + ("|promoted:" + ",".join(sorted(promoted)) if promoted else "")
    cache_key = element_id
    guidance_section = ""
    if salt:
        h = hashlib.sha1(salt.encode()).hexdigest()[:8]
        cache_key = f"{element_id}::{h}"
    if guidance:
        guidance_section = (
            "\nProduct-specific moment boundaries the designer has confirmed — apply these:\n"
            + guidance + "\n")

    cache = _read_cache()
    if use_cache and cache_key in cache:
        return InferredMoment.model_validate(cache[cache_key])

    key = _load_key()
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY — moment inference needs a real generation.")

    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=1500,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _PROMPT.format(
            vocab=_vocab_block(), guidance=guidance_section,
            context=json.dumps(ctx.model_dump(), indent=2))}],
        output_format=InferredMoment,
    )
    result = resp.parsed_output
    if result is None:
        raise RuntimeError(f"Moment inference returned nothing for {element_id!r}")

    cache[cache_key] = result.model_dump()
    _write_cache(cache)
    return result
