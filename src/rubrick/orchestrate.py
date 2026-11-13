"""The orchestrator — point at a repo, get a product_system. No hardcoded element
targeting: discovery finds what to observe, so it works on any repo.

  - product-level facets (style + ambient) are already repo-level scans
  - discovery finds which components hold material/behavior worth extracting
  - dispositions are GENERATED from the captured delta (can't be hand-authored)
  - assembly is graceful per-modality: a product with no lit-object surface simply
    gets no Surface record — that's correct identity, not a failure
"""

from __future__ import annotations

import re

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
    title: str = ""


_MATERIAL_ROLES = {
    "base": "the fill color", "sheen": "a directional gloss gradient",
    "lighting": "radial highlights/shadows simulating light on the surface",
    "texture": "a repeating micro-pattern", "bevel": "a lit edge", "shadow": "a drop shadow",
}

# words that attribute a BUSINESS motive to a design choice. A principle is the product's
# intent as builders read it; one that invents a retention/engagement motive tells an agent
# to build manipulation. Flagged for the designer unless the product's own jobs say so.
_MOTIVE = re.compile(r"\b(retention|retain(?:ing)?|engagement|conversion|convert(?:ing)?|churn|upsell|"
                     r"monetiz\w*|cost of (?:exit|leaving)|disengag\w*|lock[- ]in|stickiness|"
                     r"keep (?:users|them) (?:from|in)|dark pattern|addict\w*|habit[- ]forming)\b", re.I)


def motive_flag(prior: str, jobs: list[str] | None = None) -> str | None:
    """A reason to check this principle, or None. Deterministic."""
    m = _MOTIVE.search(prior or "")
    if not m:
        return None
    if jobs and any(m.group(0).lower() in j.lower() for j in jobs):
        return None  # the product's own jobs name this motive — it's the product's, not invented
    return (f"attributes a business motive (“{m.group(0)}”) the product never states — "
            f"builders follow principles as intent, so confirm or reword it")


def _move_descriptions(kind: str, moves: list[str]) -> dict:
    """What each captured move MEANS, in plain words — so the generator reads intent from
    meaning, not from a bare (and sometimes loaded) vocabulary name."""
    from rubrick.interaction import TREATMENT_DESCRIPTIONS
    from rubrick.style_facets import FACETS
    from rubrick.type_extract import TYPE_FEATURE_DESCRIPTIONS
    table = dict(TREATMENT_DESCRIPTIONS) | dict(TYPE_FEATURE_DESCRIPTIONS) | _MATERIAL_ROLES
    for f in FACETS.values():
        table |= dict(f.get("vocab", {}))
    for facet in ("typography", "color", "density", "ambient", "elevation"):
        table |= learned.promoted_facets(facet)
    table |= learned.promoted_treatments()
    return {m: table.get(m, "") for m in moves}


def similar_moves(a: set, b: set, threshold: float = 0.6) -> bool:
    """Two move sets describe the same behavior (Jaccard >= threshold) — they share one
    principle instead of getting near-duplicate ones."""
    return bool(a or b) and len(a & b) / len(a | b) >= threshold


_DISP_PROMPT = """You are stating the design PRINCIPLE behind one area of a product's identity.

PRODUCT: {product}
WHAT PEOPLE USE IT FOR:
{jobs}
WHERE THIS APPLIES: {where}
THE CAPTURED MOVES, and what each one means:
{moves}

State the underlying disposition — the design intent that generates these moves — as a
short kebab-case id, a one-line prior (the "why", feature-agnostic), and a short plain title
of 2–6 words a designer would recognize (e.g. "Type that commands attention").
- Write it from the experience the product creates for the person using it, in terms of
  this product's purpose.
- Do NOT attribute business motives (retention, engagement, conversion, making it costly
  to leave) unless the product's own uses above state them.
- Some move names describe mechanics that sound negative out of context — read each one
  through its meaning above (e.g. a deliberate pause is ceremony, not obstruction)."""


def generate_disposition(kind: str, delta: list[str], *, context: dict | None = None,
                         product_key: str = "", use_cache: bool = True) -> Disposition:
    """The 'why' behind a set of captured moves. With `context` (the product's kind and
    jobs, and where the moves apply) the principle is product-specific and cached per
    product; without it (no key / no jobs) it falls back to the bare move list. A
    designer's rewording (learned.rationale, scoped to `product_key`) always wins."""
    moves = sorted(delta)
    if context:
        ctx = {"product": context.get("product", ""), "jobs": list(context.get("jobs", [])),
               "where": context.get("where", kind)}
        desc = _move_descriptions(kind, moves)
        prompt = _DISP_PROMPT.format(
            product=ctx["product"] or "a web product",
            jobs="\n".join(f"- {j}" for j in ctx["jobs"]) or "- (unknown)",
            where=ctx["where"],
            moves="\n".join(f"- {m}: {desc[m]}" if desc[m] else f"- {m}" for m in moves))
        key = f"{kind}:{','.join(moves)}:{content_key(prompt)}"
    else:
        prompt = (f"A product's captured {kind} identity moves are {moves}. State the "
                  f"underlying DISPOSITION — the design prior that generates them — as a short "
                  f"kebab-case id, a one-line prior (the 'why', feature-agnostic), and a short "
                  f"plain title of 2-6 words.")
        key = f"{kind}:{','.join(moves)}"
    cache = json.loads(_DISP_CACHE.read_text()) if _DISP_CACHE.exists() else {}
    if use_cache and key in cache:
        d = cache[key]
        disp = Disposition(d["id"], d["prior"], title=d.get("title", ""))
    else:
        resp = anthropic.Anthropic(api_key=_load_key()).messages.parse(
            model="claude-opus-4-8", max_tokens=1200, thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}], output_format=DispositionOut)
        cache[key] = resp.parsed_output.model_dump()
        _DISP_CACHE.write_text(json.dumps(cache, indent=2))
        disp = Disposition(resp.parsed_output.id, resp.parsed_output.prior,
                           title=resp.parsed_output.title)
    r = learned.rationale(disp.id, product=product_key)  # the designer's wording wins
    if r:
        disp.prior = r
    t = learned.title(disp.id, product_key) if product_key else None
    if t:
        disp.title = t
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

    # what the product is FOR — extracted once (sticky across compiles), shared by every
    # principle (so the "why" is about THIS product) and by the generic-twin baseline
    jobs0 = None
    try:
        from rubrick.absences import extract_jobs
        jobs0 = extract_jobs(repo, gcss, comps)
    except Exception as e:
        log.append(f"jobs: SKIPPED ({type(e).__name__}) — principles generated without product context")
    pctx = {"product": jobs0.product_kind, "jobs": jobs0.jobs} if jobs0 and jobs0.jobs else None

    # every switchable item in this product's system, active or not (the UI renders this;
    # the records below hold only ACTIVE items, so checks read only what's active)
    from rubrick.absences import _cat
    catalog: list[dict] = []

    def sw(key: str) -> str | None:
        return learned.switch(product_key, key)

    def why(kind: str, moves, where: str) -> Disposition:
        return generate_disposition(kind, sorted(moves), product_key=product_key,
                                    context={**pctx, "where": where} if pctx else None)

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
            # the product's switches: OFF drops a captured move; ON rescues a thin one
            delta = {f for f in orig_delta if sw(f"{facet}:{f}") != "off"}
            rescued = {f for f in obs.grounded_set() if sw(f"{facet}:{f}") == "on"}
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
            recorded_by_default = len(orig_delta) >= 2 or disciplined
            for f in sorted(orig_delta | rescued):
                default = "on" if (f in orig_delta and recorded_by_default) else "off"
                catalog.append(_cat(f"{facet}:{f}", "add", default, product_key, label=f, area=facet))
            if recorded and (delta or disciplined):
                application = []
                if facet == "color":  # HOW color is applied (kind→role bindings), not just which
                    asrc = gather_color_application(repo, gcss, comps)
                    application = extract_color_application(asrc, content_key(asrc)).model_dump()["bindings"]
                fprev = {mv: p for mv, p in prevalence_map.get(facet, {}).items() if mv in delta}
                styles.append(StyleRecord(facet, delta,
                                          add_disp(why(facet, sorted(delta) or [facet], f"the product's {facet}")),
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
        disp = calibrate_surface(why("material surface", roles,
                                     "the material of the product's focal object"), mat)
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
            im.moment = learned.moment_correction(stem, im.moment, product=product_key) or im.moment  # designer fix
            # TREATMENTS are DETERMINISTIC (detect_treatments), so the rule's required features
            # and the candidate's re-observation come from the SAME code signatures — no LLM
            # resampling, no recall misses. The LLM is used only for the semantic moment LABEL.
            delta = detect_treatments(gathered) - gen_interaction_default(im.moment, im.qualifiers).features()
            log.append(f"behavior: {stem} → {im.moment}, delta {sorted(delta)}")
            if len(delta) >= 2 and (im.moment not in by_moment or len(delta) > by_moment[im.moment][0]):
                by_moment[im.moment] = (len(delta), stem, eb, im, delta, gathered)

    # capture the top distinct identity interactions (most identity-bearing moments).
    # Interactions with mostly the same moves describe ONE behavior: they share one
    # principle, generated once with every moment it covers (no near-duplicate "whys").
    top = sorted(by_moment.values(), key=lambda x: -x[0])[:3]
    groups: list[list] = []
    for row in top:
        g = next((g for g in groups if similar_moves(set(row[4]), set(g[0][4]))), None)
        (g.append(row) if g else groups.append([row]))
    from rubrick.moment_vocab import MOMENT_VOCAB
    group_disp = {}
    for g in groups:
        moves = set().union(*(set(r[4]) for r in g))
        where = "the " + ", ".join(f"'{r[3].moment}' ({MOMENT_VOCAB.get(r[3].moment, r[3].moment)})"
                                   for r in g) + " interaction" + ("s" if len(g) > 1 else "")
        d = why("interaction", moves, where)
        for r in g:
            group_disp[r[3].moment] = d
        if len(g) > 1:
            log.append(f"behavior: {[r[3].moment for r in g]} share one principle ({d.id})")
    for _, stem, eb, im, delta, gathered in top:
        for nt in eb.novel_treatments:
            if nt.name not in learned.discarded("treatment"):
                pending.append({"name": nt.name, "modality": "behavior:treatment",
                                "evidence": nt.evidence})
        moment_items.append({"interaction": stem, "moment": im.moment,
                             "confidence": round(im.confidence, 2), "correct_to": ""})
        tim = detect_timings(gathered)  # deterministic choreography timing
        shared = group_disp[im.moment]
        disp = calibrate_rule(Disposition(shared.id, shared.prior, title=shared.title),
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
            cdisp = add_disp(why("composition", delta, "the product's overall layout"))
            composition = CompositionRecord(cobs.archetype, cobs.focal_anchor,
                                            cobs.composition, cdisp)
            log.append(f"composition: CAPTURE {cobs.archetype} · anchor={cobs.focal_anchor} "
                       f"· {cobs.composition}")
    except Exception as e:
        log.append(f"composition: skipped ({type(e).__name__})")

    # --- components: the identity-bearing ROLES where aesthetic × interaction meet ---
    components = []
    baseline: dict = {"jobs": None, "twins": [], "log": []}
    try:
        from rubrick.components import capture_components
        from rubrick.product_system import ComponentRecord
        sigs = capture_components(repo, comps, css, limit=10)
        # the generic baseline (jobs -> twins) — built once, only for DESIGNED products,
        # shared by the gesture twin-check here and the subtractive channel below
        nrec0 = len(styles) + len(surfaces) + len(rules) + (1 if composition else 0) + min(len(sigs), 3)
        if nrec0 >= 2:
            from rubrick.absences import build_baseline, check_component_gestures
            baseline = build_baseline(repo, gcss, comps, jobs=jobs0)
            log += baseline["log"]
            gt = check_component_gestures(repo, sigs, baseline, comps, gcss, product=product_key)
            catalog.extend(gt["catalog"])
            log += gt["log"]
            sigs = gt["kept"]
            for r in gt["review"]:
                intent_items.append({"subject": f"component:{r['role']}", "captured": False,
                                     "why": f"{r['role']}'s identity is a {r['gesture']} gesture"
                                            + (f"/{sorted(r['patterns'])}" if r.get("patterns") else "")
                                            + f" the generic build also uses for the same purpose "
                                              f"({r['_votes']}) — 'capture' if it's still yours"})
        for sig in sigs[:3]:
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
    # ONE channel for every omission (rubrick.absences + rubrick.subtractions): each
    # registered absence detector (built-in or learned) is captured only when the product
    # zeroes it AND the generated generic twin has it; zeroed-but-the-twin-lacks-it goes to
    # the designer (confirm_intent; not captured unless confirmed). Open survey -> tears.
    subtractions: list[dict] = []
    observed_absences: list[dict] = []
    nrec = len(styles) + len(surfaces) + len(rules) + (1 if composition else 0) + len(components)
    try:
        from rubrick.absences import observe_absences
        ab = observe_absences(repo, gcss, comps, designed=nrec >= 2, product=product_key,
                              baseline=baseline if baseline["twins"] else None)
        subtractions = ab["subtractions"]
        catalog.extend(ab["catalog"])
        pending += ab["pending"]
        observed_absences = ab["observed"]
        log += ab["log"]
        for r in ab["subtractions"]:
            intent_items.append({"subject": f"absence:{r['omits']}", "captured": True,
                                 "why": f"omits {r['omits']} — {r['baseline']}"})
        for r in ab["uncertain"]:
            intent_items.append({"subject": f"absence:{r['omits']}", "captured": False,
                                 "why": f"product omits {r['omits']}, but {r['baseline']} — "
                                        f"a refusal or just never needed? 'capture' to keep it"})
    except Exception as e:
        log.append(f"absence channel: SKIPPED ({type(e).__name__}: {e})")

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

    # the product's switches over the structural records: OFF drops the requirement
    for sr in surfaces:
        catalog.append(_cat(f"surface:{sr.applies_to}", "add", "on", product_key, label=sr.applies_to))
    surfaces = [sr for sr in surfaces if sw(f"surface:{sr.applies_to}") != "off"]
    for r in rules:
        catalog.append(_cat(f"rule:{r.applies_to}", "add", "on", product_key, label=r.applies_to))
    rules = [r for r in rules if sw(f"rule:{r.applies_to}") != "off"]
    if composition is not None:
        catalog.append(_cat("composition", "add", "on", product_key, label=composition.archetype))
        if sw("composition") == "off":
            composition = None
    # MEMBERSHIP: each catalog item names the principle it belongs to. Moves follow their
    # facet's principle; the lit object, interactions and layout follow their own; parts
    # follow the layout (else the interaction) principle; new finds follow their facet, or
    # the interaction principle for patterns/treatments. Omissions have no principle.
    by_facet = {st.facet: st.disposition.id for st in styles}
    first_rule = rules[0].disposition.id if rules else None
    comp_id = composition.disposition.id if composition is not None else None
    def member(key: str) -> str | None:
        head, _, rest = key.partition(":")
        if head in by_facet:
            return by_facet[head]
        if head == "surface":
            return next((sr.disposition.id for sr in surfaces if sr.applies_to == rest), None)
        if head == "rule":
            return next((r.disposition.id for r in rules if r.applies_to == rest), None)
        if key == "composition":
            return comp_id
        if head == "component":
            return comp_id or first_rule
        if head == "new":
            mod = rest.split(":", 1)[0]
            return by_facet.get(mod) or (first_rule if mod in ("pattern", "behavior") else None)
        return None
    for c in catalog:
        c["principle"] = member(c["key"])
    # a principle no active record cites is not shown to builders
    cited = {x.disposition.id for x in [*styles, *surfaces, *rules]} | (
        {composition.disposition.id} if composition else set())
    principles = [{"id": d.id, "title": d.title, "prior": d.prior, "active": d.id in cited}
                  for d in dispositions.values()]
    dispositions = {k: v for k, v in dispositions.items() if k in cited}

    ps = ProductSystem(dispositions=dispositions, surfaces=surfaces, rules=rules,
                       styles=styles, composition=composition, components=components,
                       subtractions=subtractions, observed_patterns=observed_patterns,
                       capabilities=capabilities, observed_absences=observed_absences,
                       catalog=catalog, principles=principles)
    ps._log = log  # type: ignore[attr-defined]
    # dedup pending by (name, modality), preserving first evidence
    seen, deduped = set(), []
    for p in pending:
        k = (p["name"], p["modality"])
        if k in seen:
            continue
        seen.add(k)
        # a new find is INACTIVE until promoted; one the designer kept inactive for THIS
        # product stays in the catalog but leaves the review (per product, not global)
        c = _cat(f"new:{p['modality']}:{p['name']}", "omit" if p["modality"] == "absence" else "add",
                 "off", product_key, label=p["name"], new=True)
        # the find describes itself in the system, not only in the review file
        for f in ("evidence", "instead", "against", "host", "confidence", "component"):
            if p.get(f):
                c[f] = p[f]
        c["principle"] = member(c["key"])
        ps.catalog.append(c)
        if not (c["set_by"] == "you" and c["state"] == "off"):
            deduped.append(p)
    ps._pending = deduped  # type: ignore[attr-defined]
    ps._intent = intent_items  # type: ignore[attr-defined]
    ps._jobs = baseline.get("jobs") or jobs0  # type: ignore[attr-defined]
    if ps._jobs:
        ps.about = {"kind": ps._jobs.product_kind,
                    "jobs": [{"original": o, "need": n} for o, n in zip(ps._jobs.raw_jobs, ps._jobs.needs)]}
    ps._disp_flags = {d.id: f for d in dispositions.values()  # type: ignore[attr-defined]
                      if (f := motive_flag(d.prior, jobs0.jobs if jobs0 else None))}
    for i, f in ps._disp_flags.items():
        log.append(f"principle CHECK {i}: {f}")
    ps._moments = moment_items  # type: ignore[attr-defined]
    return ps
