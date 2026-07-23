"""Axis A of the salience detector: the consumer agent generates the baseline.

We ask the SAME model class that would consume the product system: "given this
element's role, what's the default material you'd build?" The structural diff
between observed and this default IS the delta.

Integrity rule: the baseline must be a real model generation, never authored by
us — otherwise we're hand-drawing the thing we claim to detect.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
from rubrick import paths

import anthropic

from rubrick.material import DefaultMaterial

_CACHE = paths.cache_dir() / "baseline_cache.json"

_PROMPT = """You are the coding agent that will build this UI.

For an element with role "{role}" ({desc}), output the DEFAULT material you would \
use with no special design direction — the obvious, competent baseline a good \
engineer reaches for without being told to make it special.

A material is an ordered stack of layers. Layer roles:
- base: the fill color
- sheen: a directional gradient simulating gloss/oil-slick
- lighting: radial highlights/shadows simulating environmental light on a surface
- texture: a repeating micro-pattern (foil grain, scanlines)
- bevel: a lit edge rendered as a border-gradient
- shadow: a drop shadow

Only include the layers a competent DEFAULT would have. Do not add flourishes, \
gloss, simulated lighting, foil, or lit bevels unless they are genuinely the \
obvious default for this role. Set neutral=true when a layer uses only white/black \
at low alpha (no hue)."""


def content_key(source: str) -> str:
    """A cache key bound ONLY to the observed SOURCE (no caller prefix), so extraction
    is CANONICAL per input: the same source resolves to ONE cache entry no matter who
    asks — a compile and a later conformance check of identical code SHARE the entry, so
    self-conformance is exact; any edit resolves to a new entry and re-extracts. This is
    the determinism mechanism — opus-4-8 accepts no temperature, so we can't sample
    deterministically; instead a given source's observation is stable and reused.
    (The extractors already namespace by facet, so a bare content hash can't collide.)"""
    return "src-" + hashlib.sha1(source.encode()).hexdigest()[:16]


def _key_from_dotenv(path: pathlib.Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def load_key() -> str | None:
    """Resolve the Anthropic API key from portable sources, in priority order:

    1. ANTHROPIC_API_KEY environment variable (standard; how the MCP server runs).
    2. RUBRICK_ENV_FILE — a dotenv path the user points at explicitly.
    3. .env.local / .env under the data home (RUBRICK_HOME or cwd).
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]

    override = os.environ.get("RUBRICK_ENV_FILE")
    if override and (key := _key_from_dotenv(pathlib.Path(override).expanduser())):
        return key

    for name in (".env.local", ".env"):
        if key := _key_from_dotenv(paths.home() / name):
            return key

    return None


# Backwards-compatible alias — every module imports `_load_key`.
_load_key = load_key


def _read_cache() -> dict:
    if _CACHE.exists():
        return json.loads(_CACHE.read_text())
    return {}


def _write_cache(cache: dict) -> None:
    _CACHE.write_text(json.dumps(cache, indent=2))


def generate_default(role: str, desc: str, *, use_cache: bool = True) -> DefaultMaterial:
    cache = _read_cache()
    if use_cache and role in cache:
        return DefaultMaterial.model_validate(cache[role])

    key = _load_key()
    if not key:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY found. Set the env var, point RUBRICK_ENV_FILE "
            "at a dotenv, or add a .env.local in the Rubrick directory."
        )

    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=2000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _PROMPT.format(role=role, desc=desc)}],
        output_format=DefaultMaterial,
    )
    result = resp.parsed_output
    if result is None:
        raise RuntimeError(f"Baseline generation returned no parsed output for {role!r}")

    cache[role] = result.model_dump()
    _write_cache(cache)
    return result
