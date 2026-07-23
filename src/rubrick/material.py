"""Canonical material representation — the schema both observed and default speak.

A material is an ordered stack of layers. We only reason structurally: which
*roles* are present, whether overlays are neutral, and (from observed fixtures)
how coherent / specific / effortful the composition is. Raw pixel values never
enter the diff.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# The vocabulary. `base` is the fill; the rest are the depth/material signals.
LayerRole = Literal["base", "sheen", "lighting", "texture", "bevel", "shadow"]
LayerKind = Literal[
    "solid",
    "linear-gradient",
    "radial-set",
    "repeating-linear",
    "border-gradient",
    "box-shadow",
]

# Roles that count as "beyond a competent flat default" — the delta signal.
# base is the fill; shadow is generic enough that we don't count it.
MATERIAL_ROLES: set[str] = {"sheen", "lighting", "texture", "bevel"}


class Layer(BaseModel):
    """A rich layer, used by hand-authored observed fixtures.

    `alpha` is a TYPED quantity: the overlay's peak opacity. Kept separate from
    `params` so calibration can't confuse it with a gradient-stop *position* or
    any other loose float (the 0.58 bug). params holds structural-only values
    (angle, stops, period, light anchors) that are not calibration-relevant.
    """

    role: LayerRole
    kind: LayerKind
    neutral: bool = True  # overlay uses only white/black alpha (transferable) vs a hue
    alpha: float | None = None  # peak overlay opacity (overlays only)
    params: dict[str, Any] = Field(default_factory=dict)


class MaterialStack(BaseModel):
    role: str  # the element role this material applies to
    layers: list[Layer]
    geometry: dict[str, Any] = Field(default_factory=dict)

    # ---- structural features (all derived, never raw values) ----

    def material_roles(self) -> set[str]:
        return {l.role for l in self.layers if l.role in MATERIAL_ROLES}

    def overlays_all_neutral(self) -> bool:
        overlays = [l for l in self.layers if l.role != "base"]
        return all(l.neutral for l in overlays) if overlays else True

    def has_top_keyed_lighting(self) -> bool:
        """Coherence signal: a lighting pass anchored to one top light source."""
        for l in self.layers:
            if l.role == "lighting":
                lights = l.params.get("lights", [])
                return any("top" in str(x.get("role", "")) for x in lights)
        return False


# ---- default material as returned by the consumer agent (minimal, strict) ----


class DefaultLayer(BaseModel):
    model_config = {"extra": "forbid"}
    role: LayerRole
    kind: LayerKind
    neutral: bool


class DefaultMaterial(BaseModel):
    model_config = {"extra": "forbid"}
    layers: list[DefaultLayer]

    def material_roles(self) -> set[str]:
        return {l.role for l in self.layers if l.role in MATERIAL_ROLES}
