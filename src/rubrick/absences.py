"""The subtractive channel's BASELINE and OPEN OBSERVATION — omission seen as openly as addition.

Every omission is an absence detector in one registry (rubrick.subtractions). This module
supplies what that registry is measured against, and finds omissions it doesn't know yet:

  1. JOBS — what the product is FOR: the user-facing jobs (verbs on domain objects) with
     every MECHANISM stripped ("delete a task", never "delete with an undo row"), plus a
     deterministic scrub of the product's own component names. This is the two-channel
     discipline for omission: a substitute IS structure (an UndoRow replaces a confirm
     dialog), so a baseline built from the product's structure inherits its substitutes
     and becomes blind to what the product refused.
  2. GENERIC TWIN — the consumer agent builds those jobs its own default way, with no
     design direction; materialized with the product's file layout so every registry
     measurement runs on it through the same code as on the product. Integrity rule as in
     baseline.py: the twin is a real model generation, never authored by us.
  3. SURVEY (seen) — diff the product's code against the twin's: what the twin includes
     that the product systematically leaves out, WHERE in the product it would apply (the
     host — mechanically checked against the source), what the product does INSTEAD, and
     any sign the gap is an ACCIDENT (unused tokens, half-wired handlers). Triage is
     deterministic: ungrounded hosts are dropped, findings are confidence-ranked
     (substitute and no counter-evidence = high; counter-evidence and no substitute = low).
  4. Promoted findings become instructed SUBTRACTIONs, then gated detectors (inverted
     admission, rubrick.detectors), and join the registry.
"""

from __future__ import annotations

import json
import pathlib
import re

from pydantic import BaseModel

from rubrick import learned, paths
from rubrick.baseline import content_key, load_key

_CACHE = paths.cache_dir() / "absence_cache.json"
_SURVEY_BUDGET = 120_000  # chars of product source per call; larger products are chunked


# --- model calls (content-cached, same determinism story as every extraction) ---------

def _cached_parse(key: str, prompt: str, output_format, *, max_tokens: int,
                  use_cache: bool = True):
    cache = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    if use_cache and key in cache:
        return output_format.model_validate(cache[key])
    import anthropic
    api_key = load_key()
    if not api_key:
        raise RuntimeError("No ANTHROPIC_API_KEY found for the absence channel")
    resp = anthropic.Anthropic(api_key=api_key).messages.parse(
        model="claude-opus-4-8", max_tokens=max_tokens, thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}], output_format=output_format)
    out = resp.parsed_output
    if out is None:
        raise RuntimeError("absence channel call returned no parsed output")
    cache[key] = out.model_dump()
    _CACHE.write_text(json.dumps(cache, indent=2))
    return out


def _source_files(repo: str, gcss: str, comps: str) -> list[tuple[str, str]]:
    from rubrick.discover import discover_components
    files = []
    g = pathlib.Path(repo) / gcss
    if g.exists():
        files.append((gcss, g.read_text()))
    for f in discover_components(repo, comps):
        try:
            files.append((str(pathlib.Path(f).relative_to(repo)), pathlib.Path(f).read_text()))
        except Exception:
            continue
    return files


def _chunks(repo: str, gcss: str, comps: str) -> list[str]:
    """The product source, chunked on file boundaries under the budget. Coverage is
    complete (no truncation): callers reconcile across chunks."""
    chunks, cur = [], ""
    for name, text in _source_files(repo, gcss, comps):
        block = f"// ==== {name} ====\n{text[:_SURVEY_BUDGET]}\n"
        if cur and len(cur) + len(block) > _SURVEY_BUDGET:
            chunks.append(cur)
            cur = ""
        cur += block
    if cur:
        chunks.append(cur)
    return chunks


# --- 1. jobs: what the product is FOR, with every mechanism stripped -------------------

class Jobs(BaseModel):
    product_kind: str        # "a personal task list", "a live operations console"
    jobs: list[str] = []     # user-facing outcomes, mechanism-free (after rewrite + overrides)
    content: list[str] = []  # the domain objects and the data they carry
    raw_jobs: list[str] = []  # as extracted, before the need-rewrite (the review file shows both)
    needs: list[str] = []     # the rewrite of each raw job, BEFORE designer overrides (same length)


class _Need(BaseModel):
    original: str
    need: str


class _Needs(BaseModel):
    product_kind: str
    needs: list[_Need] = []


_REWRITE_PROMPT = """Below are jobs extracted from ONE product. Some are stated as the trace
of that product's particular DESIGN CHOICE rather than the user's underlying need — e.g.
"restore a removed task" is how an undo-based product phrases "recover from removing a
task by mistake" (which a generic build would more likely serve with a confirmation);
"view past states of the board" may be the trace of a replay feature behind "understand
how the project changed over time".

Two levels — keep them apart:
- The product CATEGORY, as a user would name it (a kanban board, a spreadsheet, a map, a
  drawing tool, a chat app). KEEP it: a category's standard conventions are exactly the
  generic defaults the baseline must contain. product_kind = the category, minus any
  feature that is this product's own choice ("a kanban board", not "a kanban board with
  history replay").
- This product's CHOICES within the category. Rewrite a job only when its phrasing
  reflects one of those choices; then state the underlying need, at the level where
  different products OF THIS CATEGORY would solve it differently. A job that is standard
  for the category ("move a card to another column" on a kanban board) stays as is.
Merge jobs that are two faces of one need (one entry, `original` = the first). Never
introduce a mechanism, widget, gesture or feedback technique that the job didn't name.

PRODUCT KIND: {kind}
JOBS:
{jobs}"""


def rewrite_to_needs(kind: str, jobs: list[str], *, use_cache: bool = True) -> _Needs:
    prompt = _REWRITE_PROMPT.format(kind=kind, jobs="\n".join(f"- {j}" for j in jobs))
    return _cached_parse("needs:" + content_key(prompt), prompt, _Needs,
                         max_tokens=3000, use_cache=use_cache)


def _repo_key(repo: str) -> str:
    return str(pathlib.Path(repo).resolve())


def apply_job_overrides(jobs: list[tuple[str, str]], overrides: dict) -> list[str]:
    """(original, need) pairs -> the needs the twin is built from, after the designer's
    overrides (keyed by the original job, lower-cased): 'STRIKE' drops it, any other text
    replaces it. Pure."""
    out = []
    for orig, need in jobs:
        o = overrides.get(orig.strip().lower())
        if o == "STRIKE":
            continue
        out.append(o if o else need)
    return out


_JOBS_PROMPT = """Read this product's source and describe WHAT IT IS FOR — not how it is
built. Output:
- product_kind: a short plain description of the kind of product.
- jobs: the outcomes a user can accomplish or needs, as verbs on domain objects
  ("add a task", "remove a task", "know whether changes are saved", "see how many tasks
  are open"). STRIP EVERY MECHANISM: never mention a UI component, widget, layout, visual
  treatment, feedback mechanism, animation, safeguard or interaction technique (not
  "undo", "inline", "toast", "dialog", "badge", "row", "icon", "hover", "drag"...). Two
  products that solve the same jobs in completely different ways must get the same list.
- content: the domain objects and the fields they carry.

SOURCE{chunk_note}:
{source}"""


def _component_names(repo: str, comps: str, domain: set[str]) -> set[str]:
    """The product's component names, plus their words that are NOT domain nouns
    (UndoRow -> UndoRow, Undo, Row; but TaskRow keeps 'Task' when tasks are the content)."""
    from rubrick.discover import discover_components
    names = set()
    for f in discover_components(repo, comps):
        stem = pathlib.Path(f).stem
        if stem in ("page", "layout", "index"):
            continue
        names.add(stem)
        for w in re.findall(r"[A-Z][a-z]+", stem):
            if w.lower().rstrip("s") not in domain:
                names.add(w)
    return {n for n in names if len(n) >= 3}


def scrub(text: str, names: set[str]) -> str:
    """Deterministically remove the product's own component names (and their words) from
    a jobs line — the model is told to strip mechanism, this guarantees the names don't
    leak (an 'UndoRow' must not tell the twin to build an undo row)."""
    for n in sorted(names, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(n)}\b", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;-")


_JOBS_MEMORY = paths.cache_dir() / "jobs_memory.json"

class _JobsDelta(BaseModel):
    add_jobs: list[str] = []
    remove_jobs: list[str] = []      # verbatim entries of the previous list
    add_content: list[str] = []
    remove_content: list[str] = []


_JOBS_DELTA_PROMPT = """Below is the previous description of WHAT A PRODUCT IS FOR, and the
product's current source. A product's purpose rarely changes between edits. Report ONLY
real changes in what users can accomplish: jobs the source now supports that the list
lacks (add_jobs, same mechanism-free style: verbs on domain objects, no UI mechanism),
and previous entries the source no longer supports (remove_jobs, copied VERBATIM).
Same for content. Rewording, renames, refactors and styling are NOT changes — for an
edit with no change in purpose, every list is empty.

PREVIOUS DESCRIPTION:
{prev}

SOURCE{chunk_note}:
{source}"""


def apply_jobs_delta(prev: dict, deltas: list[_JobsDelta]) -> dict:
    """Keep the previous description VERBATIM, applying only reported changes. With
    several chunks, adds are unioned and a removal needs EVERY chunk to agree (a chunk
    that doesn't show a job is not evidence the product lost it). Pure."""
    def merge(key, add, rem):
        removed = set.intersection(*({x.strip().lower() for x in getattr(d, rem)} for d in deltas)) \
            if deltas else set()
        kept = [x for x in prev.get(key, []) if x.strip().lower() not in removed]
        seen = {x.strip().lower() for x in kept}
        for d in deltas:
            for x in getattr(d, add):
                if x.strip() and x.strip().lower() not in seen:
                    seen.add(x.strip().lower())
                    kept.append(x.strip())
        return kept
    return {"product_kind": prev.get("product_kind", ""),
            "jobs": merge("jobs", "add_jobs", "remove_jobs"),
            "content": merge("content", "add_content", "remove_content")}


def _jobs_memory() -> dict:
    try:
        return json.loads(_JOBS_MEMORY.read_text()) if _JOBS_MEMORY.exists() else {}
    except Exception:
        return {}


def extract_jobs(repo: str, gcss: str, comps: str, *, use_cache: bool = True) -> Jobs:
    """What the product is FOR. STICKY across recompiles: the previous extraction for this
    repo is fed back and kept verbatim unless the source contradicts it — so an edit with
    no design meaning leaves the jobs identical, every downstream generation (rewrite,
    twins, matching) hits its cache, and no decision moves. Overrides (keyed on the raw
    job text) stay attached for the same reason."""
    chunks = _chunks(repo, gcss, comps)
    if not chunks:
        return Jobs(product_kind="")
    prev = _jobs_memory().get(_repo_key(repo))
    parts = []
    if prev:  # sticky: the model reports CHANGES only; code keeps the rest verbatim
        deltas = []
        for n, chunk in enumerate(chunks):
            note = f" (part {n + 1} of {len(chunks)})" if len(chunks) > 1 else ""
            prompt = _JOBS_DELTA_PROMPT.format(prev=json.dumps(prev, indent=1),
                                               chunk_note=note, source=chunk)
            deltas.append(_cached_parse("jobsdelta:" + content_key(prompt), prompt, _JobsDelta,
                                        max_tokens=3000, use_cache=use_cache))
        parts = [Jobs(**apply_jobs_delta(prev, deltas))]
    else:
        for n, chunk in enumerate(chunks):
            note = f" (part {n + 1} of {len(chunks)})" if len(chunks) > 1 else ""
            prompt = _JOBS_PROMPT.format(chunk_note=note, source=chunk)
            parts.append(_cached_parse("jobs:" + content_key(prompt), prompt, Jobs,
                                       max_tokens=4000, use_cache=use_cache))
        # settle on the FIRST compile: check the fresh extraction against the source once
        # (the same delta pass every later compile runs), so compile 1 == compile 2.
        first = {"product_kind": parts[0].product_kind,
                 "jobs": [j for p in parts for j in p.jobs],
                 "content": [c for p in parts for c in p.content]}
        deltas = []
        for n, chunk in enumerate(chunks):
            note = f" (part {n + 1} of {len(chunks)})" if len(chunks) > 1 else ""
            prompt = _JOBS_DELTA_PROMPT.format(prev=json.dumps(first, indent=1),
                                               chunk_note=note, source=chunk)
            deltas.append(_cached_parse("jobsdelta:" + content_key(prompt), prompt, _JobsDelta,
                                        max_tokens=3000, use_cache=use_cache))
        parts = [Jobs(**apply_jobs_delta(first, deltas))]
    domain = {w.lower().rstrip("s") for p in parts for t in [p.product_kind, *p.content]
              for w in re.findall(r"[A-Za-z]{3,}", t)}
    names = _component_names(repo, comps, domain)
    seen_j, seen_c, jobs, content = set(), set(), [], []
    for p in parts:  # union across chunks, scrubbed
        for j in p.jobs:
            s = scrub(j, names)
            if s and s.lower() not in seen_j:
                seen_j.add(s.lower())
                jobs.append(s)
        for c in p.content:
            s = scrub(c, names)
            if s and s.lower() not in seen_c:
                seen_c.add(s.lower())
                content.append(s)
    mem = _jobs_memory()  # remember the raw (pre-scrub) extraction for the next compile
    mem[_repo_key(repo)] = {"product_kind": parts[0].product_kind,
                            "jobs": [j for p in parts for j in p.jobs],
                            "content": [c for p in parts for c in p.content]}
    _JOBS_MEMORY.write_text(json.dumps(mem, indent=2))
    # the KIND is a category name ("a kanban board") — scrub only full component names
    # from it (a 'Board' component must not strip the category noun "board")
    stems = {n for n in names if re.search(r"[a-z][A-Z]", n)}
    kind = scrub(parts[0].product_kind, stems)
    try:
        needs = rewrite_to_needs(kind, jobs, use_cache=use_cache)
        pairs = [(n.original, scrub(n.need, names)) for n in needs.needs if n.need.strip()]
        kind = scrub(needs.product_kind, stems) or kind
    except Exception:
        pairs = [(j, j) for j in jobs]  # no key: the scrubbed extraction stands
    overrides = learned.load().get("job_overrides", {}).get(_repo_key(repo), {})
    return Jobs(product_kind=kind, jobs=apply_job_overrides(pairs, overrides),
                content=content, raw_jobs=[o for o, _ in pairs], needs=[n for _, n in pairs])


# --- 2. the GENERIC TWIN: the baseline every absence is measured against ---------------

class TwinFile(BaseModel):
    path: str
    content: str


class GenericTwin(BaseModel):
    files: list[TwinFile] = []


_TWIN_PROMPT = """You are the coding agent asked to build this product, with NO design
direction. Write a COMPLETE implementation — the obvious, competent build a good engineer
produces by default. Keep the code tight, but do NOT simplify away anything you would
normally include just to save space: this build is the reference for what a default
build contains. Make every decision the way you normally would: page
chrome, containers, depth, rounding, color, type, iconography, how status and counts are
displayed, feedback after actions, safeguards on destructive actions, loading states,
hover/press states, transitions. Include what you would normally include; leave out
what you normally would not. Do not aim for any particular aesthetic.

PRODUCT: {kind}
USERS NEED TO:
{jobs}
CONTENT:
{content}

Output files:
- `{gcss}` — the global stylesheet,
- `.tsx` component files under `{comps}/` (React; inline styles and/or class names backed
  by the stylesheet; any common libraries you'd normally use), at most 10 files, each
  under ~100 lines. Name files however you like.
Paths must be relative, under those two locations only."""


# Several twins, each from a different (equally undirected) builder framing, so a single
# generation's quirks can't decide what counts as default: the model takes no temperature,
# so variety has to come from the framing. A move is DEFAULT when a majority of twins have it.
TWIN_FRAMINGS = {
    "default": "",
    "library": ("\nYou build the way most product teams do today: React with a popular "
                "component library and its stock patterns."),
    "plain": ("\nYou build the way a careful engineer does with no component library: "
              "hand-written components and CSS, still including whatever you'd normally include."),
}


def generate_twin(repo: str, gcss: str, comps: str, *, framing: str = "default",
                  jobs: Jobs | None = None, use_cache: bool = True) -> GenericTwin:
    jobs = jobs or extract_jobs(repo, gcss, comps, use_cache=use_cache)
    if not jobs.jobs:
        return GenericTwin()
    prompt = _TWIN_PROMPT.format(kind=jobs.product_kind or "a web product",
                                 jobs="\n".join(f"- {j}" for j in jobs.jobs),
                                 content="\n".join(f"- {c}" for c in jobs.content) or "- (none)",
                                 gcss=gcss, comps=comps) + TWIN_FRAMINGS[framing]
    # 21k: just under the SDK's non-streaming ceiling; thinking shares this budget, and a
    # truncated twin fails JSON parsing (the caller logs it per framing — never silently)
    return _cached_parse("twin:" + content_key(prompt), prompt, GenericTwin,
                         max_tokens=21000, use_cache=use_cache)


def build_baseline(repo: str, gcss: str, comps: str) -> dict:
    """The jobs + every framing's materialized twin — built ONCE per compile and shared by
    the subtractive channel and the component twin check. {"jobs", "twins": [(name,
    repo, gcss, comps)], "log"}; empty twins when no key (callers degrade)."""
    log, twins, jobs = [], [], None
    try:
        jobs = extract_jobs(repo, gcss, comps)
        log.append(f"baseline jobs ({jobs.product_kind}): {jobs.jobs}")
        for name in TWIN_FRAMINGS:
            try:
                t = generate_twin(repo, gcss, comps, framing=name, jobs=jobs)
            except Exception as e:  # one framing failing must not shrink the vote silently
                log.append(f"generic twin '{name}': FAILED ({type(e).__name__}: {str(e)[:120]})")
                continue
            if (root := materialize_twin(t, gcss, comps)):
                twins.append((name, root, gcss, comps))
        log.append(f"generic twins: {len(twins)}/{len(TWIN_FRAMINGS)} "
                   f"{[t[0] for t in twins]}")
    except Exception as e:
        log.append(f"generic twins: SKIPPED ({type(e).__name__}: {e}) — baseline unavailable")
    return {"jobs": jobs, "twins": twins, "log": log}


def materialize_twin(twin: GenericTwin, gcss: str, comps: str) -> str | None:
    """Write the twin under .cache/twins/<content hash>/ with the product's layout, so
    every measurement runs on it EXACTLY as on the product (same code path). Paths are
    confined to the stylesheet and the components dir. None if nothing usable."""
    import hashlib
    blob = json.dumps(twin.model_dump(), sort_keys=True)
    root = paths.cache_dir() / "twins" / hashlib.sha1(blob.encode()).hexdigest()[:16]
    comps_root = pathlib.PurePosixPath(comps)
    wrote = 0
    for f in twin.files:
        rel = pathlib.PurePosixPath(f.path.strip().lstrip("/"))
        if ".." in rel.parts:
            continue
        if str(rel) != gcss and not (rel.parts[:len(comps_root.parts)] == comps_root.parts
                                     and rel.suffix in (".tsx", ".ts", ".jsx", ".css")):
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f.content)
        wrote += 1
    return str(root) if wrote else None


# --- 3. the survey: product code vs twin code ----------------------------------------

class AbsenceSighting(BaseModel):
    name: str                 # OPEN str — kebab-case, names the THING omitted
    category: str             # surface | structure | feedback | interaction | content
    twin_evidence: str        # the twin code that includes it (becomes a generic exemplar)
    host: str                 # the product component/element where it would apply
    evidence: str             # that the product genuinely lacks it, everywhere
    instead: str = ""         # what the product does in its place, if anything
    against: str = ""         # signs the gap is ACCIDENTAL (unused token, half-wired code)
    systematic: bool          # absent everywhere it would apply


class AbsenceSurvey(BaseModel):
    deliberate: list[AbsenceSighting] = []
    unverified_seen: list[str] = []


_SURVEY_PROMPT = """Two builds of the same product. The GENERIC TWIN is the undirected
default build; the PRODUCT is the designed one. Report what the twin includes that the
product DELIBERATELY LEAVES OUT.

ALREADY KNOWN omissions — do NOT report these (tracked elsewhere):
{known}

For each omission:
- name: kebab-case, naming the THING omitted (e.g. "confirm-dialog", "toast", "icons"),
  not the product's substitute.
- twin_evidence: the exact twin code that includes it (one short snippet).
- host: the PRODUCT's component or element where it would apply (it must exist in the
  product source — an omission is a treatment missing from something that EXISTS; if the
  product has nothing it would attach to, it is not an omission, do not report it).
- evidence: that the product lacks it EVERYWHERE — search every spelling first (CSS,
  inline style, Tailwind, libraries).
- instead: a DIFFERENT mechanism the product uses to serve the same purpose (inline
  status text for toasts, an undo for a confirm dialog, text labels for icons). Merely
  restating the absence ("none", "instant", "plain", "static", "no X") is NOT a
  substitute — leave it empty.
- against: any sign the gap is an ACCIDENT rather than a refusal — a token or class
  defined but never applied, a handler or state wired halfway, a TODO; empty if none.
  Report the omission anyway; the designer weighs it.
- systematic: false if it is missing only in some places it would apply.
NEVER report missing accessibility, error handling, security, or correctness features —
their absence is a defect, not identity. An empty list is correct when the product
includes the twin's defaults.

In `unverified_seen`, list which of these designer-confirmed omissions the product
maintains (absent throughout): {unverified}

GENERIC TWIN:
{twin}

PRODUCT{chunk_note}:
{source}"""


def _known_omissions() -> list[str]:
    from rubrick.subtractions import registry
    reg = registry()
    known = [f"- {k}: {v['note']}" for k, v in sorted(reg.items())]
    known += [f"- {k}: {v}" for k, v in learned.promoted_absences().items() if k not in reg]
    known += [f"- {k}: (designer discarded)" for k in learned.discarded("absence")]
    return known


def _twin_source(twin_repo: str, gcss: str, comps: str) -> str:
    return "\n".join(f"// ==== {n} ====\n{t}" for n, t in _source_files(twin_repo, gcss, comps))


def survey_absences(repo: str, gcss: str, comps: str, twin_repo: str, *,
                    use_cache: bool = True) -> AbsenceSurvey:
    from rubrick.detectors import learned_names
    twin_src = _twin_source(twin_repo, gcss, comps)
    if not twin_src:
        return AbsenceSurvey()
    unverified = sorted(set(learned.promoted_absences()) - learned_names("absence"))
    chunks = _chunks(repo, gcss, comps)
    results = []
    for n, chunk in enumerate(chunks):
        note = f" (part {n + 1} of {len(chunks)} — judge only what this part shows)" \
            if len(chunks) > 1 else ""
        prompt = _SURVEY_PROMPT.format(known="\n".join(_known_omissions()) or "(none)",
                                       unverified=unverified or "(none)", twin=twin_src,
                                       chunk_note=note, source=chunk)
        results.append(_cached_parse("survey:" + content_key(prompt), prompt, AbsenceSurvey,
                                     max_tokens=8000, use_cache=use_cache))
    if len(results) == 1:
        return results[0]
    # multi-chunk: an omission holds only if EVERY part reports it (by name)
    common = set.intersection(*({s.name for s in r.deliberate} for r in results))
    first = {s.name: s for s in results[0].deliberate}
    seen = set.intersection(*(set(r.unverified_seen) for r in results))
    return AbsenceSurvey(deliberate=[first[n] for n in sorted(common)],
                         unverified_seen=sorted(seen))


# --- deterministic triage ------------------------------------------------------------

_STOP = {"the", "and", "for", "with", "each", "every", "all", "component", "element",
         "button", "buttons", "text", "list", "item", "items", "page", "main", "div", "span"}


def host_grounded(host: str, product_source: str) -> bool:
    """The host must name something that EXISTS in the product: at least one distinctive
    word of it (identifier-ish, 4+ chars, not filler) appears in the source."""
    src = product_source.lower()
    words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", host)}  # `.row` counts
    words |= {w.lower() for w in re.findall(r"[A-Z][a-z]{2,}", host)}           # TaskRow -> task, row
    words -= _STOP
    # whole-word match, so a 3-letter host word can't hit inside an unrelated identifier
    return any(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", src) for w in words)


def confidence(s: AbsenceSighting) -> str:
    """A substitute is the strongest sign of a refusal; counter-evidence the strongest
    sign of an accident."""
    sub, against = bool(s.instead.strip()), bool(s.against.strip())
    if sub and not against:
        return "high"
    if against and not sub:
        return "low"
    return "medium"


_RANK = {"high": 0, "medium": 1, "low": 2}


def triage(survey: AbsenceSurvey, product_source: str, known: set[str],
           discarded: set[str]) -> tuple[list[dict], list[str]]:
    """(pending tears ranked high -> low, dropped-with-reason log lines). Pure."""
    keep, dropped = [], []
    for s in survey.deliberate:
        if s.name in known or s.name in discarded:
            continue
        if not s.systematic:
            dropped.append(f"{s.name}: not systematic")
            continue
        if not host_grounded(s.host, product_source):
            dropped.append(f"{s.name}: host {s.host!r} not found in the product (inapplicable)")
            continue
        keep.append({"name": s.name, "modality": "absence", "category": s.category,
                     "host": s.host, "evidence": s.evidence, "instead": s.instead,
                     "against": s.against, "confidence": confidence(s),
                     "exemplars": [s.twin_evidence] if s.twin_evidence.strip() else []})
    keep.sort(key=lambda p: (_RANK[p["confidence"]], p["name"]))
    return keep, dropped


# --- the compile-time channel ----------------------------------------------------------

def observe_absences(repo: str, gcss: str, comps: str, *, designed: bool,
                     baseline: dict | None = None, roles: list[str] | None = None) -> dict:
    """The whole subtractive channel for one compile. Returns
    {"subtractions": captured records, "uncertain": records for the designer,
     "pending": ranked tears, "observed": instructed-only, "log": lines}.
    Every registered absence goes through the ONE rule in subtractions.classify, voted
    across the generic twins (`baseline` from build_baseline — built here if absent).
    Model calls are content-cached; failures degrade, never crash."""
    from rubrick.facet_signatures import raw_source
    from rubrick.subtractions import classify, registry
    empty = {"subtractions": [], "uncertain": [], "pending": [], "observed": [], "log": []}
    if not designed:
        return empty
    log, pending, observed = [], [], []
    if baseline is None:
        baseline = build_baseline(repo, gcss, comps)
        log += baseline["log"]
    twins = [t[1:] for t in baseline["twins"]]
    res = classify(repo, gcss, comps, twins, designed=True)
    log += res["log"]
    captured, uncertain = [], []
    for rec in res["captured"] + res["uncertain"]:  # a designer decision is final
        dec = learned.intent_decision(f"absence:{rec['omits']}")
        if dec == "DISCARD":
            continue
        if rec in res["captured"]:
            captured.append(rec)
        elif dec == "CAPTURE":
            captured.append({**rec, "baseline": rec["baseline"] + "; designer confirmed"})
        else:
            uncertain.append(rec)
    for r in captured:
        log.append(f"subtraction: OMITS {r['omits']} — {r['note']} [{r['baseline']}]")
    for r in uncertain:
        log.append(f"subtraction: UNCERTAIN {r['omits']} [{r['baseline']}] -> confirm_intent")
    if twins:
        rep = twins[res["representative"] or 0]
        log.append(f"absence survey: against the '{baseline['twins'][res['representative'] or 0][0]}' "
                   f"twin (closest to the majority)")
        try:
            survey = survey_absences(repo, gcss, comps, rep[0])
            known = set(registry())
            pending, dropped = triage(survey, raw_source(repo, gcss, comps), known,
                                      set(learned.discarded("absence")))
            for d in dropped:
                log.append(f"absence survey: dropped {d}")
            promoted = learned.promoted_absences()
            observed = [{"name": n, "note": promoted.get(n, "")}
                        for n in survey.unverified_seen if n in promoted and n not in known]
            log.append("absence survey: novel "
                       + (", ".join(f"{p['name']}({p['confidence']})" for p in pending) or "none")
                       + (f" · unverified-seen {sorted(o['name'] for o in observed)}"
                          if observed else ""))
        except Exception as e:
            log.append(f"absence survey: SKIPPED ({type(e).__name__}: {e})")
    return {"subtractions": captured, "uncertain": uncertain, "pending": pending,
            "observed": observed, "log": log}


# --- the GESTURE layer: is this component's gesture/pattern the default FOR ITS PURPOSE? --
# Gestures and structural patterns count as identity on their own (components.
# _identity_bearing) — context-blind: drag between columns is the DEFAULT for a kanban
# board. The twins decide, PER PURPOSE: each product component is matched to the twin
# file serving the same purpose (a model call — purpose is semantic), and the
# counterparts' gestures/patterns are read with the SAME deterministic detectors. A
# gesture/pattern a MAJORITY of counterparts share is default for that purpose; a
# component whose identity rested only on such defaults goes to REVIEW, never silently
# out — the twin can only downgrade a capture to a question, never erase identity.
# The FEEL layer (treatments, timings, material) is untouched: it keeps its global
# per-moment baselines, which can't leak.

class _Match(BaseModel):
    role: str
    counterparts: list[str] = []  # the twin file paths that together serve the same purpose


class _Matches(BaseModel):
    matches: list[_Match] = []


_MATCH_PROMPT = """Match each PRODUCT component to the files in the GENERIC BUILD that
TOGETHER serve the SAME PURPOSE for the user (what it lets them do or see) — regardless
of how differently it is implemented, named or split across files (one product file may
correspond to several generic files, e.g. a board split into board/column/card). Use an
empty list when no generic file serves that purpose. Match by purpose only, never by
name or technique."""
_MATCH_PROMPT_TAIL = """

PRODUCT COMPONENTS:
{product}

GENERIC BUILD FILES:
{twin}"""


def _excerpt(text: str, lines: int = 40) -> str:
    return "\n".join(text.splitlines()[:lines])


def match_counterparts(repo: str, roles: dict, twin_root: str, gcss: str, comps: str, *,
                       use_cache: bool = True) -> dict:
    """{role: [twin file texts]} — the twin files that together serve the same purpose."""
    tfiles = {n: t for n, t in _source_files(twin_root, gcss, comps) if n != gcss}
    if not tfiles or not roles:
        return {r: [] for r in roles}
    prompt = (_MATCH_PROMPT + _MATCH_PROMPT_TAIL).format(
        product="\n\n".join(f"### {r}\n{_excerpt(pathlib.Path(p).read_text())}"
                             for r, p in sorted(roles.items())),
        twin="\n\n".join(f"### {n}\n{_excerpt(t)}" for n, t in sorted(tfiles.items())))
    out = _cached_parse("match:" + content_key(prompt), prompt, _Matches,
                        max_tokens=3000, use_cache=use_cache)
    by_role = {m.role: [c.strip() for c in m.counterparts] for m in out.matches}
    return {r: [tfiles[c] for c in by_role.get(r, []) if c in tfiles] for r in roles}


def gesture_defaults(sig: dict, counterparts: list[list[str]]) -> dict:
    """Which of a component's identity gestures/patterns a MAJORITY of twins use for the
    same purpose (default for it). Pure: one entry per twin, each the list of that twin's
    counterpart file texts ([] = no counterpart); a twin has the gesture/pattern when ANY
    of its counterpart files does (read per file — no cross-file conjunctions)."""
    from rubrick.components import _DISTINCTIVE_GESTURES, detect_gesture, detect_patterns
    n = len(counterparts)
    if not n:
        return {"gesture": False, "patterns": set(), "votes": "no twins"}
    g = sig.get("gesture")
    g_votes = sum(1 for files in counterparts if any(detect_gesture(f) == g for f in files)) \
        if g in _DISTINCTIVE_GESTURES else 0
    p_votes = {p: sum(1 for files in counterparts if any(p in detect_patterns(f) for f in files))
               for p in sig.get("patterns", ())}
    return {"gesture": g in _DISTINCTIVE_GESTURES and 2 * g_votes > n,
            "patterns": {p for p, v in p_votes.items() if 2 * v > n},
            "votes": f"{g}: {g_votes}/{n}" + "".join(f", {p}: {v}/{n}" for p, v in p_votes.items())}


def still_identity(sig: dict, defaults: dict) -> bool:
    """Is the component identity-bearing WITHOUT the gestures/patterns that are default
    for its purpose? (material and treatments — the feel — still count in full.)"""
    from rubrick.components import _identity_bearing
    stripped = {**sig, "gesture": "click" if defaults["gesture"] else sig.get("gesture"),
                "patterns": set(sig.get("patterns", ())) - defaults["patterns"]}
    return _identity_bearing(stripped)


def check_component_gestures(repo: str, sigs: list[dict], baseline: dict, comps: str,
                             gcss: str) -> dict:
    """Split captured component sigs into {"kept", "review", "log"} by the twin check."""
    from rubrick.discover import discover_components
    from rubrick.components import _kebab
    twins = baseline.get("twins") or []
    if not twins:
        return {"kept": sigs, "review": [], "log": ["gesture twin-check: no twins — skipped"]}
    paths_by_role = {_kebab(pathlib.Path(f).stem): f for f in discover_components(repo, comps)}
    roles = {s["role"]: paths_by_role[s["role"]] for s in sigs if s["role"] in paths_by_role}
    per_twin = []
    for name, root, tg, tc in twins:
        try:
            per_twin.append(match_counterparts(repo, roles, root, tg, tc))
        except Exception:
            per_twin.append({r: [] for r in roles})
    kept, review, log = [], [], []
    for s in sigs:
        d = gesture_defaults(s, [m.get(s["role"], []) for m in per_twin])
        if (d["gesture"] or d["patterns"]) and not still_identity(s, d):
            dec = learned.intent_decision(f"component:{s['role']}")
            if dec == "CAPTURE":
                kept.append(s)
                log.append(f"gesture twin-check: {s['role']} default for its purpose "
                           f"({d['votes']}) — designer confirmed, kept")
            elif dec != "DISCARD":
                review.append({**s, "_votes": d["votes"]})
                log.append(f"gesture twin-check: {s['role']} -> REVIEW — its identity is a "
                           f"gesture/pattern the generic build uses for the same purpose ({d['votes']})")
            continue
        kept.append(s)
        log.append(f"gesture twin-check: {s['role']} kept ({d['votes']})")
    return {"kept": kept, "review": review, "log": log}


# --- exemplars + near-misses for detector admission ------------------------------------

class _Exemplars(BaseModel):
    exemplars: list[str]
    near_misses: list[str] = []


_EXEMPLAR_PROMPT = """You are the coding agent building a typical, undirected React/TSX +
CSS product. Show how a generic build would implement "{name}" ({description}).
SHORT snippets, under 200 chars each:
- exemplars: 2–3 generic implementations that differ in CONSTRUCT, not just spelling —
  vary the visual form and technique (Tailwind vs inline style vs a component library),
  so together they pin down WHAT the thing is, not one way of drawing it. Include a
  common component-library spelling when one exists.
- near_misses: 1–2 snippets of common code that SHARES a surface trait with it but is
  NOT it — a detector for the thing must not fire on these.
Plain and typical — no design direction."""


def generate_exemplars(name: str, description: str, *,
                       use_cache: bool = True) -> tuple[list[str], list[str]]:
    """(exemplars, near_misses) — a SEPARATE generation from the detector proposal, so
    admission against them is not the proposer grading itself."""
    prompt = _EXEMPLAR_PROMPT.format(name=name, description=description or name)
    out = _cached_parse("exemplars:" + content_key(prompt), prompt, _Exemplars,
                        max_tokens=3000, use_cache=use_cache)
    return ([e for e in out.exemplars if e.strip()][:3],
            [e for e in out.near_misses if e.strip()][:2])
