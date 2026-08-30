"""Compositional spine — the product's structural archetype.

A new MODALITY (not a style facet): what the product is ORGANIZED AROUND and how
content composes against that anchor. This is UPSTREAM of behavior — the interactions
a product has are shaped by its composition (a canvas-anchored product's overlay-panel
interactions exist because there's a central surface to overlay onto). Style captures the skin; this captures
the skeleton.

Observation is holistic and structural, so it lives in the TOP-LEVEL layout (root /
page / shell / canvas components + layout-signal CSS), not scattered like style. We
gather that deterministically and infer the archetype with the model (like infer_moment).
"""

from __future__ import annotations

import pathlib
from rubrick import paths
import re
from typing import Optional

import anthropic
from pydantic import BaseModel

from rubrick.baseline import _load_key

# base archetype vocab (OPEN str — self-extending like moments). GENERIC ones mean
# "no distinctive spine" — the delta-from-generic default a coding agent produces
# with no direction.
ARCHETYPES = {
    "central-canvas": "organized around one dominant central element (map, artboard, video, 3D scene) that the product exists around",
    "feed": "a single vertical stream of items is the structure",
    "dashboard-grid": "tiles/widgets arranged in a grid",
    "split-pane": "master-detail — a list beside a detail view",
    "board": "columns/cards of a board or canvas (kanban, whiteboard)",
    "flow": "a linear step-by-step sequence (wizard)",
    "sidebar-shell": "a persistent nav sidebar framing a content area",
    "document-column": "a centered reading column (GENERIC default)",
    "stacked-sections": "stacked full-width sections down the page (GENERIC default)",
}
_GENERIC = {"document-column", "stacked-sections", "centered-column", "generic", "none"}

_LAYOUT_CSS = ("position", "inset", "z-index", "100vw", "100vh", "100dvh", "100%",
               "grid-template", "overflow", "fixed", "absolute", "sticky", "flex")
_ROOT_FILES = ("src/app/layout.tsx", "src/app/page.tsx", "src/App.tsx", "src/App.jsx",
               "src/main.tsx", "app/layout.tsx", "app/page.tsx")
_ROOT_NAME = re.compile(r"shell|layout|canvas|workspace|root|app|board|stage|deck|"
                        r"viewport|frame|grid|split|pane|map", re.I)


class CompositionObs(BaseModel):
    archetype: str
    focal_anchor: Optional[str]   # load-bearing central element, or null (feed/grid)
    composition: str              # how secondary content relates to the anchor
    evidence: str


def is_generic(archetype: str, focal_anchor: Optional[str]) -> bool:
    """No distinctive spine — a generic archetype with no focal anchor is the default."""
    return archetype.lower() in _GENERIC and not focal_anchor


def gather_composition_source(repo: str, gcss: str, comps: str) -> str:
    from rubrick.discover import discover_components
    root = pathlib.Path(repo)
    parts: list[str] = []
    seen: set[str] = set()
    for rel in _ROOT_FILES:
        p = root / rel
        if p.exists():
            seen.add(str(p))
            parts.append(f"// {rel}\n" + "\n".join(p.read_text().splitlines()[:130]))
    # shell-named files from the SHARED discovery list (components dir + src/app + …) — a
    # Workspace/Canvas living beside a page in src/app is as structural as one in components
    matched = [pathlib.Path(f) for f in discover_components(repo, comps)
               if str(pathlib.Path(f)) not in seen and _ROOT_NAME.search(pathlib.Path(f).stem)]
    for p in matched[:5]:
        parts.append(f"// {p.name}\n" + "\n".join(p.read_text().splitlines()[:130]))
    cp = root / gcss
    if cp.exists():
        css = [l for l in cp.read_text().splitlines()
               if any(k in l.lower() for k in _LAYOUT_CSS)]
        parts.append("// layout-signal CSS\n" + "\n".join(css[:45]))
    return "\n\n".join(parts)


_PROMPT = """Here is a product's TOP-LEVEL layout source — its root / page / shell /
canvas components and layout-signal CSS. Determine its COMPOSITIONAL ARCHETYPE: what
the product is ORGANIZED AROUND, grounded in the code.

- archetype: the dominant organizing pattern. Base vocabulary:
{vocab}
  If none fits, NAME a new short kebab-case archetype (don't force-fit).
- focal_anchor: the single LOAD-BEARING central element the product is built around
  and plays off of (e.g. map-canvas, artboard, video-stage, thread) — or null if the
  archetype has no single anchor (feed, dashboard-grid).
- composition: how secondary content relates to the anchor — e.g. overlaid-panels
  (float over it), docked-rails (beside it), stacked-sections, toolbar-chrome.
- evidence: cite the specific code (a full-bleed container, position:fixed overlays,
  a central <Map/>, a grid, etc.).

Judge the DOMINANT organizing structure, not minor layout details. SOURCE:
{source}"""


def infer_composition(source: str, key_id: str, *, use_cache: bool = True) -> CompositionObs:
    import json
    cache_path = paths.cache_dir() / "composition_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    if use_cache and key_id in cache:
        return CompositionObs.model_validate(cache[key_id])
    key = _load_key()
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY — composition inference needs a real generation.")
    vocab = "\n".join(f"  - {k}: {v}" for k, v in ARCHETYPES.items())
    resp = anthropic.Anthropic(api_key=key).messages.parse(
        model="claude-opus-4-8", max_tokens=1500, thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": _PROMPT.format(vocab=vocab, source=source)}],
        output_format=CompositionObs)
    result = resp.parsed_output
    if result is None:
        raise RuntimeError("Composition inference returned nothing")
    cache[key_id] = result.model_dump()
    cache_path.write_text(json.dumps(cache, indent=2))
    return result
