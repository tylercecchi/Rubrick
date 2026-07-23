"""The conformance engine — the value behind the MCP `check_conformance` tool.

Re-observes a candidate (a repo, or an agent's generated output) and measures it
against a product_system, returning objective violations. This is the "verified
gate": not the agent's self-report of whether it honored the identity, but a
ground-truth re-extraction diffed against the system.

Covers all four facet records (typography / color / density / ambient) AND — once
the product system's surface/behavior dispositions are CALIBRATED — the surface
(material) and behavior (interaction) records, whose checks are quantitative
(alpha band, ceremony timing) not just feature-presence.
"""

from __future__ import annotations

import json
import pathlib

from rubrick.ambient_extract import gather_ambient_source
from rubrick.baseline import content_key as _content_key  # canonical per-source cache key
from rubrick.style_facets import extract_facet, gather_facet_source
from rubrick.type_extract import extract_typography, gather_type_source


def _moment_key(ctx) -> str:
    """Canonical moment-inference cache key: bound to the interaction's structural
    context, so a compile and a later check infer the SAME moment for the same
    interaction (and multiple interactions in one component get distinct keys)."""
    return _content_key(json.dumps(ctx.model_dump(), sort_keys=True))


def candidate_type_obs(repo: str, gcss: str, comps: str, key: str):
    """The candidate's typography observation — HYBRID: mechanical moves from code signatures
    (deterministic), faces + detailed-face from the LLM (irreducibly semantic). Shared by
    posture (feature_set) and native (concrete faces)."""
    from rubrick.facet_signatures import hybrid_type_obs
    ts = gather_type_source(repo, gcss, comps)
    return hybrid_type_obs(repo, gcss, comps, ts, _content_key(ts))


def candidate_facets(repo: str, gcss: str, comps: str, key: str) -> dict[str, set[str]]:
    """Re-observe a candidate's facets — the same extraction used to observe products.
    Cache keys are content-bound so a re-check after an edit truly re-observes."""
    from rubrick.facet_signatures import detect_facet_moves, raw_source
    cs = gather_facet_source(repo, gcss, comps, "color")
    rs = raw_source(repo, gcss, comps)  # density + elevation + ambient are DETERMINISTIC (signatures)
    # grounded-only (see grounded_set): novel features are unpromoted/run-variant and
    # would otherwise create phantom conformance diffs between the record and candidate.
    return {
        "typography": candidate_type_obs(repo, gcss, comps, key).grounded_set(),
        "color": extract_facet("color", cs, _content_key(cs)).grounded_set(),
        "density": detect_facet_moves("density", rs),
        "ambient": detect_facet_moves("ambient", rs),
        "elevation": detect_facet_moves("elevation", rs),
    }


# facet -> function mapping a candidate's observation to its concrete (native) shape.
# Only typography today; other facets register here as the aesthetic layer widens.
def _candidate_application(repo: str, gcss: str, comps: str, key: str) -> list:
    """The candidate's own color kind→role bindings. Keyed on content_key(asrc) — the SAME key
    compile uses — so a check of the SAME source reuses the one canonical observation (exact
    self-conformance); a different candidate re-observes under its own content key. This is the
    determinism mechanism used across every modality (caching, not sampling)."""
    from rubrick.baseline import content_key
    from rubrick.style_facets import extract_color_application, gather_color_application
    asrc = gather_color_application(repo, gcss, comps)
    return extract_color_application(asrc, content_key(asrc)).model_dump()["bindings"]


def _candidate_metrics(facet: str, repo: str, gcss: str, comps: str) -> dict:
    """The candidate's own quantitative magnitudes (deterministic regex, no LLM), to
    compare against a record's calibrated `metrics` via StyleRecord.check_metrics."""
    if facet == "typography":
        from rubrick.type_extract import (gather_type_source, max_tracking, max_weight,
                                   scale_contrast_ratio)
        src = gather_type_source(repo, gcss, comps)
        m = {}
        r = scale_contrast_ratio(src)
        if r:
            m["scale_contrast_ratio"] = r
        t = max_tracking(src)
        if t:
            m["micro_tracking_em"] = t
        w = max_weight(src)
        if w:
            m["max_weight"] = w
        return m
    if facet == "color":
        from rubrick.style_facets import (background_tonality, gather_facet_source,
                                  palette_coherence, palette_max_chroma)
        cs = gather_facet_source(repo, gcss, comps, "color")
        m = {}
        c = palette_max_chroma(cs)
        if c:
            m["accent_chroma"] = c
        pc = palette_coherence(cs)
        if pc is not None:
            m["palette_coherence"] = pc
        bt = background_tonality(cs)
        if bt is not None:
            m["background_tonality"] = bt
        return m
    if facet == "density":
        from rubrick.style_facets import (content_density, gather_facet_source, median_spacing,
                                  spacing_discipline)
        ds = gather_facet_source(repo, gcss, comps, "density")
        m = {}
        sp = median_spacing(ds)
        if sp:
            m["density_spacing_px"] = sp
        d = spacing_discipline(ds)
        if d is not None:
            m["spacing_discipline"] = d
        cd = content_density(repo, comps)
        if cd is not None:
            m["content_density"] = cd
        return m
    if facet == "elevation":
        from rubrick.style_facets import gather_facet_source, max_shadow_blur
        b = max_shadow_blur(gather_facet_source(repo, gcss, comps, "elevation"))
        return {"shadow_depth_px": b} if b else {}
    return {}


def _candidate_concrete(facet: str, repo: str, gcss: str, comps: str, key: str) -> dict | None:
    if facet == "typography":
        from rubrick.type_extract import candidate_type_concrete
        from rubrick.facet_signatures import capture_face_roles, raw_source
        cc = candidate_type_concrete(candidate_type_obs(repo, gcss, comps, key))
        cc["face_roles"] = capture_face_roles(raw_source(repo, gcss, comps))  # deterministic role gate
        return cc
    if facet == "color":
        # palette anchors are a deterministic regex over source — no model call
        from rubrick.style_facets import candidate_facet_concrete, gather_facet_source
        return candidate_facet_concrete("color", gather_facet_source(repo, gcss, comps, "color"))
    return None


# ---- surface + behavior re-observation (mirrors the orchestrator's discovery) ----

def _sample_components(repo: str, comps: str, limit: int = 40) -> list[str]:
    d = pathlib.Path(repo) / comps
    return [str(p) for p in sorted(d.rglob("*.tsx"))[:limit]] if d.exists() else []


def _rank_interaction_components(repo: str, comps: str, gcss: str, limit: int = 5) -> list[str]:
    """The top-`limit` components by choreography richness — a DETERMINISTIC regex signal
    (timings, keyframes, multi-phase, pointer-lock), the analog of surface's richest-stack
    finder. Same ranking the orchestrator uses, so compile and check select the SAME
    components. No fuzzy LLM discovery (its variance dropped the true identity interaction)."""
    from rubrick.orchestrate import _gather_component_behavior, _interaction_richness
    css = pathlib.Path(repo) / gcss
    css_text = css.read_text() if css.exists() else ""
    scored = [(_interaction_richness(_gather_component_behavior(c, css_text, repo)), c)
              for c in _sample_components(repo, comps)]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [c for _, c in scored[:limit]]


def candidate_surface(repo: str, comps: str, key: str):
    """Re-observe the candidate's focal material surface (or None if it has none) —
    the component with the richest material stack (see extract_css.find_focal_surface)."""
    from rubrick.extract_css import find_focal_surface
    found = find_focal_surface(repo, comps)
    return found[1] if found else None


def candidate_behaviors(repo: str, gcss: str, comps: str, key: str) -> list:
    """Re-observe the candidate's interactions DETERMINISTICALLY — treatments + timings read
    by code signature (detect_treatments), NO LLM. Returns a flat list of InteractionSpec; a
    rule matches the candidate interaction with the best TREATMENT OVERLAP, so no moment
    inference is needed at check — that per-edit LLM reclassification was the source of the
    behavior flapping (PASS then FAIL on the same code) and the recall misses. Same source →
    same specs → exact self-conformance, and a behavior PASS now means verified."""
    from rubrick.detect_treatments import detect_timings, detect_treatments
    from rubrick.interaction import InteractionSpec, Qualifiers
    from rubrick.orchestrate import _gather_component_behavior

    css = (pathlib.Path(repo) / gcss).read_text() if (pathlib.Path(repo) / gcss).exists() else ""
    q = Qualifiers(frequency="rare", stakes="trivial", reversibility="free-undo",
                   blast="self-local", latency="instant", initiative="user")
    specs = []
    for c in _rank_interaction_components(repo, comps, gcss):
        gathered = _gather_component_behavior(c, css, repo)
        tr = detect_treatments(gathered)
        if not tr:
            continue  # no choreography — not an identity interaction
        tim = detect_timings(gathered)
        specs.append(InteractionSpec(
            moment="", qualifiers=q, treatment_features=tr,
            params={"exit_ms": tim["exit_ms"], "enter_ms": tim["enter_ms"]}))
    return specs


def check_conformance(candidate_repo: str, gcss: str, comps: str, key: str, ps,
                      native: bool = False) -> dict:
    """Return {record: {"conforms": bool, "violations": [...]}} across facet, surface,
    and behavior records. Surface/behavior are re-observed only when the system carries
    such records; a record is skipped (not failed) if the candidate exposes no
    corresponding element.

    POSTURE by default ("does this carry the transferable identity moves?"). With
    native=True, ALSO runs value-conformance ("does this reuse the product's actual
    faces/palette?") for facets that carry concrete aesthetics — the check for a
    SAME-PRODUCT native feature. Native violations appear as `native:<facet>` records."""
    report = {}

    cf = candidate_facets(candidate_repo, gcss, comps, key)
    for sr in ps.styles:
        v = sr.check(cf.get(sr.facet, set()))
        if sr.metrics:  # quantitative magnitude check (depth) folded into the facet
            v = v + sr.check_metrics(_candidate_metrics(sr.facet, candidate_repo, gcss, comps))
        if sr.application:  # HOW color is applied — kind→role binding discipline (threshold-gated)
            v = v + sr.check_application(_candidate_application(candidate_repo, gcss, comps, key))
        report[sr.facet] = {"conforms": not v, "violations": v}

    if native:
        for sr in ps.styles:
            if not sr.concrete.get("anchors"):
                continue  # no concrete captured for this facet — nothing to value-check
            cc = _candidate_concrete(sr.facet, candidate_repo, gcss, comps, key)
            if cc is None:
                report[f"native:{sr.facet}"] = {"conforms": None, "violations": [],
                    "note": "no candidate-concrete extractor for this facet yet"}
            else:
                v = sr.check_native(cc)
                report[f"native:{sr.facet}"] = {"conforms": not v, "violations": v}

    if ps.surfaces:
        cand = candidate_surface(candidate_repo, comps, key)
        for rec in ps.surfaces:
            if cand is None:
                report[f"surface:{rec.applies_to}"] = {"conforms": None,
                    "violations": [], "note": "no comparable surface in candidate"}
            else:
                v = rec.check(cand)
                report[f"surface:{rec.applies_to}"] = {"conforms": not v, "violations": v,
                    "calibrated": rec.disposition.calibrated}

    if ps.rules:
        cand_specs = candidate_behaviors(candidate_repo, gcss, comps, key)
        group = set().union(*(c.features() for c in cand_specs)) if cand_specs else set()
        for rec in ps.rules:
            # treatments checked against the GROUP (the build's interaction vocabulary — a
            # decomposed interaction lives across co-rendered parts); timing from the best-
            # matching component. No overlap anywhere → the interaction is genuinely absent → SKIP.
            best = max(cand_specs, key=lambda c: len(rec.required_features & c.features()),
                       default=None)
            if best is None or not (rec.required_features & group):
                report[f"behavior:{rec.applies_to}"] = {"conforms": None, "violations": [],
                    "note": f"candidate has no comparable {rec.applies_to!r} interaction "
                    f"(no treatment overlap; found treatments: {sorted(group) or 'none'})"}
            else:
                v = rec.check(best, group=group)
                report[f"behavior:{rec.applies_to}"] = {"conforms": not v, "violations": v,
                    "calibrated": rec.disposition.calibrated}

    if ps.composition:  # the structural spine — re-observe the candidate's archetype
        from rubrick.infer_composition import gather_composition_source, infer_composition
        csrc = gather_composition_source(candidate_repo, gcss, comps)
        try:
            cobs = infer_composition(csrc, _content_key(csrc))
            cand = {"archetype": cobs.archetype, "focal_anchor": cobs.focal_anchor,
                    "composition": cobs.composition}
            v = ps.composition.check(cand, native=native)
            report["composition"] = {"conforms": not v, "violations": v}
        except Exception:
            report["composition"] = {"conforms": None, "violations": [],
                                     "note": "could not observe candidate composition"}

    if ps.components:  # identity ROLES: aesthetic × interaction × affordance, bound per component
        from rubrick.components import capture_components
        ccss = (pathlib.Path(candidate_repo) / gcss).read_text() \
            if (pathlib.Path(candidate_repo) / gcss).exists() else ""
        # capture MORE on the candidate side than the system's handful of roles — a build has
        # more identity components, and each role must be able to find its true counterpart
        # (a drag sheet ranked 4th was excluded by the cap, so its role matched a click element).
        cand_comps = capture_components(candidate_repo, comps, ccss, limit=10)
        for rec in ps.components:
            best, overlap = rec.best_match(cand_comps)
            if best is None or overlap == 0:
                report[f"component:{rec.role}"] = {"conforms": None, "violations": [],
                    "note": f"candidate has no comparable {rec.role!r} component "
                    f"(no aesthetic/interaction overlap)"}
            else:
                v = rec.check(best, cand_comps)  # group = the build's identity components
                report[f"component:{rec.role}"] = {"conforms": not v, "violations": v}

    if ps.subtractions:  # negative-space identity — flag VIOLATION BY EXCESS (added what it omits)
        from rubrick.subtractions import check_subtractions
        v = check_subtractions(ps.subtractions, candidate_repo, gcss, comps)
        report["subtractions"] = {"conforms": not v, "violations": v}

    checked = [r for f, r in report.items() if r.get("conforms") is not None]
    report["_summary"] = {
        "records_checked": len(checked),
        "conforming": sum(1 for r in checked if r["conforms"]),
        "skipped": sum(1 for f, r in report.items()
                       if f != "_summary" and r.get("conforms") is None),
    }
    return report


def format_report(report: dict) -> str:
    lines = []
    for name, r in report.items():
        if name == "_summary":
            continue
        if r.get("conforms") is None:
            mark = "SKIP –"
        else:
            mark = "PASS ✓" if r["conforms"] else "FAIL ✗"
        lines.append(f"  {name:<22} {mark}")
        if r.get("note"):
            lines.append(f"        · {r['note']}")
        for v in r["violations"]:
            lines.append(f"        · {v}")
    s = report["_summary"]
    tail = f"  {'':<22} {s['conforming']}/{s['records_checked']} records conform"
    if s.get("skipped"):
        tail += f" ({s['skipped']} skipped)"
    lines.append(tail)
    return "\n".join(lines)
