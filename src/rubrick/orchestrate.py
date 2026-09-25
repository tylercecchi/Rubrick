"""The orchestrator — point at a repo, get a product_system. No hardcoded element
targeting: discovery finds what to observe, so it works on any repo.

  - product-level facets (style + ambient) are already repo-level scans
  - discovery finds which components hold material/behavior worth extracting
  - dispositions are GENERATED from the captured delta (can't be hand-authored)
  - assembly is graceful per-modality: a product with no lit-object surface simply
    gets no Surface record — that's correct identity, not a failure
"""

from __future__ import annotations

import json
import importlib
import pathlib
from rubrick import paths

import anthropic
from pydantic import BaseModel

from rubrick import learned
from rubrick.ambient_extract import _all_keyframes, gather_ambient_source
from rubrick.baseline import _load_key, content_key
from rubrick.extract_behavior import extract_interactions
from rubrick.extract_css import find_focal_surface
from rubrick.interaction_baseline import generate_default as gen_interaction_default
from rubrick.moment_context import MomentContext
from rubrick.product_system import (CompositionRecord, Disposition, ProductSystem, RuleRecord,
                            StyleRecord, SurfaceRecord, calibrate_rule, calibrate_surface)
from rubrick.detect_treatments import detect_timings, detect_treatments
from rubrick.style_facets import (extract_color_application, extract_facet, facet_aesthetic,
                          gather_color_application, gather_facet_source, generate_facet_default)
from rubrick.type_extract import (extract_typography, facet_metrics, gather_type_source,
                          generate_type_default, type_aesthetic)

_DISP_CACHE = paths.cache_dir() / "disposition_cache.json"


class DispositionOut(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    prior: str


def generate_disposition(kind: str, delta: list[str], *, use_cache: bool = True) -> Disposition:
    key = f"{kind}:{','.join(sorted(delta))}"
    cache = json.loads(_DISP_CACHE.read_text()) if _DISP_CACHE.exists() else {}
    if use_cache and key in cache:
        d = cache[key]
        disp = Disposition(d["id"], d["prior"])
    else:
        prompt = (f"A product's captured {kind} identity moves are {sorted(delta)}. State the "
                  f"underlying DISPOSITION — the design prior that generates them — as a short "
                  f"kebab-case id and a one-line prior (the 'why', feature-agnostic).")
        resp = anthropic.Anthropic(api_key=_load_key()).messages.parse(
            model="claude-opus-4-8", max_tokens=600, thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}], output_format=DispositionOut)
        cache[key] = resp.parsed_output.model_dump()
        _DISP_CACHE.write_text(json.dumps(cache, indent=2))
        disp = Disposition(resp.parsed_output.id, resp.parsed_output.prior)
    r = learned.rationale(disp.id)  # a designer-refined 'why' overrides the generated one
    if r:
        disp.prior = r
    return disp


import re

_IMPORT = re.compile(r"""import\s+[^;'"]*?from\s+['"]([^'"]+)['"]""")


def _behavior_rank(spec: str) -> int:
    """Rank an import by how likely it holds INTERACTION logic (lower = more likely).
    A hook or an interaction/animation module outranks a generic lib/util, which
    outranks a plain data/type module — so a bounded gather keeps the behavior, not
    the data (the trial's swap logic was a use* hook; PRESSINGS was just data)."""
    tail = spec.rsplit("/", 1)[-1]
    if re.match(r"use[A-Z]", tail) or re.search(r"interaction|animation|motion|gesture|transition", spec, re.I):
        return 0
    if re.search(r"(?:^|/)hooks?(?:/|$)", spec):
        return 1
    if re.search(r"(?:^|/)(lib|utils?)(?:/|$)", spec):
        return 2
    return 3


def _resolve_local_imports(comp_path: str, repo: str, max_files: int = 4) -> list[tuple[str, str]]:
    """Resolve a component's LOCAL imports (`@/…`, `./…`, `../…`) to source files.

    Behavior is scattered: a component's distinctive interaction is often a hook it
    imports (the trial's swap treatments lived in src/lib/useReciprocalSwap.ts, which
    a component-only scan never saw). We follow local imports — preferring hook/util
    files — so the gathered behavior includes where the interaction actually lives."""
    root, comp = pathlib.Path(repo), pathlib.Path(comp_path)
    src_root = root / "src"
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    specs = _IMPORT.findall(comp.read_text())
    # interaction-bearing imports first — that's where the distinctive behavior lives
    specs.sort(key=_behavior_rank)
    for spec in specs:
        if spec.startswith("@/"):
            base = src_root / spec[2:]
        elif spec.startswith("."):
            base = (comp.parent / spec).resolve()
        else:
            continue  # package import, not local
        for cand in (base.with_suffix(e) for e in (".ts", ".tsx")) if not base.suffix else (base,):
            if cand.exists() and str(cand) not in seen:
                seen.add(str(cand))
                body = "\n".join(cand.read_text().splitlines()[:200])
                out.append((cand.name, body))
                break
        if len(out) >= max_files:
            break
    return out


def _interaction_richness(gathered: str) -> int:
    """Cheap, LLM-free score of how identity-likely an interaction is — choreography
    signals (multi-phase, timed, keyframe-driven, input-locking) PLUS structural
    interaction patterns (a carousel, a drawing surface, a spotlight collection), which
    are strong identity even with no animation at all. Used to spend the (costly)
    extraction budget on the most identity-likely candidates first, instead of whatever
    sorts first alphabetically."""
    s = gathered
    score = 0
    score += len(set(re.findall(r"(\d{2,4})\s*ms", s)))                              # distinct timings
    score += 2 * len(re.findall(r"@keyframes|animation:|-exit|-enter|swap-", s))     # keyframe choreography
    score += 3 * len(re.findall(r"setTimeout|requestAnimationFrame|\bphase\b|\bstage\b|\bstep\b", s, re.I))  # multi-phase
    score += 3 * len(re.findall(r"pointerEvents|setPointerCapture|pointer-events", s))  # interaction-lock
    score += len(re.findall(r"\btransform\b|translate|scale\(|rotate", s))            # spatial motion
    # motion-library choreography — a framer/GSAP/react-spring component IS choreographed
    # even with zero CSS, and must rank into the extraction budget like its CSS twin
    score += 2 * len(re.findall(r"<motion\.|<animated\.|AnimatePresence|\bvariants\s*[=:]|"
                                r"useMotionValue|useSpring|useTransform\(|gsap\.|staggerChildren", s))
    from rubrick.components import detect_patterns
    score += 4 * len(detect_patterns(s))  # a quiet-but-structural pattern must still rank
    return score


def _gather_component_behavior(comp_path: str, css: str, repo: str | None = None) -> str:
    src = "\n".join(pathlib.Path(comp_path).read_text().splitlines()[:220])
    kf = "\n\n".join(_all_keyframes(css))
    parts = [f"// component: {pathlib.Path(comp_path).name}\n{src}"]
    if repo:
        for name, body in _resolve_local_imports(comp_path, repo):
            parts.append(f"// imported by component: {name}\n{body}")
    parts.append(f"/* keyframes */\n{kf}")
    return "\n\n".join(parts)


def compile_product_system(repo: str, gcss: str, comps: str,
                           sample_components: list[str], product_key: str) -> ProductSystem:
    dispositions: dict[str, Disposition] = {}
    styles: list[StyleRecord] = []
    surfaces: list[SurfaceRecord] = []
    rules: list[RuleRecord] = []
    log: list[str] = []
    pending: list[dict] = []   # novel moves awaiting designer promotion (the human loop)
    intent_items: list[dict] = []  # captured/thin moves for designer CAPTURE/DISCARD confirm
    moment_items: list[dict] = []  # inferred moments for designer confirm/correct

    # Self-discover source files when the caller doesn't supply them — through the SHARED
    # discovery list (components dir + src/app + src/lib + …, complete and uncapped), the
    # same list conform observes, so components/pages living outside the components dir
    # are seen and a recompile after new work is added can't silently miss it.
    from rubrick.discover import discover_components, source_dirs
    if not sample_components:
        sample_components = discover_components(repo, comps)
        dirs = [str(pathlib.Path(d).relative_to(repo)) for d in source_dirs(repo, comps)]
        log.append(f"coverage: {len(sample_components)} .tsx files across {dirs}")

    def add_disp(d: Disposition) -> Disposition:
        dispositions[d.id] = d
        return d

    # --- product-level facets: typography + color + density + ambient ---
    # Each spec captures (source, observation) so we build BOTH the posture delta AND
    # the concrete aesthetics (native mode) — retain what's observed.
    # Facet extractions are keyed by CONTENT (content_key), not product name, so a
    # compile and a later conformance check of the SAME source share ONE canonical
    # observation — that is what makes self-conformance exact despite unsampleable
    # (no-temperature) extraction. Changed source still re-extracts.
    facet_specs = [
        ("typography",
         lambda: gather_type_source(repo, gcss, comps),
         lambda src: importlib.import_module("rubrick.facet_signatures").hybrid_type_obs(repo, gcss, comps, src, content_key(src)),
         lambda: generate_type_default().feature_set(),
         # concrete = LLM aesthetic (faces/moves) + DETERMINISTIC face_roles for the native
         # value->role gate (read from raw source, not the summarized gather).
         lambda obs, src: {**type_aesthetic(obs),
                           "face_roles": importlib.import_module("rubrick.facet_signatures").capture_face_roles(
                               importlib.import_module("rubrick.facet_signatures").raw_source(repo, gcss, comps))}),
        ("color",
         lambda: gather_facet_source(repo, gcss, comps, "color"),
         lambda src: extract_facet("color", src, content_key(src)),
         lambda: generate_facet_default("color").feature_set(),
         lambda obs, src: facet_aesthetic("color", obs, src)),
        ("density",
         lambda: gather_facet_source(repo, gcss, comps, "density"),
         lambda src: extract_facet("density", src, content_key(src)),
         lambda: generate_facet_default("density").feature_set(),
         lambda obs, src: facet_aesthetic("density", obs, src)),
        ("ambient",
         lambda: gather_ambient_source(repo, gcss, comps),
         lambda src: extract_facet("ambient", src, content_key(src)),
         lambda: generate_facet_default("ambient").feature_set(),
         lambda obs, src: facet_aesthetic("ambient", obs, src)),
        ("elevation",
         lambda: gather_facet_source(repo, gcss, comps, "elevation"),
         lambda src: extract_facet("elevation", src, content_key(src)),
         lambda: generate_facet_default("elevation").feature_set(),
         lambda obs, src: facet_aesthetic("elevation", obs, src)),
    ]
    from rubrick.facet_signatures import (DETERMINISTIC_FACETS, raw_source,
                                          scoped_move_prevalence, signature_facet_obs)
    # deployment frequency of the scoped moves — measured once, per-file, deterministically;
    # attached to each style record so the manifest can say HOW OFTEN a move is deployed
    # (reserve-it-for-the-focal-moments) and conform can gate clear over-application.
    try:
        prevalence_map = scoped_move_prevalence(repo, gcss, comps)
        log.append("prevalence: measured " + str({f: len(m) for f, m in prevalence_map.items()}))
    except Exception as e:  # never silent — an empty map disables the deployment channel
        prevalence_map = {}
        log.append(f"prevalence: SKIPPED ({type(e).__name__}: {e}) — deployment channel inactive this compile")
    for facet, gather_fn, extract_fn, def_fn, concrete_fn in facet_specs:
        try:
            src = gather_fn()
            # density + elevation are DETERMINISTIC (code signatures on the raw source) — no LLM,
            # no flapping. The rest keep the LLM (they carry genuinely-semantic moves).
            obs = (signature_facet_obs(facet, raw_source(repo, gcss, comps))
                   if facet in DETERMINISTIC_FACETS else extract_fn(src))
            # REQUIRED delta = grounded vocab only. novel_features are unpromoted,
            # invented fresh each run — including them made self-conformance flap.
            orig_delta = obs.grounded_set() - def_fn()
            # intent-confirmation: designer can DISCARD a captured move or CAPTURE (rescue) a thin one
            delta = {f for f in orig_delta if learned.intent_decision(f"{facet}:{f}") != "DISCARD"}
            rescued = {f for f in obs.grounded_set()
                       if learned.intent_decision(f"{facet}:{f}") == "CAPTURE"}
            delta |= rescued
            novel = obs.feature_set() - obs.grounded_set()
            for nf in getattr(obs, "novel_features", []):
                if nf.name not in learned.discarded(facet):
                    pending.append({"name": nf.name, "modality": facet, "evidence": nf.evidence})
            mets = facet_metrics(facet, delta, src)
            if facet == "density":  # MAGNITUDE: felt density (content per component), not just spacing
                from rubrick.style_facets import content_density
                cd = content_density(repo, comps)
                if cd is not None:
                    mets = {**mets, "content_density": cd}
            # DISCIPLINE axis: a facet is identity-bearing if DIFFERENTIATED (delta) OR
            # DISCIPLINED (rigorous systematicity) — restraint earns identity at low delta.
            disciplined = (mets.get("spacing_discipline", 0) >= 0.85
                           or mets.get("palette_coherence", 0) >= 0.85)
            recorded = len(delta) >= 2 or bool(rescued) or disciplined
            for f in sorted(orig_delta | rescued):
                intent_items.append({"subject": f"{facet}:{f}", "captured": recorded and f in delta})
            if recorded and (delta or disciplined):
                application = []
                if facet == "color":  # HOW color is applied (kind→role bindings), not just which
                    asrc = gather_color_application(repo, gcss, comps)
                    application = extract_color_application(asrc, content_key(asrc)).model_dump()["bindings"]
                fprev = {mv: p for mv, p in prevalence_map.get(facet, {}).items() if mv in delta}
                styles.append(StyleRecord(facet, delta,
                                          add_disp(generate_disposition(facet, sorted(delta) or [facet])),
                                          concrete=concrete_fn(obs, src), metrics=mets,
                                          application=application, prevalence=fprev))
                log.append(f"style/{facet}: CAPTURE {sorted(delta)}"
                           + (f" · disciplined({mets['spacing_discipline']})" if disciplined and not delta else "")
                           + (f" · pending-promotion {sorted(novel)}" if novel else ""))
            else:
                log.append(f"style/{facet}: thin ({sorted(delta)}) — no record")
        except Exception as e:  # graceful per-modality
            log.append(f"style/{facet}: skipped ({type(e).__name__})")

    # --- surface: deterministic (richest material stack), NOT fuzzy discovery ---
    css = (pathlib.Path(repo) / gcss).read_text() if (pathlib.Path(repo) / gcss).exists() else ""
    found = find_focal_surface(repo, comps)
    if found:
        surface_comp_name, mat = pathlib.Path(found[0]).stem, found[1]
        roles = mat.material_roles()
        disp = calibrate_surface(generate_disposition("material surface", sorted(roles)), mat)
        from rubrick.extract_css import material_prevalence
        sprev = material_prevalence(repo, comps)  # how RESERVED the rich material is
        surfaces.append(SurfaceRecord("focal-entity", roles, add_disp(disp), prevalence=sprev))
        log.append(f"material: CAPTURE {sorted(roles)} from {surface_comp_name}"
                   + (f" · calibrated α≤{disp.params['overlay_alpha_ceiling']}"
                      if disp.calibrated else " · uncalibrated (no neutral overlays)")
                   + (f" · reserved ({sprev:.0%} of files)" if sprev is not None else ""))
    else:
        log.append("material: no lit-object surface — no record (correct if the product is flat)")

    # --- behavior: DETERMINISTIC selection, the analog of surface's richest-material-stack
    #     finder. Rank EVERY component by choreography richness (a cheap regex — timings,
    #     keyframes, multi-phase, pointer-lock) and extract the top few. NO fuzzy LLM
    #     discovery pre-filter: that step's run-to-run variance could drop the true identity
    #     interaction (a product's swap) before it was ever ranked. Regex ranking is stable, so
    #     the choreographed identity interaction reliably makes the cut; generic-but-busy
    #     components are filtered downstream by the delta>=2 identity threshold. ---
    from rubrick.infer_moment import infer_moment
    scored = []
    for cpath in sample_components:
        gathered = _gather_component_behavior(cpath, css, repo)
        scored.append((_interaction_richness(gathered), cpath, gathered))
    scored.sort(key=lambda t: t[0], reverse=True)
    if scored:
        log.append("behavior: richness ranking " + ", ".join(
            f"{pathlib.Path(c).stem}={s}" for s, c, _ in scored[:6]))

    # Each candidate component may hold SEVERAL distinct interactions — enumerate them
    # (extract_interactions) and key each by moment, keeping the highest-delta per moment
    # across all components. A product's identity can be MULTIPLE interactions (a swap AND
    # a reactive hover), so we capture the top distinct moments, not just one.
    by_moment: dict[str, tuple] = {}  # moment -> (delta_size, stem, eb, im, delta)
    for _, cpath, gathered in scored[:5]:  # top-K richest; extraction is an LLM call each
        stem = pathlib.Path(cpath).stem
        try:
            ckey = content_key(gathered)  # canonical per-source — shared with the check path
            interactions = extract_interactions(gathered, ckey)
        except Exception as e:
            log.append(f"behavior: candidate {stem} skipped ({type(e).__name__})")
            continue
        for eb in interactions:
            ctx = MomentContext(trigger=eb.trigger, view_effect=eb.view_effect,
                                persistent_effect=eb.persistent_effect, affects=eb.affects,
                                frequency_cue=eb.frequency_cue, reversibility_cue=eb.reversibility_cue)
            im = infer_moment(content_key(json.dumps(ctx.model_dump(), sort_keys=True)), ctx)
            im.moment = learned.moment_correction(stem, im.moment) or im.moment  # designer fix
            # TREATMENTS are DETERMINISTIC (detect_treatments), so the rule's required features
            # and the candidate's re-observation come from the SAME code signatures — no LLM
            # resampling, no recall misses. The LLM is used only for the semantic moment LABEL.
            delta = detect_treatments(gathered) - gen_interaction_default(im.moment, im.qualifiers).features()
            log.append(f"behavior: {stem} → {im.moment}, delta {sorted(delta)}")
            if len(delta) >= 2 and (im.moment not in by_moment or len(delta) > by_moment[im.moment][0]):
                by_moment[im.moment] = (len(delta), stem, eb, im, delta, gathered)

    # capture the top distinct identity interactions (most identity-bearing moments)
    for _, stem, eb, im, delta, gathered in sorted(by_moment.values(), key=lambda x: -x[0])[:3]:
        for nt in eb.novel_treatments:
            if nt.name not in learned.discarded("treatment"):
                pending.append({"name": nt.name, "modality": "behavior:treatment",
                                "evidence": nt.evidence})
        moment_items.append({"interaction": stem, "moment": im.moment,
                             "confidence": round(im.confidence, 2), "correct_to": ""})
        tim = detect_timings(gathered)  # deterministic choreography timing
        disp = calibrate_rule(generate_disposition("interaction", sorted(delta)),
                              tim["exit_ms"], tim["enter_ms"], eb.disorientation)
        rules.append(RuleRecord(im.moment, delta, add_disp(disp),
                                exit_ms=tim["exit_ms"], enter_ms=tim["enter_ms"]))
        log.append(f"behavior: CAPTURE {im.moment} from {stem} {sorted(delta)}"
                   + (f" · exit {tim['exit_ms']}ms" if tim["exit_ms"] else " · no timing"))
    if not by_moment:
        log.append("behavior: no identity-bearing interaction — no record")

    # --- composition: the structural SPINE (a modality, upstream of behavior) ---
    composition = None
    try:
        from rubrick.infer_composition import (gather_composition_source, infer_composition,
                                        is_generic)
        csrc = gather_composition_source(repo, gcss, comps)
        cobs = infer_composition(csrc, content_key(csrc))
        if is_generic(cobs.archetype, cobs.focal_anchor):
            log.append(f"composition: generic ({cobs.archetype}) — no distinctive spine, no record")
        else:
            delta = [cobs.archetype, cobs.composition] + ([cobs.focal_anchor] if cobs.focal_anchor else [])
            cdisp = add_disp(generate_disposition("composition", delta))
            composition = CompositionRecord(cobs.archetype, cobs.focal_anchor,
                                            cobs.composition, cdisp)
            log.append(f"composition: CAPTURE {cobs.archetype} · anchor={cobs.focal_anchor} "
                       f"· {cobs.composition}")
    except Exception as e:
        log.append(f"composition: skipped ({type(e).__name__})")

    # --- components: the identity-bearing ROLES where aesthetic × interaction meet ---
    components = []
    try:
        from rubrick.components import capture_components
        from rubrick.product_system import ComponentRecord
        for sig in capture_components(repo, comps, css):
            components.append(ComponentRecord(sig["role"], sig["affordance"],
                                              sig["material_roles"], sig["treatments"],
                                              gesture=sig.get("gesture", "none"),
                                              patterns=sig.get("patterns", set())))
            log.append(f"component: CAPTURE {sig['role']} · {sig['gesture']}→{sig['affordance']} · "
                       f"material={sorted(sig['material_roles'])} interaction={sorted(sig['treatments'])}"
                       + (f" · patterns={sorted(sig['patterns'])}" if sig.get("patterns") else ""))
    except Exception as e:
        log.append(f"components: skipped ({type(e).__name__})")

    # --- subtractions: deliberate OMISSIONS (negative-space identity) ---
    subtractions = []
    try:
        from rubrick.subtractions import detect_subtractions
        nrec = len(styles) + len(surfaces) + len(rules) + (1 if composition else 0) + len(components)
        subtractions = detect_subtractions(repo, gcss, comps, designed=nrec >= 2)
        for s in subtractions:
            log.append(f"subtraction: OMITS {s['omits']} — {s['note']}")
    except Exception as e:
        log.append(f"subtractions: skipped ({type(e).__name__})")

    # --- OPEN OBSERVATION: novelty surveys — seeing is never bounded by what gates. ---
    # One model call each (content-cached). Novel sightings become tears (-> review ->
    # promotion -> a model-proposed, mechanically-admitted detector may then gate them);
    # promoted-but-not-yet-gated patterns seen here are INSTRUCTED via the checklist.
    observed_patterns: list[dict] = []
    try:
        from rubrick.novelty import survey_novel_patterns
        psurv = survey_novel_patterns(repo, gcss, comps)
        for s in psurv.novel:
            if s.name not in learned.discarded("pattern"):
                pending.append({"name": s.name, "modality": "pattern",
                                "evidence": s.evidence, "component": s.component})
        observed_patterns = [{"name": s.name, "component": s.component, "evidence": s.evidence}
                             for s in psurv.unverified_seen]
        log.append(f"patterns survey: novel {sorted(s.name for s in psurv.novel)}"
                   + (f" · unverified-seen {sorted(o['name'] for o in observed_patterns)}"
                      if observed_patterns else ""))
    except Exception as e:
        log.append(f"patterns survey: SKIPPED ({type(e).__name__}: {e})")
    try:
        from rubrick.novelty import survey_novel_facet_moves
        fsurv = survey_novel_facet_moves(repo, gcss, comps)
        for s in fsurv.novel:
            if s.facet in ("density", "elevation", "ambient") \
                    and s.name not in learned.discarded(s.facet):
                pending.append({"name": s.name, "modality": s.facet, "evidence": s.evidence})
        log.append(f"facet novelty survey: {sorted(f'{s.facet}/{s.name}' for s in fsurv.novel) or 'none'}")
    except Exception as e:
        log.append(f"facet novelty survey: SKIPPED ({type(e).__name__}: {e})")

    # --- capabilities: the runtime classes the identity rides on (deterministic) ---
    capabilities: list[dict] = []
    try:
        from rubrick.capabilities import detect_capabilities
        capabilities = detect_capabilities(repo, comps)
        for c in capabilities:
            log.append(f"capability: {c['class']} via {c['libraries']} ({c['evidence']})")
    except Exception as e:
        log.append(f"capabilities: SKIPPED ({type(e).__name__}: {e})")

    ps = ProductSystem(dispositions=dispositions, surfaces=surfaces, rules=rules,
                       styles=styles, composition=composition, components=components,
                       subtractions=subtractions, observed_patterns=observed_patterns,
                       capabilities=capabilities)
    ps._log = log  # type: ignore[attr-defined]
    # dedup pending by (name, modality), preserving first evidence
    seen, deduped = set(), []
    for p in pending:
        k = (p["name"], p["modality"])
        if k not in seen:
            seen.add(k)
            deduped.append(p)
    ps._pending = deduped  # type: ignore[attr-defined]
    ps._intent = intent_items  # type: ignore[attr-defined]
    ps._moments = moment_items  # type: ignore[attr-defined]
    return ps
