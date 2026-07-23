"""Typography as a PRODUCT-SYSTEM facet — a new dimension, sibling to surface and
behavior. Captures the DELTAS + DISPOSITION (typography-as-identity), NOT the
type-scale values (that would be a design system, which we deliberately avoid).

Same principle as everywhere: only what's non-generic. Generic = system fonts
(Inter/Roboto/system-ui), a plain scale, regular weights. The identity lives in
the divergence from that.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

# The closed delta vocabulary — distinctive, identity-bearing typographic moves.
# Generic type (system face, plain scale) has NONE of these. Open via novel_features.
TYPE_FEATURE_DESCRIPTIONS = {
    "custom-display-face": "a distinctive non-system typeface for identity/headlines",
    "distinct-body-face": "a separate functional typeface for body/data",
    "extreme-scale-contrast": "very large display sizes set against very small labels",
    "type-as-graphic": "oversized type used as a visual/texture element, not just to read",
    "expressive-weight": "black / ultrabold / condensed display weights",
    "detailed-face": "a typeface with distinctive display detailing (inktraps, condensed)",
    "treated-microtype": "small labels in uppercase with wide letter-spacing",
}


class GroundedFace(BaseModel):
    name: str
    kind: str   # "system-font" | "custom"
    role: str   # "display" | "body" | "label"
    evidence: str


class GroundedTypeFeature(BaseModel):
    feature: str  # OPEN str (base vocab + promoted), not a closed Literal
    evidence: str


class NovelTypeFeature(BaseModel):
    name: str
    evidence: str


class TypeObservation(BaseModel):
    faces: list[GroundedFace]
    features: list[GroundedTypeFeature]
    novel_features: list[NovelTypeFeature] = []

    def feature_set(self) -> set[str]:
        return ({f.feature for f in self.features}
                | {n.name for n in self.novel_features})

    def grounded_set(self) -> set[str]:
        """Only the KNOWN-VOCAB features — excludes novel_features, which are
        unpromoted tear-escapes invented fresh each run (so they vary run-to-run).
        Use this to build a REQUIRED conformance delta; novel features are pending-
        promotion candidates for the human loop, never hard requirements."""
        return {f.feature for f in self.features}


class DefaultType(BaseModel):
    model_config = {"extra": "forbid"}
    features: list[str]  # what a competent DEFAULT typography would have (usually few)

    def feature_set(self) -> set[str]:
        return set(self.features)
