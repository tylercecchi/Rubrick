"""product_system.py — the emitted artifact (Phase 1.1: operative dispositions).

Records now carry DERIVED PARAMETERS and dispositions are OPERATIVE LEVERS
calibrated from the observed product, not rationale strings:

  - a Disposition holds calibrated constants (a light source + alpha ceiling; a
    ceremony scale + timing ratio) extracted from what the product actually does.
  - .generate() DERIVES params for a new context from those constants
    (a swap's timing scales with the new moment's disorientation; a surface's
    overlays are laid on any hue within the calibrated alpha band).
  - .check() validates QUANTITATIVE relationships, not just feature presence —
    it catches a candidate that has every required feature but times/weights it
    wrong for the disposition.

Still: library (.generate) + validator (.check) + blueprint (.emit_manifest),
candidates in the same structural types used to observe.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from rubrick.interaction import InteractionSpec, Qualifiers
from rubrick.material import Layer, MaterialStack

_KIND = {"sheen": "linear-gradient", "lighting": "radial-set",
         "texture": "repeating-linear", "bevel": "border-gradient"}
_TIMING_TOL = 0.25  # a candidate's timing may differ from derived by ±25%
# color-application role classes: MARKING (color as signal) vs FILL (color as ground/decoration)
_FILL_ROLES = {"ground", "surface", "decoration"}
# distinctive interaction gestures — a specific trigger IS identity; plain click is the default
_DISTINCTIVE_GESTURES = {"drag", "double-click", "hover", "scroll"}
# responses that REQUIRE a particular surface — a build whose domain lacks that surface (an EV
# garage has no map to `zoom-to`) shouldn't be failed for it. Captured, shown, but not gated.
# Gestures stay strict (drag transfers to any domain); only surface-bound responses go advisory.
_SURFACE_DEPENDENT_RESPONSES = {"zoom-to"}
# DEPLOYMENT FREQUENCY (the over-application channel). A move's identity includes WHERE it's
# deployed: a reserved texture/glow/loop applied everywhere reads as noise, not identity. A
# system-side prevalence at/below _RESERVED_MAX marks a move as reserved (it gets a DEPLOYMENT
# note and a ceiling); the ceiling fires only on a CLEAR spread — candidate prevalence beyond
# sys×_SPREAD_MULT + _SPREAD_PAD — so a candidate that IS the source always self-conforms and
# modest variation stays silent. Symmetric counterpart of the magnitude FLOORS in check_metrics.
_RESERVED_MAX = 0.35
_SPREAD_MULT = 3.0
_SPREAD_PAD = 0.15
_DEFAULT_ALPHA_CEILING = 0.15  # subtle fallback when a surface disposition is uncalibrated
_DEFAULT_CEREMONY_MS = 220.0    # fallback ceremony scale (ms per unit disorientation)
_DEFAULT_ENTER_RATIO = 0.75


@dataclass
class Disposition:
    id: str
    prior: str
    params: dict = field(default_factory=dict)  # calibrated constants (operative)

    @property
    def calibrated(self) -> bool:
        """True once operative constants have been derived from observation. An
        uncalibrated disposition still drives feature-presence checks; only the
        QUANTITATIVE checks require calibration."""
        return bool(self.params)


def _overlay_alphas(stack: MaterialStack) -> list[float]:
    # read the TYPED alpha field — no more confusing a stop position for opacity
    return [l.alpha for l in stack.layers
            if l.role != "base" and l.neutral and l.alpha is not None]


# ---- calibration: derive a disposition's operative constants from observation ----
# Used by the orchestrator on the arbitrary-repo path. Calibration is best-effort: when the
# observed data lacks the quantities, the disposition stays uncalibrated and its
# records fall back to feature-presence checks.

def calibrate_surface(disp: Disposition, observed: MaterialStack) -> Disposition:
    """Light disposition: the product's own subtle-lighting alpha band + key direction."""
    alphas = _overlay_alphas(observed)
    if alphas:
        disp.params = {"light_source": "top", "overlay_alpha_ceiling": round(max(alphas), 3)}
    return disp


def calibrate_rule(disp: Disposition, exit_ms, enter_ms, disorientation) -> Disposition:
    """Ceremony disposition: ms-per-unit-disorientation + the enter/exit timing ratio."""
    if exit_ms and disorientation and disorientation > 0:
        params = {"ceremony_scale_ms": round(exit_ms / disorientation, 1)}
        if enter_ms:
            params["enter_ratio"] = round(enter_ms / exit_ms, 3)
        disp.params = params
    return disp


@dataclass
class SurfaceRecord:
    applies_to: str
    required_roles: set[str]
    disposition: Disposition
    prevalence: float | None = None  # fraction of source files carrying rich material (reservedness)

    def check(self, cand: MaterialStack, spread: float | None = None) -> list[str]:
        v = []
        # DEPLOYMENT: the source reserves this material (low prevalence) but the build
        # wallpapers it — right material, wrong frequency. Fires only on a clear spread.
        if (self.prevalence is not None and self.prevalence <= _RESERVED_MAX
                and spread is not None
                and spread > self.prevalence * _SPREAD_MULT + _SPREAD_PAD):
            v.append(f"{self.applies_to}: rich material on {spread:.0%} of the build's components "
                     f"but the source reserves it for ~{self.prevalence:.0%} — the material reads "
                     f"as wallpaper, not a focal accent; keep it on the focal object")
        missing = self.required_roles - cand.material_roles()
        if missing:
            v.append(f"{self.applies_to}: missing material layers {sorted(missing)} "
                     f"— too flat for a lit object")
        if not cand.overlays_all_neutral():
            v.append(f"{self.applies_to}: overlays carry a hue — won't transfer across entities")
        if "lighting" in self.required_roles and "lighting" in cand.material_roles() \
                and not cand.has_top_keyed_lighting():
            v.append(f"{self.applies_to}: lighting not top-keyed — breaks the shared light environment")
        # QUANTITATIVE (only when calibrated): overlays stay within the subtle alpha band
        ceiling = self.disposition.params.get("overlay_alpha_ceiling")
        if ceiling is not None:
            hot = [a for a in _overlay_alphas(cand) if a > ceiling + 1e-6]
            if hot:
                v.append(f"{self.applies_to}: overlay α={max(hot):.2f} exceeds the system's "
                         f"subtle-lighting ceiling {ceiling:.2f} — reads as paint, not light")
        return v

    def generate(self, base_color: str) -> MaterialStack:
        ceiling = self.disposition.params.get("overlay_alpha_ceiling", _DEFAULT_ALPHA_CEILING)
        a = round(ceiling * 0.85, 3)
        layers = [Layer(role="base", kind="solid", neutral=False, params={"fill": base_color})]
        for r in ("sheen", "lighting", "texture", "bevel"):
            if r in self.required_roles:
                p = {"lights": [{"role": "top-key"}]} if r == "lighting" else {}
                layers.append(Layer(role=r, kind=_KIND[r], neutral=True, alpha=a, params=p))
        return MaterialStack(role=self.applies_to, layers=layers, geometry={"radius": 12})


@dataclass
class RuleRecord:
    applies_to: str
    required_features: set[str]
    disposition: Disposition
    exit_ms: int | None = None     # the system's own choreography timing (deterministic)
    enter_ms: int | None = None

    def check(self, cand: InteractionSpec, group: set[str] | None = None) -> list[str]:
        # A behavior is the interaction LANGUAGE, abstracted from where it lives — a decomposed
        # build splits an interaction across co-rendered components (a drag part + a create part),
        # which is correct. So treatments are checked against the GROUP (the build's interaction
        # vocabulary), not one component; timing/symmetry are read from the best-matching one.
        feats = group if group is not None else cand.features()
        v = []
        missing = self.required_features - feats
        if missing:
            v.append(f"{self.applies_to}: missing treatment {sorted(missing)}")
        if "symmetry" in self.required_features and "multi-phase" in feats \
                and "symmetry" not in feats:
            v.append(f"{self.applies_to}: choreographed but not symmetric — exchange isn't legible")
        # QUANTITATIVE timing: compare the candidate's exit against the SYSTEM'S stored exit
        # (both read deterministically), not a disorientation-derived expectation that resampled
        # every run (the "moving oracle" — no fixed duration could satisfy it). Ceremony is
        # identity: flag only a candidate markedly BRIEFER (flatter) than the system; more
        # ceremony is fine. Fires only when the system HAS ceremony (manufactured-latency).
        ce = cand.params.get("exit_ms")
        if "manufactured-latency" in self.required_features and self.exit_ms and ce is not None \
                and ce < self.exit_ms * 0.5:
            v.append(f"{self.applies_to}: exit {ce}ms is far briefer than the system's "
                     f"{self.exit_ms}ms — the interaction's ceremony is flattened, not the "
                     f"deliberate choreography of the identity")
        return v

    def generate(self, disorientation: float = 0.0) -> InteractionSpec:
        exit_ms = self.exit_ms or round(_DEFAULT_CEREMONY_MS)
        enter_ms = self.enter_ms or round(exit_ms * self.disposition.params.get("enter_ratio", _DEFAULT_ENTER_RATIO))
        return InteractionSpec(
            moment=self.applies_to,
            qualifiers=Qualifiers(frequency="rare", stakes="trivial", reversibility="free-undo",
                                  blast="self-local", latency="instant", initiative="user"),
            treatment_features=set(self.required_features),
            params={"exit_ms": exit_ms, "enter_ms": enter_ms},
        )


@dataclass
class StyleRecord:
    """A static-style facet (typography / color / density) as a runnable record.

    TWO CHANNELS, for two use cases:
      - POSTURE (required_features): the transferable identity moves, feature-agnostic.
        For "new product, borrow the soul" — reproduce with your OWN fonts/colors.
        This is the product-system-vs-design-system line.
      - CONCRETE (concrete): the grounded instantiation — actual faces, palette
        anchors, per-move evidence — bound to the identity moves. For "new feature,
        look NATIVE to this product" where reusing the real values IS the point.
        Held ONLY for the identity moves (not a full token dump), hung off the record.
    """
    facet: str                    # typography | color | density
    required_features: set[str]   # the recognised-vocab identity delta (POSTURE)
    disposition: Disposition
    concrete: dict = field(default_factory=dict)  # CONCRETE aesthetics (native mode)
    metrics: dict = field(default_factory=dict)   # QUANTITATIVE magnitudes (depth)
    application: list = field(default_factory=list)  # color kind→role BINDINGS (how applied)
    prevalence: dict = field(default_factory=dict)  # move → deployment frequency (scoped moves only)

    def check(self, candidate_features: set[str]) -> list[str]:
        req = self.required_features
        if not req:  # discipline-only record — identity is in the metrics, not moves
            return []
        if not (candidate_features & req):
            return [f"{self.facet}: generic — carries NONE of the identity moves "
                    f"{sorted(req)}; drifts to system default"]
        missing = req - candidate_features
        return ([f"{self.facet}: missing identity moves {sorted(missing)} — "
                 f"partial drift toward generic"] if missing else [])

    def check_metrics(self, cand: dict) -> list[str]:
        """QUANTITATIVE magnitude check: a move can be PRESENT yet far off the system's
        character — `extreme-scale-contrast` at 1.4x is not the same identity as at 15x. Flags
        a candidate markedly QUIETER than the calibrated magnitude (being MORE expressive is
        fine, so only the low side fails). Floors tightened to ~0.7-0.75 so 'conforms' means
        'as committed as the source', not merely present — a build at 60% reads noticeably
        tamer (the 'kin but quieter' gap the trials showed), and the sources self-conform at 1.0."""
        v = []
        ref = self.metrics.get("scale_contrast_ratio")
        got = cand.get("scale_contrast_ratio")
        if ref and got is not None and got < ref * 0.75:
            v.append(f"{self.facet}: scale-contrast {got}x is well below the system's "
                     f"{ref}x — type reads tamer, not as expressively scaled as the identity")
        rt = self.metrics.get("micro_tracking_em")
        gt = cand.get("micro_tracking_em")
        if rt and gt is not None and gt < rt * 0.7:
            v.append(f"{self.facet}: microtype tracking {gt}em is well tighter than the "
                     f"system's {rt}em — labels aren't 'treated' (wide-tracked, uppercase)")
        rw = self.metrics.get("max_weight")
        gw = cand.get("max_weight")
        if rw and gw is not None and gw < rw - 100:  # weight steps of 100; >1 step lighter
            v.append(f"{self.facet}: heaviest weight {gw} is lighter than the system's "
                     f"{rw} — weight isn't expressive/black enough for the identity")
        rc = self.metrics.get("accent_chroma")
        gc = cand.get("accent_chroma")
        if rc and gc is not None and gc < rc * 0.75:
            v.append(f"{self.facet}: accent chroma {gc} is well below the system's {rc} — "
                     f"color reads muted, not the bold/saturated accent of the identity")
        rs = self.metrics.get("density_spacing_px")
        gs = cand.get("density_spacing_px")
        if rs and gs is not None and gs > rs * 1.5:  # denser=smaller; flag much airier
            v.append(f"{self.facet}: median spacing {gs}px is well airier than the system's "
                     f"{rs}px — layout isn't information-dense like the identity")
        # MAGNITUDE: felt density — content PER COMPONENT, not just how tight the spacing is.
        # Fires only when the system is genuinely dense (≥30), flagging an empty/airy build that
        # renders far less than the source (the "empty center" both trials showed).
        rcd = self.metrics.get("content_density")
        gcd = cand.get("content_density")
        if rcd and rcd >= 30 and gcd is not None and gcd < rcd * 0.4:
            v.append(f"{self.facet}: content density {gcd} is far below the system's {rcd} — the "
                     f"build renders far less per component (empty / airy), not the packed felt "
                     f"density of the identity")
        rb = self.metrics.get("shadow_depth_px")
        gb = cand.get("shadow_depth_px")
        if rb and gb is not None and gb < rb * 0.7:
            v.append(f"{self.facet}: shadow depth {gb}px is well shallower than the system's "
                     f"{rb}px — elevation reads flatter than the identity")
        rd = self.metrics.get("spacing_discipline")  # DISCIPLINE axis (systematicity)
        gd = cand.get("spacing_discipline")
        if rd and rd >= 0.85 and gd is not None and gd < rd - 0.2:
            v.append(f"{self.facet}: spacing discipline {gd} is far below the system's {rd} — "
                     f"the layout applies its spacing scale loosely, not with the product's rigor")
        rp = self.metrics.get("palette_coherence")
        gp = cand.get("palette_coherence")
        if rp and rp >= 0.75 and gp is not None and gp < rp - 0.3:
            v.append(f"{self.facet}: palette coherence {gp} is far below the system's {rp} — "
                     f"colors are scattered ad-hoc singletons, not the product's systematic palette")
        rbg = self.metrics.get("background_tonality")  # mode polarity — light vs dark ground
        gbg = cand.get("background_tonality")
        if rbg is not None and gbg is not None:
            if rbg >= 0.6 and gbg <= 0.4:
                v.append(f"{self.facet}: the product's ground is LIGHT (tonality {rbg}) but the "
                         f"build is DARK ({gbg}) — mode polarity is inverted; a dark clone reads "
                         f"as a different product even with the right accent logic")
            elif rbg <= 0.4 and gbg >= 0.6:
                v.append(f"{self.facet}: the product's ground is DARK (tonality {rbg}) but the "
                         f"build is LIGHT ({gbg}) — mode polarity is inverted; a light clone reads "
                         f"as a different product even with the right accent logic")
        return v

    def check_application(self, cand_bindings: list) -> list[str]:
        """How color is APPLIED, not just which colors exist (kin products need both).
        Threshold-gated (middle stance): only RESERVED system bindings gate, and only a clear
        inversion fires — the system reserves a color KIND to one ROLE (a deliberate discipline)
        and the build deploys that kind OUTSIDE it. Same palette applied loosely = a different
        product. Unreserved / subtle variation stays silent; a build that simply lacks the kind
        is caught by the moves check, not here."""
        v = []
        # The real discipline is role-CLASS: saturated color MARKS (data/text/interactive/edge)
        # vs FILLS grounds/surfaces/decoration. The identity signal is a saturated kind the
        # system confines to marking and never fills with — "color signals, it doesn't decorate."
        # Derived deterministically from the bindings (self-consistent, exact self-conformance).
        # Threshold: only fires when the system HAS that discipline for a kind (no fill role) AND
        # the candidate floods that kind into a fill role — the clear inversion, nothing subtle.
        sys_roles: dict = {}
        for b in self.application:
            sys_roles.setdefault(b["kind"], set()).add(b["role"])
        cand_roles: dict = {}
        for b in cand_bindings:
            cand_roles.setdefault(b["kind"], set()).add(b["role"])
        for kind in sorted(sys_roles):
            if kind == "neutral":
                continue  # neutrals legitimately fill grounds/surfaces — that's their job
            sroles = sys_roles[kind]
            if sroles & _FILL_ROLES:
                continue  # the system itself fills with this kind → no marking-discipline to enforce
            strayed = cand_roles.get(kind, set()) & _FILL_ROLES
            if strayed:
                v.append(f"{self.facet}: the system confines its {kind} color to marking "
                         f"{sorted(sroles)} — it signals, never fills — but the build applies "
                         f"{kind} color to {sorted(strayed)}; saturated color floods surfaces "
                         f"instead of marking, breaking the discipline that makes it read as one "
                         f"product (right palette, wrong application)")
        return v

    def check_prevalence(self, cand_prevalence: dict) -> list[str]:
        """DEPLOYMENT ceiling — the symmetric counterpart of the magnitude floors above. A
        move can be PRESENT at the right magnitude and still wrong: a texture/glow/loop the
        source reserves for its focal moments, applied across the whole build, reads as
        noise, not identity. Both sides are measured by the same per-file signatures
        (facet_signatures.scoped_move_prevalence), so the source self-conforms exactly;
        only a CLEAR spread beyond the reserved frequency fires."""
        v = []
        for move in sorted(self.required_features):
            sys_p = self.prevalence.get(move)
            cand_p = cand_prevalence.get(move)
            if sys_p is None or cand_p is None or sys_p > _RESERVED_MAX:
                continue  # unscoped move, or the source itself deploys it broadly
            if cand_p > sys_p * _SPREAD_MULT + _SPREAD_PAD:
                v.append(f"{self.facet}: '{move}' is deployed across {cand_p:.0%} of the build's "
                         f"source files but the source reserves it (~{sys_p:.0%}) — over-applied; "
                         f"a reserved move used everywhere reads as noise, not identity. Keep it "
                         f"for the focal moments it marks")
        return v

    def check_native(self, candidate_concrete: dict) -> list[str]:
        """Value-conformance for a SAME-PRODUCT native feature: the concrete identity
        anchors (the actual custom faces, the signature palette) must be REUSED, not
        merely gestured at. Stricter than posture check — divergence here is
        inconsistency within one product, not healthy variation across products."""
        viol = []
        anchors = self.concrete.get("anchors", [])
        if anchors:
            have = set(candidate_concrete.get("anchors", []))
            missing = [a for a in anchors if a not in have]
            if missing:
                viol.append(f"{self.facet}: native feature must reuse {missing} — using other "
                            f"values reads as foreign to this product")
        # value->ROLE binding: the values must be in the SAME roles, not merely present. A build
        # can pass the flat anchor check with the right faces in swapped roles (Geigy display /
        # RuderPlakat body) and still read foreign. Gate the base/reading VOICE (deterministic —
        # the LLM role read is too noisy to gate). Only faceted records carry face_roles.
        fr = self.concrete.get("face_roles")
        if fr and fr.get("body"):
            cb = (candidate_concrete.get("face_roles") or {}).get("body")
            if cb and cb != fr["body"]:
                kind = "a display face" if cb in (fr.get("display") or []) else "a foreign face"
                viol.append(f"{self.facet}: body/reading voice is {cb!r} ({kind}) — a native feature "
                            f"must keep {fr['body']!r} as the base voice; right faces in the wrong "
                            f"roles read foreign")
        return viol

    def generate(self, *, native: bool = False) -> dict:
        out = {
            "facet": self.facet,
            "identity_posture": sorted(self.required_features),
            "disposition": self.disposition.prior,
            "instantiate": "reproduce these identity moves with YOUR OWN fonts/"
                           "colors/spacing — do NOT copy specific values",
        }
        if native and self.concrete:
            out["concrete"] = self.concrete
            out["instantiate"] = ("SAME-PRODUCT native feature: reuse these exact "
                                  "values (faces / palette / spacing) so the new work is "
                                  "indistinguishable from what's already here")
            fr = self.concrete.get("face_roles")
            if fr and fr.get("body"):
                out["instantiate"] += (f" — and keep each face in ITS role: {fr['body']!r} is the "
                                       f"base/reading voice, {fr.get('display')} carry display. Do "
                                       f"NOT swap them; right faces in the wrong roles read foreign.")
        return out


_GENERIC_ARCH = {"document-column", "stacked-sections", "centered-column", "generic", "none"}


@dataclass
class CompositionRecord:
    """The product's compositional SPINE — its structural archetype + the load-bearing
    focal anchor that content composes against. A distinct MODALITY, upstream of
    behavior: the interactions a product has are shaped by what it's organized around
    (right skin + wrong skeleton loses the interactions that hang off the skeleton).

    Composition is LOAD-BEARING identity (upstream of behavior), so it's stricter than
    the style facets — the ARCHETYPE must transfer even in posture. Two channels:
      - POSTURE: the archetype must match (a `central-canvas` product must be built as a
        central-canvas) — but the specific anchor can be the new product's OWN central
        element; you don't need the original's specific canvas, just A central canvas.
      - NATIVE: archetype AND the actual anchor must match (a real feature FOR the product
        lives around the product's actual central element)."""
    archetype: str
    focal_anchor: str | None
    composition: str
    disposition: Disposition

    def check(self, cand: dict, *, native: bool = False) -> list[str]:
        v = []
        c_arch = (cand.get("archetype") or "").lower()
        s_arch = self.archetype.lower()
        if s_arch not in _GENERIC_ARCH:
            # POSTURE — the archetype is the right structural direction and must transfer
            if not c_arch or c_arch in _GENERIC_ARCH:
                v.append(f"composition: generic/structureless — this product is organized as a "
                         f"{self.archetype} ({self.composition}); the build has no such spine, "
                         f"so the interactions that hang off it have nowhere to live")
            elif c_arch != s_arch:
                v.append(f"composition: {cand.get('archetype')!r} isn't the product's "
                         f"{self.archetype!r} spine — build a {self.archetype} (you can use your "
                         f"OWN central element, it need not be {self.focal_anchor!r})")
            # NATIVE — additionally reuse the product's ACTUAL anchor
            elif native and self.focal_anchor:
                c_anchor = (cand.get("focal_anchor") or "").lower()
                if c_anchor != self.focal_anchor.lower():
                    v.append(f"composition: native feature centers on {cand.get('focal_anchor')!r} "
                             f"but this product is built around {self.focal_anchor!r} — a native "
                             f"feature should live around the product's actual central element")
        return v

    def generate(self, *, native: bool = False) -> dict:
        out = {
            "modality": "composition",
            "archetype": self.archetype,
            "focal_anchor": self.focal_anchor,
            "composition": self.composition,
            "disposition": self.disposition.prior,
        }
        anchor = f" with a central {self.focal_anchor}" if self.focal_anchor else ""
        if native:
            out["instantiate"] = (f"SAME-PRODUCT native feature: reproduce this exact "
                f"{self.archetype} archetype{anchor} so the feature fits the product's structure.")
        else:
            out["instantiate"] = (f"Build the SKELETON first: organize around a {self.archetype}"
                f"{anchor}, composing secondary content as {self.composition}. The "
                "interactions hang off this structure — get it right before styling.")
        return out


@dataclass
class ComponentRecord:
    """An identity-bearing component ROLE — the unit where aesthetic and interaction meet.
    Not the component's code (that would be a design system); the disposition RECIPE from
    which a component is CREATED: its affordance (what it does), the material it carries
    (aesthetic), and the interaction it hosts. All read deterministically, so it self-conforms
    exactly. The role name is a filename-derived label; it never gates."""
    role: str
    affordance: str                                        # the RESPONSE (what it does)
    material_roles: set[str] = field(default_factory=set)
    treatments: set[str] = field(default_factory=set)
    gesture: str = "none"                                  # the TRIGGER (gesture → response)
    patterns: set[str] = field(default_factory=set)        # structural interaction PATTERNS (carousel, drawing…)

    def _bound(self) -> bool:  # binds BOTH an aesthetic and an interaction (the point of this layer)
        return bool(self.material_roles) and bool(self.treatments)

    def best_match(self, cands: list[dict]) -> tuple[dict | None, int]:
        """The candidate component whose signature best overlaps this role (material ∩ +
        treatment ∩ + affordance + gesture match). Matching by SIGNATURE, not by name."""
        def overlap(c: dict) -> int:
            return (len(self.material_roles & c["material_roles"])
                    + len(self.treatments & c["treatments"])
                    + (1 if c["affordance"] == self.affordance != "inline" else 0)
                    # a distinctive gesture (drag/hover/…) IS the pattern's identity — it must
                    # DOMINATE the match, so a drag role binds the build's drag component, not a
                    # click element that happens to share a treatment or two.
                    + (5 if c.get("gesture") == self.gesture and self.gesture in _DISTINCTIVE_GESTURES else 0)
                    # a shared structural pattern (carousel, drawing, spotlight) is likewise a
                    # stronger identity signal than an incidental shared treatment.
                    + 3 * len(self.patterns & c.get("patterns", set())))
        if not cands:
            return None, 0
        best = max(cands, key=overlap)
        return best, overlap(best)

    def check(self, best: dict, group: list[dict]) -> list[str]:
        v = []
        # BINDING (group level): the material must be on the focal OBJECT (the matched
        # component), and the interaction must live in that object's GROUP — the object plus the
        # sub-parts co-rendered with it. A well-decomposed build splits a watch into body +
        # crown; that's correct, so we don't demand one file, only that aesthetic and interaction
        # inhabit the same object-group (not scattered across unrelated parts of the app).
        if self._bound():
            # material AND interaction both checked against the GROUP (the focal object + its
            # co-rendered parts) — symmetric. A lit marker beside an interactive popover is
            # correct decomposition; only a build with NO lit object anywhere in the focal group
            # fails. (Was asymmetric: material on the single best-match, which failed when the
            # lit element was a sibling of the interactive one — e.g. a lit marker beside a popover.)
            group_material: set[str] = set().union(*(c["material_roles"] for c in group)) if group else set()
            group_treatments: set[str] = set().union(*(c["treatments"] for c in group)) if group else set()
            missing_material = self.material_roles - group_material
            missing_interaction = self.treatments - group_treatments
            if missing_material:
                v.append(f"component/{self.role}: the build's focal object-group is missing material "
                         f"{sorted(missing_material)} — no lit object among the interactive parts")
            elif missing_interaction:
                v.append(f"component/{self.role}: this role binds material with interaction "
                         f"{sorted(self.treatments)}, but the build's focal object-group never "
                         f"carries {sorted(missing_interaction)} — the interaction is absent from "
                         f"the object")
        # AFFORDANCE: the RESPONSE — same choreography, different kind of component (an overlay
        # built as a dropdown). Fires only when the role's response is distinctive AND portable —
        # surface-dependent responses (zoom-to) are advisory, not gated, so a domain without that
        # surface isn't penalized.
        if self.affordance not in ("inline", *_SURFACE_DEPENDENT_RESPONSES) \
                and best["affordance"] != self.affordance:
            v.append(f"component/{self.role}: the role's response is '{self.affordance}' but the "
                     f"build's nearest component is '{best['affordance']}' — same motion, different "
                     f"kind of component")
        # GESTURE: the TRIGGER — the interaction pattern is gesture → response. A distinctive
        # trigger (drag/hover/double-click) is identity; a plain click never gates.
        if self.gesture in _DISTINCTIVE_GESTURES and best.get("gesture") != self.gesture:
            v.append(f"component/{self.role}: the role is triggered by '{self.gesture}' but the "
                     f"build's nearest component uses '{best.get('gesture', 'none')}' — the "
                     f"interaction pattern differs (the gesture that drives the response)")
        # PATTERNS: the structural interaction archetypes (sequential-traverse, staged-disclosure,
        # pointer-authoring, spotlight-filter…). Checked against the GROUP like treatments — a
        # decomposed build may split a pattern's parts across co-rendered components; only a build
        # where the pattern exists NOWHERE in the focal group fails.
        if self.patterns:
            group_patterns: set[str] = set().union(*(c.get("patterns", set()) for c in group)) if group else set()
            missing_patterns = self.patterns - group_patterns
            if missing_patterns:
                v.append(f"component/{self.role}: the role hosts the interaction pattern(s) "
                         f"{sorted(missing_patterns)}, but the build's focal object-group carries "
                         f"none of them — the structural interaction (what it IS, not how it "
                         f"animates) is absent")
        return v

    def emit(self) -> dict:
        aff = {"replaces-subject": "swaps its own content in place — a takeover, NOT a dropdown",
               "opens-over-canvas": "opens as a layer over the canvas",
               "expands-in-place": "expands attached to its trigger (a dropdown/disclosure)",
               "inline": "sits inline"}.get(self.affordance, self.affordance)
        parts = []
        if self.material_roles:
            parts.append(f"carrying material [{', '.join(sorted(self.material_roles))}]")
        if self.treatments:
            parts.append(f"hosting interaction [{', '.join(sorted(self.treatments))}]")
        if self.patterns:
            from rubrick.components import pattern_description
            parts.append("embodying the pattern(s) " + "; ".join(
                f"'{p}' ({pattern_description(p)})" for p in sorted(self.patterns)))
        combine = " — combine the aesthetic and the interaction in the SAME object" if self._bound() else ""
        trigger = (f"On {self.gesture}, it " if self.gesture in _DISTINCTIVE_GESTURES else "")
        return {"role": self.role, "gesture": self.gesture, "affordance": self.affordance,
                "material_roles": sorted(self.material_roles), "treatments": sorted(self.treatments),
                "patterns": sorted(self.patterns),
                "instantiate": f"{trigger}{'builds' if trigger else 'Build'} a component that {aff}"
                               + (", " + " and ".join(parts) if parts else "") + combine
                               + (f" Triggered by {self.gesture}." if self.gesture in _DISTINCTIVE_GESTURES else ".")}


@dataclass
class ProductSystem:
    dispositions: dict[str, Disposition]
    surfaces: list[SurfaceRecord] = field(default_factory=list)
    rules: list[RuleRecord] = field(default_factory=list)
    styles: list[StyleRecord] = field(default_factory=list)
    composition: "CompositionRecord | None" = None
    components: list["ComponentRecord"] = field(default_factory=list)
    subtractions: list = field(default_factory=list)  # deliberate OMISSIONS (negative-space identity)
    # promoted-but-not-yet-gated interaction patterns SEEN in this product (open
    # observation): instructed via the checklist, verified only once a detector is
    # admitted — the middle stage of seen -> instructed -> gated.
    observed_patterns: list = field(default_factory=list)

    def surface_for(self, role: str):
        return next((s for s in self.surfaces if s.applies_to == role), None)

    def rule_for(self, moment: str):
        return next((r for r in self.rules if r.applies_to == moment), None)

    def style_for(self, facet: str):
        return next((s for s in self.styles if s.facet == facet), None)

    def check_style(self, facet: str, candidate_features: set[str]) -> list[str]:
        rec = self.style_for(facet)
        return rec.check(candidate_features) if rec else [f"no record for facet {facet!r}"]

    def check_surface(self, cand: MaterialStack) -> list[str]:
        rec = self.surface_for(cand.role)
        return rec.check(cand) if rec else [f"no record for role {cand.role!r}"]

    def check_rule(self, cand: InteractionSpec) -> list[str]:
        rec = self.rule_for(cand.moment)
        return rec.check(cand) if rec else [f"no record for moment {cand.moment!r}"]

    def emit_manifest(self) -> dict:
        m = {
            "dispositions": {d.id: {"prior": d.prior, "calibrated": d.params}
                             for d in self.dispositions.values()},
            "surfaces": [{"applies_to": s.applies_to, "requires": sorted(s.required_roles),
                          "because": s.disposition.id, "prevalence": s.prevalence}
                         for s in self.surfaces],
            "rules": [{"applies_to": r.applies_to, "requires": sorted(r.required_features),
                       "because": r.disposition.id, "exit_ms": r.exit_ms, "enter_ms": r.enter_ms}
                      for r in self.rules],
            "styles": [{"facet": s.facet, "identity_moves": sorted(s.required_features),
                        "because": s.disposition.id, "concrete": s.concrete,
                        "metrics": s.metrics, "application": s.application,
                        "prevalence": s.prevalence}
                       for s in self.styles],
            "composition": ({"archetype": self.composition.archetype,
                             "focal_anchor": self.composition.focal_anchor,
                             "composition": self.composition.composition,
                             "because": self.composition.disposition.id}
                            if self.composition else None),
            "components": [c.emit() for c in self.components],
            "subtractions": self.subtractions,
            "observed_patterns": self.observed_patterns,
        }
        m["_checklist"] = self._checklist()
        m["_guide"] = self._guide()
        return m

    @staticmethod
    def _why(disp: "Disposition | None") -> str:
        """The disposition's prior, trimmed to a clause — so the PRINCIPLE (not just the
        requirement) travels with each checklist line. An agent that builds to the why makes
        the right call in the 90% the checks don't cover."""
        if disp is None or not disp.prior:
            return ""
        p = disp.prior.strip()
        p = p.split(", so ")[0] if ", so " in p else p  # keep the stance, drop the mechanism tail
        return f"  WHY: {p.rstrip('.')}."

    def _checklist(self) -> list[str]:
        """An explicit, plain-language to-do of EVERY requirement — so the newer layers
        (components, color application) are treated as first-class, not glossed under the
        facet moves. check_conformance gates all of these. Each line carries the disposition
        WHY so the agent builds to the principle, not just to pass the check."""
        items = []
        if self.composition:
            items.append(f"COMPOSITION — organize around a {self.composition.archetype} spine."
                         + self._why(self.composition.disposition))
        for s in self.styles:
            line = f"{s.facet.upper()} — carry the moves {sorted(s.required_features)}"
            reserved = sorted(m for m in s.required_features
                              if s.prevalence.get(m) is not None
                              and s.prevalence[m] <= _RESERVED_MAX)
            if reserved:
                freqs = ", ".join(f"'{m}' in ~{s.prevalence[m]:.0%} of source files"
                                  for m in reserved)
                line += (f" · DEPLOYMENT: reserve {reserved} for the focal moments — the source "
                         f"deploys sparingly ({freqs}); a reserved move applied everywhere stops "
                         f"reading as identity")
            if s.facet == "color" and s.application:
                roles: dict = {}
                for b in s.application:
                    roles.setdefault(b["kind"], set()).add(b["role"])
                marks = sorted(k for k, rs in roles.items()
                               if k != "neutral" and not (rs & {"ground", "surface", "decoration"}))
                bt = s.metrics.get("background_tonality")
                extra = []
                if marks:
                    extra.append(f"APPLICATION: keep {marks} color to marking (data/text/"
                                 f"interactive), never flood it onto surfaces")
                if bt is not None:
                    extra.append(f"ground is {'LIGHT' if bt >= 0.6 else 'DARK' if bt <= 0.4 else 'mid'} "
                                 f"(tonality {bt}) — match that polarity")
                if extra:
                    line += " · " + " · ".join(extra)
            items.append(line + "." + self._why(s.disposition))
        for surf in self.surfaces:
            line = (f"SURFACE/{surf.applies_to} — a materially-rich focal object "
                    f"(layers {sorted(surf.required_roles)}).")
            if surf.prevalence is not None and surf.prevalence <= _RESERVED_MAX:
                line += (f" DEPLOYMENT: reserve this material for the focal object — only "
                         f"~{surf.prevalence:.0%} of source components carry it; the same "
                         f"texture on everything reads as wallpaper, not a lit centerpiece.")
            items.append(line + self._why(surf.disposition))
        for r in self.rules:
            items.append(f"BEHAVIOR/{r.applies_to} — an interaction carrying {sorted(r.required_features)}"
                         + (f" at ~{r.exit_ms}ms" if r.exit_ms else "") + "."
                         + self._why(r.disposition))
        for c in self.components:
            items.append(f"COMPONENT/{c.role} — {c.emit()['instantiate']}")
        for s in self.subtractions:
            items.append(f"SUBTRACTION — the product is {s['note']}. Do NOT add it back; this "
                         f"identity is defined by its ABSENCE (adding it is a violation by excess).")
        for op in self.observed_patterns:
            from rubrick.components import pattern_description
            where = f" (seen in {op['component']})" if op.get("component") else ""
            items.append(f"PATTERN/{op['name']} (unverified) — the product carries this "
                         f"interaction pattern: {pattern_description(op['name'])}{where}. "
                         f"Evidence: {op.get('evidence', '')[:160]}. The gate cannot verify this "
                         f"one yet — reproduce it and own it by hand, like the craft in the guide.")
        return items

    def _guide(self) -> dict:
        """Standing build guidance — the levers the GATE cannot enforce, so they must be
        INSTRUCTED. The checklist says WHAT to build and WHY; this says HOW to build it well
        and how to read the gate. Everything here is product-agnostic on purpose: it heads off
        the failure modes we see agents hit (dismissing a real finding as noise, chasing green
        instead of craft, styling before there's a spine)."""
        return {
            "deployment_frequency": (
                "An identity move has a HOME. Carrying a move does NOT mean maximizing it: the "
                "source deploys its strongest moves — textures, glows, loops, display type — at a "
                "specific frequency (the checklist's DEPLOYMENT notes give the observed rate), and "
                "that restraint is itself part of the identity. Applying a reserved move to every "
                "element destroys the figure/ground contrast that makes it read as identity; the "
                "build goes noisy and one-dimensional, and the gate flags clear over-application. "
                "Match the deployment pattern, not just the move."
            ),
            "build_to_the_why": (
                "The checklist's WHY clauses are the product's dispositions — its soul. Build to "
                "those principles, not just to pass the checks. A check is a floor, not the finish: "
                "passing conformance means you didn't violate the grammar, NOT that it feels like "
                "one designer's hand."
            ),
            "build_order": [
                "1. SKELETON — stand up the composition spine and the focal object first "
                "(structure before style). A great skin on no spine reads as generic.",
                "2. MATERIAL — give the focal object its layered material (the SURFACE moves).",
                "3. BEHAVIOR — bind the interaction grammar (gesture → response) on the component roles.",
                "4. STYLE — carry each facet's moves at the stated MAGNITUDE (as loud as the source, "
                "not a tasteful echo).",
                "5. POLISH — the craft below. This is where a passing build becomes a good one.",
            ],
            "you_own_these_the_gate_cannot_check": {
                "note": "Static analysis reads declared DOM/CSS, not the rendered/animated result. "
                        "These are real identity but UNVERIFIABLE — a green report does NOT cover them, "
                        "so they are yours to get right by hand.",
                "motion_smoothness": "Real easing and staged timing — no linear tweens, no jank. "
                                     "Animate transform/opacity, not layout. Honor prefers-reduced-motion.",
                "color_harmony": "The palette must read as ONE system — even lightness/chroma steps, "
                                 "restrained hue families. Passing the color moves ≠ a harmonious palette.",
                "type_layout": "Clean arrangement — aligned to a grid, consistent vertical rhythm, a "
                               "hierarchy that reads. (Rich size vocabularies are fine; sloppy ARRANGEMENT is not.)",
                "material_feel": "Glossy vs flat, focal richness — the rendered richness the layer/alpha "
                                 "counts can't distinguish. Make the focal object look genuinely lit.",
            },
            "reading_the_gate": (
                "The gate is DETERMINISTIC except color, which is semantic (marking-vs-decoration is a "
                "judgment about meaning). Consequences: (a) a FAIL that stays IDENTICAL on UNCHANGED "
                "code is REAL — fix the build, do not re-run hoping it clears, and do not contort code to "
                "game a signature. (b) The color check can shift between edits because it re-reads meaning; "
                "trust a stable verdict on unchanged code. (c) 'accent decorates instead of marks' is about "
                "MEANING: a colored glow on a data entity MARKS (good); a decorative gradient DECORATES (flagged)."
            ),
        }


# ---- persistence: compile once (slow) -> save -> server loads (fast) ------------

def save_product_system(ps: ProductSystem, path: str) -> None:
    pathlib.Path(path).write_text(json.dumps(ps.emit_manifest(), indent=2))


def load_product_system(path: str) -> ProductSystem:
    """Reconstruct a ProductSystem from a saved manifest (enough to run check).
    Calibrated disposition params round-trip through the manifest, so a loaded
    surface/behavior record runs its quantitative checks; an uncalibrated one
    degrades to feature-presence checks (see Disposition.calibrated)."""
    m = json.loads(pathlib.Path(path).read_text())
    disps = {i: Disposition(i, d["prior"], d.get("calibrated", {}))
             for i, d in m["dispositions"].items()}
    styles = [StyleRecord(s["facet"], set(s["identity_moves"]), disps[s["because"]],
                          concrete=s.get("concrete", {}), metrics=s.get("metrics", {}),
                          application=s.get("application", []),
                          prevalence=s.get("prevalence", {}))
              for s in m.get("styles", [])]
    surfaces = [SurfaceRecord(s["applies_to"], set(s["requires"]), disps[s["because"]],
                              prevalence=s.get("prevalence"))
                for s in m.get("surfaces", [])]
    rules = [RuleRecord(r["applies_to"], set(r["requires"]), disps[r["because"]],
                        exit_ms=r.get("exit_ms"), enter_ms=r.get("enter_ms"))
             for r in m.get("rules", [])]
    cm = m.get("composition")
    composition = (CompositionRecord(cm["archetype"], cm.get("focal_anchor"),
                                     cm["composition"], disps[cm["because"]])
                   if cm else None)
    components = [ComponentRecord(c["role"], c["affordance"],
                                  set(c.get("material_roles", [])), set(c.get("treatments", [])),
                                  gesture=c.get("gesture", "none"),
                                  patterns=set(c.get("patterns", [])))
                 for c in m.get("components", [])]
    return ProductSystem(dispositions=disps, surfaces=surfaces, rules=rules, styles=styles,
                         composition=composition, components=components,
                         subtractions=m.get("subtractions", []),
                         observed_patterns=m.get("observed_patterns", []))
