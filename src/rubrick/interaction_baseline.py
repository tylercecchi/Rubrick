"""Axis A for interactions: the consumer agent generates the default treatment.

"Given a <moment> with these qualifiers, what treatment features would you build
by default, with no special direction?" The diff between observed and this
default is the delta. Same integrity rule: must be a real generation.
"""

from __future__ import annotations

import json
import pathlib
from rubrick import paths

import anthropic

from rubrick.baseline import _load_key
from rubrick.interaction import TREATMENT_DESCRIPTIONS, DefaultInteraction, Qualifiers

_CACHE = paths.cache_dir() / "interaction_baseline_cache.json"

_PROMPT = """You are the coding agent that will build this UI.

For a "{moment}" interaction ({quals}), list the treatment features you would \
implement by DEFAULT — the obvious, competent behavior a good engineer reaches \
for without being told to make it special or expressive.

Available treatment features:
{features}

Include only the features a competent DEFAULT would have for this moment. Do NOT \
add ceremony, choreography, manufactured delay, spring physics, or continuous \
reactive effects unless they are genuinely the obvious default here. A plain fade \
or an instant update needs no feature listed."""


def _features_block() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in TREATMENT_DESCRIPTIONS.items())


def _read_cache() -> dict:
    return json.loads(_CACHE.read_text()) if _CACHE.exists() else {}


def _write_cache(c: dict) -> None:
    _CACHE.write_text(json.dumps(c, indent=2))


def generate_default(moment: str, quals: Qualifiers, *, use_cache: bool = True) -> DefaultInteraction:
    key = f"{moment}|{quals.summary()}"
    cache = _read_cache()
    if use_cache and key in cache:
        return DefaultInteraction.model_validate(cache[key])

    api_key = _load_key()
    if not api_key:
        raise RuntimeError("No ANTHROPIC_API_KEY — interaction baseline needs a real generation.")

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=1500,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _PROMPT.format(
            moment=moment, quals=quals.summary(), features=_features_block(),
        )}],
        output_format=DefaultInteraction,
    )
    result = resp.parsed_output
    if result is None:
        raise RuntimeError(f"Interaction baseline returned nothing for {moment!r}")

    cache[key] = result.model_dump()
    _write_cache(cache)
    return result
