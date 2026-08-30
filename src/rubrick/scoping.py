"""Effect-locality scoping — which vocabulary moves get a deployment frequency.

A move's identity includes WHERE it's deployed only if its effect is ELEMENT-LOCAL (a
texture, a glow, a loop — more deployments = more visual effect, so reservedness is a
design decision worth capturing). A PAGE-GLOBAL move (full-bleed, an overall density
posture, safe-area handling) shapes the whole page from one declaration, so counting the
files that declare it is meaningless.

That locality is a property of the VOCABULARY WORD, not of any product — and per the
integrity rule (never hand-author what you claim to detect) it is GENERATED, not curated:
the model classifies each word once, the result caches globally and compounds, and a
designer can override it in learned.json (same pattern as disposition rationales). New
words promoted through the human loop are classified at promotion time, so the deployment
channel covers self-extended vocabulary automatically — the failure mode this replaces
was a hand-curated whitelist that could never know about promoted moves.

Resolution order: learned override -> global cache -> model classification.
Classification runs only on the COMPILE path; the check side measures prevalence for
exactly the moves a system stored, keeping the gate deterministic.
"""

from __future__ import annotations

import json

import anthropic
from pydantic import BaseModel

from rubrick import learned, paths
from rubrick.baseline import load_key

_CACHE = paths.cache_dir() / "locality_cache.json"

ELEMENT_LOCAL = "element-local"
PAGE_GLOBAL = "page-global"

_PROMPT = """A product-system vocabulary word names a visual/motion identity move. \
Classify its EFFECT LOCALITY:

- element-local: the effect lives on the element that carries it (a texture, a glow, an \
ambient loop, an oversized graphic headline, a dramatic shadow). Deploying it on more \
elements multiplies the visual effect — so HOW OFTEN a product deploys it is part of the \
product's identity (a reserved focal accent vs wallpaper).
- page-global: one declaration shapes the whole page or the product's overall posture (a \
full-bleed layout, an information-density strategy, safe-area handling, a global tint, a \
body typeface choice). The effect is experienced everywhere regardless of how many files \
declare it, so deployment frequency is meaningless.

Classify by where the EFFECT is felt, not where the code lives.

Word: "{move}" — {desc} (facet: {facet})."""


class LocalityOut(BaseModel):
    model_config = {"extra": "forbid"}
    locality: str  # "element-local" | "page-global"
    reason: str


def _description(facet: str, move: str) -> str:
    from rubrick.style_facets import FACETS
    from rubrick.typography import TYPE_FEATURE_DESCRIPTIONS
    if facet in FACETS and move in FACETS[facet]["vocab"]:
        return FACETS[facet]["vocab"][move]
    if facet == "typography" and move in TYPE_FEATURE_DESCRIPTIONS:
        return TYPE_FEATURE_DESCRIPTIONS[move]
    return learned.promoted_facets(facet).get(move) or "no description available"


def move_locality(facet: str, move: str, *, use_cache: bool = True) -> str:
    """The move's effect locality: learned override -> cache -> model (cached forever)."""
    override = learned.locality_override(f"{facet}:{move}")
    if override:
        return override
    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    key = f"{facet}:{move}"
    if use_cache and key in cache:
        return cache[key]["locality"]
    client = anthropic.Anthropic(api_key=load_key())
    for attempt in (1, 2):  # one retry — a cold compile makes many calls in a row and a
        try:               # single transient API error must not cost the whole channel
            resp = client.messages.parse(
                model="claude-opus-4-8", max_tokens=500, thinking={"type": "adaptive"},
                messages=[{"role": "user",
                           "content": _PROMPT.format(move=move, desc=_description(facet, move), facet=facet)}],
                output_format=LocalityOut)
            break
        except Exception:
            if attempt == 2:
                raise
    out = resp.parsed_output
    loc = ELEMENT_LOCAL if out and out.locality.strip().lower().startswith("element") else PAGE_GLOBAL
    cache[key] = {"locality": loc, "reason": (out.reason if out else "no parsed output")}
    _CACHE.write_text(json.dumps(cache, indent=2))
    return loc


def element_local_moves(facet: str, moves: set[str]) -> set[str]:
    """The element-local subset of a facet's moves — the ones whose deployment
    frequency is measured and instructed. Compile-path only (may call the model for
    words not yet classified). Per-word isolation: a word whose classification fails
    even after retry is skipped THIS compile (it classifies next time) — one bad call
    must never empty the whole deployment channel."""
    out = set()
    for m in sorted(moves):
        try:
            if move_locality(facet, m) == ELEMENT_LOCAL:
                out.add(m)
        except Exception:
            continue
    return out
