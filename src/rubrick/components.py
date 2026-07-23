"""Component layer — the unit where AESTHETIC and INTERACTION meet.

The tool captures aesthetic (facets, material) and interaction (behavior) separately and
globally, so it loses the BINDING: which aesthetic rides with which interaction on which
recurring part. A product's focal card might be [lit material] x [swap traverse]; its overlay
[floating panel] x [opens-over-canvas]. That binding is what makes a component read as one
deliberate object. This layer captures the product's few IDENTITY-BEARING component ROLES —
not component code (that would be a design system), but the disposition RECIPE (affordance +
aesthetic + interaction) from which a component is CREATED.

Capture is ~all reuse: the two richness rankers select the roles, extract_focal_surface gives
the material, detect_treatments gives the interaction. The one new piece is a deterministic
AFFORDANCE read (opens-over-canvas vs expands-in-place vs replaces-subject) — the structural
"what it does" signal. Everything checked is deterministic; the role name is a label from the
filename (no LLM), so a ComponentRecord self-conforms exactly and can't flap.
"""

from __future__ import annotations

import pathlib
import re

from rubrick.detect_treatments import detect_treatments
from rubrick.extract_css import extract_focal_surface


def _kebab(stem: str) -> str:
    """A stable role label from a component filename: OpponentCard -> opponent-card."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", stem)
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def detect_affordance(source: str) -> str:
    """The RESPONSE a component produces — the structural 'what it does' that treatment
    choreography alone can't distinguish (an overlay and a dropdown can move identically).
    Deterministic, read from the component's own file. Signals are STRICT: absolute-positioned
    light/badge layers are not a dropdown, a sticky header is not an overlay. Priority runs
    most-specific → least; each needs an unambiguous marker."""
    s = source
    # open-drawer: a panel pinned to ONE edge that slides in (fixed + edge + slide), not a
    # covering overlay.
    if re.search(r"position:\s*[\"']?fixed", s) \
            and re.search(r"(?:top|right|bottom|left)\s*:\s*0\b", s) \
            and re.search(r"translate[XY]\(|<Drawer\b|\bdrawer\b", s, re.I) \
            and not re.search(r"inset:\s*0", s):
        return "open-drawer"
    # opens-over-canvas: a NEW layer that COVERS — portal/dialog/modal, or fixed + inset/backdrop.
    if re.search(r"createPortal|role=[\"']dialog|aria-modal|<(?:Modal|Dialog|Lightbox)\b", s) \
            or (re.search(r"position:\s*[\"']?fixed", s)
                and re.search(r"inset:\s*0|\bbackdrop\b|scrim", s, re.I)):
        return "opens-over-canvas"
    # zoom-to: zoom into a map/canvas — needs an EXPLICIT map/canvas element or zoom control,
    # not a hover micro-scale plus an array `.map()` (which read a nav rail as zoom-to).
    if re.search(r"\bzoomTo\b|fitBounds|setZoom|\.setView\b|useZoom\b|mapbox|maplibre|leaflet"
                 r"|<Map\b|<MapGL|<Canvas\b|<Stage\b|data-map\b"
                 r"|className=[\"'`][^\"'`]*\b(?:map|canvas|stage|viewport)\b", s):
        return "zoom-to"
    # expands-in-place: a GENUINE dropdown/menu/disclosure (aria/role/component marker).
    if re.search(r"aria-expanded|role=[\"'](?:menu|listbox|combobox)|<(?:Dropdown|Popover|Menu|"
                 r"Disclosure|Accordion|Combobox|Select)\b", s):
        return "expands-in-place"
    # expand: an in-place size transition (height/width) toggled open — grows in place.
    if re.search(r"transition:[^;{}]*(?:height|width|max-height)", s, re.I) \
            and re.search(r"expand|collapse|isOpen|\bopen\b", s, re.I):
        return "expand"
    # replaces-subject: the same container shows a DIFFERENT subject, in place (a swap).
    if re.search(r"\bswap\b|replace[s]?[- ]?(?:its |the |own )?subject|\bin[- ]?place\b|"
                 r"setActive(?:Reference|Team|Item|Subject|View|Entity|Index)\b", s, re.I):
        return "replaces-subject"
    return "inline"


# distinctive gestures — a specific gesture IS identity ("drag to re-tune", "hover to preview");
# a plain click is the default and doesn't gate.
_DISTINCTIVE_GESTURES = {"drag", "double-click", "hover", "scroll"}


def detect_gesture(source: str) -> str:
    """The primary GESTURE that triggers a component's response — the trigger half of an
    interaction pattern (gesture → response). Deterministic, from the component's handlers."""
    s = source
    if (re.search(r"pointermove|onPointerMove|mousemove", s, re.I)
            and re.search(r"onPointerDown|setPointerCapture|isDragging|dragging|onDragStart", s, re.I)) \
            or re.search(r"\bdraggable\b|useDrag\b|onDragStart", s):
        return "drag"
    if re.search(r"onDoubleClick|onDblClick", s):
        return "double-click"
    if re.search(r"onClick|onTap|onPress\b", s):
        return "click"
    if re.search(r"onMouseEnter|onPointerEnter|onMouseOver", s):
        return "hover"
    if re.search(r"onWheel|onScroll", s):
        return "scroll"
    return "none"


def _behavior_source(path: str, css: str, repo: str) -> str:
    from rubrick.orchestrate import _gather_component_behavior
    return _gather_component_behavior(path, css, repo)


def component_signature(path: str, css: str, repo: str) -> dict:
    """One component's role recipe: its material (aesthetic), treatments (interaction), and
    affordance — all from detectors we already have, pointed at a single component."""
    try:
        material = set(extract_focal_surface(path).material_roles())
    except Exception:
        material = set()
    bsrc = _behavior_source(path, css, repo)
    own = pathlib.Path(path).read_text()
    return {
        "role": _kebab(pathlib.Path(path).stem),
        # gesture + affordance from the component's OWN file — its structure, not shared imports
        # (a swap hook pulled into every gather would make every component read 'replaces-subject').
        # Together they are the interaction pattern: gesture → response.
        "gesture": detect_gesture(own),
        "affordance": detect_affordance(own),
        "material_roles": material,
        "treatments": detect_treatments(bsrc),
    }


def _identity_bearing(sig: dict) -> bool:
    """IDENTITY-defining, not merely rich. The product's signature parts carry either its real
    MATERIAL (a genuine lit object — ≥2 layers) or a CORE interaction (≥3 identity treatments).
    A peripheral utility that is only distinctive by an affordance — a lone changelog modal —
    is rich but NOT identity, and must not become a required role (trial over-captured it).
    Same delta-from-generic discipline as everything else, applied with 'is this central?'."""
    return (len(sig["material_roles"]) >= 2 or len(sig["treatments"]) >= 3
            or sig.get("gesture") in _DISTINCTIVE_GESTURES)  # a distinctive gesture IS identity


def capture_components(repo: str, comps: str, css: str, limit: int = 3) -> list[dict]:
    """The product's few identity-bearing component roles, ranked by combined material +
    interaction richness (reusing the same signals surface and behavior rank on). Returns the
    role recipes (aesthetic x interaction x affordance), deterministically."""
    d = pathlib.Path(repo) / comps
    if not d.exists():
        return []
    sigs = []
    for cpath in sorted(d.rglob("*.tsx"))[:40]:
        sig = component_signature(str(cpath), css, repo)
        if _identity_bearing(sig):
            sig["_richness"] = len(sig["material_roles"]) + len(sig["treatments"]) \
                + (1 if sig["affordance"] != "inline" else 0) \
                + (1 if sig.get("gesture") in _DISTINCTIVE_GESTURES else 0)  # a distinctive gesture ranks up
            sigs.append(sig)
    sigs.sort(key=lambda s: s["_richness"], reverse=True)
    for s in sigs:
        s.pop("_richness", None)
    return sigs[:limit]
