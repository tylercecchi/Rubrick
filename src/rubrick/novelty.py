"""Open observation — the novelty surveys that keep seeing unbounded by gating.

The deterministic signatures can only detect what a detector exists for; the thesis
requires that Rubrick SEE anything a product does regardless. These two survey passes
(one model call each, content-cached like every extraction) read the product with an
OPEN vocabulary and report what the known vocabulary has no word for:

  - survey_novel_patterns: structural gesture→response interaction patterns beyond the
    known set (built-in + promoted) — plus sightings of promoted-but-not-yet-gated
    patterns, so those can be INSTRUCTED in the checklist while awaiting a detector.
  - survey_novel_facet_moves: density/elevation/ambient moves beyond the known vocab.
    These facets migrated to signature-only observation for determinism, which quietly
    closed their world (signature_facet_obs hard-codes novel_features=[]); this pass
    reopens it without touching the deterministic path — novelty is observed here,
    surfaced as a tear, and only ever GATES after promotion earns a validated detector.

Everything found lands in the review file (ps._pending), same as every other tear.
Trajectory: SEEN here -> INSTRUCTED once promoted -> GATED once a detector is admitted.
"""

from __future__ import annotations

import json
import pathlib
import re

import anthropic
from pydantic import BaseModel

from rubrick import learned, paths
from rubrick.baseline import content_key, load_key

_CACHE = paths.cache_dir() / "novelty_cache.json"

_INTERACTION_LINE = re.compile(
    r"on[A-Z]\w*=|addEventListener|useState|useReducer|useRef|setPointerCapture|"
    r"IntersectionObserver|ResizeObserver|contentEditable|draggable|onWheel|onScroll|"
    r"onKey|metaKey|ctrlKey|shiftKey|preventDefault|getContext\(|createPortal|"
    r"requestAnimationFrame|setTimeout|import\s")


def _interaction_digest(repo: str, comps: str, max_files: int = 40,
                        lines_per_file: int = 10) -> str:
    """A compact per-component digest of interaction-relevant lines (handlers, state,
    listeners, libs) — enough for the model to recognize a pattern's shape, cheap
    enough to survey the WHOLE product in one call."""
    from rubrick.discover import discover_components
    blocks = []
    for f in discover_components(repo, comps)[:max_files]:
        try:
            text = pathlib.Path(f).read_text()
        except Exception:
            continue
        keep = [l.strip()[:160] for l in text.splitlines() if _INTERACTION_LINE.search(l)]
        if keep:
            blocks.append(f"// {pathlib.Path(f).name}\n" + "\n".join(keep[:lines_per_file]))
    return "\n\n".join(blocks)


class Sighting(BaseModel):
    name: str        # OPEN str — kebab-case pattern/move name
    component: str = ""
    evidence: str


class PatternSurvey(BaseModel):
    novel: list[Sighting] = []
    unverified_seen: list[Sighting] = []


class FacetSighting(BaseModel):
    facet: str       # density | elevation | ambient
    name: str        # OPEN str
    evidence: str


class FacetSurvey(BaseModel):
    novel: list[FacetSighting] = []


def _cached_call(key: str, prompt: str, output_format, use_cache: bool = True):
    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    if use_cache and key in cache:
        return output_format.model_validate(cache[key])
    resp = anthropic.Anthropic(api_key=load_key()).messages.parse(
        model="claude-opus-4-8", max_tokens=2500, thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}], output_format=output_format)
    out = resp.parsed_output
    if out is None:
        raise RuntimeError("novelty survey returned no parsed output")
    cache[key] = out.model_dump()
    _CACHE.write_text(json.dumps(cache, indent=2))
    return out


_PATTERN_PROMPT = """Here is a per-component digest of a product's interaction code
(handlers, state, listeners, libraries). Survey its INTERACTION PATTERNS — the structural
gesture→response archetypes (what an interaction IS: e.g. a carousel's sequential
traversal, drawing with the pointer, select-one-dim-the-rest), NOT its animation styling.

KNOWN vocabulary (do NOT report these as novel):
{known}

Report:
- novel: real, grounded patterns that fit NO known name — a distinctive structural
  gesture→response the product clearly implements. Name each in kebab-case with the
  component and the specific code evidence. Do not force-fit, do not invent; an empty
  list is the correct answer for a product with only known/generic interactions.
- unverified_seen: sightings of exactly these not-yet-verified known patterns, if the
  product implements them: {unverified}

DIGEST:
{digest}"""

_FACET_PROMPT = """Here is style-relevant source from a product (spacing/depth/motion).
Survey it for NOVEL identity moves in three facets — density (spatial strategy),
elevation (z-axis/depth expression), ambient (perpetual untriggered motion).

KNOWN vocabulary (do NOT report these — only what fits NO known name):
{known}

Report real, grounded, DISTINCTIVE moves only (a product-identity signal a generic build
would not have), each with its facet, a kebab-case name, and specific code evidence. Do
not force-fit or invent; an empty list is the correct answer for a conventional product.

SOURCE:
{source}"""


def survey_novel_patterns(repo: str, gcss: str, comps: str, *, use_cache: bool = True) -> PatternSurvey:
    from rubrick.components import PATTERN_DESCRIPTIONS
    from rubrick.detectors import learned_names
    digest = _interaction_digest(repo, comps)
    if not digest:
        return PatternSurvey()
    known = dict(PATTERN_DESCRIPTIONS) | learned.promoted_patterns()
    unverified = sorted(set(learned.promoted_patterns()) - learned_names("pattern"))
    prompt = _PATTERN_PROMPT.format(
        known="\n".join(f"- {k}: {v}" for k, v in sorted(known.items())),
        unverified=unverified or "(none)", digest=digest)
    return _cached_call("patterns:" + content_key(prompt), prompt, PatternSurvey,
                        use_cache=use_cache)


def survey_novel_facet_moves(repo: str, gcss: str, comps: str, *, use_cache: bool = True) -> FacetSurvey:
    from rubrick.style_facets import FACETS, gather_facet_source
    known = []
    for facet in ("density", "elevation", "ambient"):
        vocab = dict(FACETS[facet]["vocab"]) | learned.promoted_facets(facet)
        known += [f"- {facet}/{k}: {v}" for k, v in sorted(vocab.items())]
    src = "\n\n".join(f"=== {facet} ===\n" + gather_facet_source(repo, gcss, comps, facet)
                      for facet in ("density", "elevation", "ambient"))
    prompt = _FACET_PROMPT.format(known="\n".join(known), source=src)
    return _cached_call("facets:" + content_key(prompt), prompt, FacetSurvey,
                        use_cache=use_cache)
