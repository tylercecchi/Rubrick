# Detectors — how Rubrick observes identity moves

A **detector** turns a product's source into the **identity moves** it carries — the deltas from a
generic build that a conformance check then requires. This doc is the contributor's map of the
detection layer: what's deterministic vs. what's genuinely semantic, the move vocabulary, and how
to add or audit a signature without breaking the guard.

Core code: [`src/rubrick/facet_signatures.py`](src/rubrick/facet_signatures.py).

## The two mechanisms

Rubrick detects a move one of two ways, and the split is deliberate:

**A. Deterministic signature** — a pure function of the declared DOM/CSS (regex over source). Same
input → same output, so a compile and a later check of identical code agree exactly (self-conformance
is *exact*, no flap). Most moves are here. This is the default; prefer it.

**B. LLM / semantic** — a model read, used **only** where the judgment is about *meaning*, not a code
shape. This is irreducible for a few things (see below) and it's the price of real semantic power: it
can shift between edits. Keep this set as small as possible.

**The governing rule: observation is OPEN, verification is CLOSED, and the closed set grows from
the open one.** The signatures bound only what can be *verified*, never what can be *seen*: the
novelty surveys (`novelty.py`) read every product with an open vocabulary, so a move or pattern no
signature anticipates still surfaces as a tear. Promotion then moves it through three stages —
**seen** (open observation) → **instructed** (checklist + guide, unverified) → **gated** (a
model-proposed detector passes admission, below). The hand-written signatures are the gate's seed
corpus, not its ceiling.

## Learned detectors (the gate's self-extension)

When a designer promotes a signature-observed kind (a density/elevation/ambient/typography move, a
treatment, or an interaction pattern), `apply_review` asks the model to **propose a detector** —
not code, but a declarative conjunctive spec stored in `learned.json` (`learned_detectors`):

```json
{"all": ["onScroll|addEventListener\\s*\\(\\s*['\"]scroll", "scrollTop\\s*=|scrollTo\\s*\\("], "none": [], "flags": ""}
```

Every `all` regex must match the source, no `none` regex may. Executing a spec
(`detectors.run_spec`) is a pure function, so everything the gate promises still holds. A proposal
only becomes `active` after **mechanical admission** (`detectors.admit`): well-formed, matches the
calibration product it was proposed for, and does NOT match the embedded generic floor (a vendored
copy of the Generic fixture, kept in sync by the eval). Rejected proposals are recorded but never
gate — the word stays at the *instructed* stage. Active specs are unioned into every detection site
(`detect_patterns`, `detect_treatments`, `detect_facet_moves`, the typography hybrid, and the
measurable-move universe for deployment prevalence), and are git-diffable and revocable: delete the
entry and the gate shrinks back. The proposal prompt enforces this file's discipline (generalize
beyond the calibration construct; fewest conjuncts that stay discriminating) — but clause 2 of the
four-way check ("an honest alternative build still matches") can only be *tested* once such a build
exists, so a stable FAIL on an honest build still means: suspect the detector first.

> Rule of thumb: if you can name the CSS/DOM shape that betrays the move, it's a signature. If the
> move is "what does this *mean*" (a colour that encodes status, a face that reads as the brand
> voice), it's LLM.

## What is deterministic vs. LLM

| Facet / layer | Mechanism | Where |
|---|---|---|
| **ambient** (motion loops) | deterministic | `_MOVE_SIGNATURES["ambient"]` |
| **density** (spatial strategy) | deterministic | `_MOVE_SIGNATURES["density"]` |
| **elevation** (z-axis / depth) | deterministic | `_MOVE_SIGNATURES["elevation"]` |
| **typography** | **hybrid** — 6 mechanical moves by signature; `detailed-face` + the faces stay LLM | `_type_moves` + `hybrid_type_obs` |
| **color** — moves *and* application (marking vs. decoration) | **LLM** | `extract_facet("color", …)`, `extract_color_application` |
| **native face→role** (Calibre-is-the-body-voice) | deterministic | `capture_face_roles` |
| **behavior** treatments + timings (CSS **and** motion-library idioms) | deterministic | `detect_treatments`, `detect_timings` |
| **capabilities** (runtime classes the identity rides on) | deterministic | `capabilities.detect_capabilities` |
| **interaction patterns** (carousel, staged disclosure, pointer drawing, spotlight) | deterministic | `components.detect_patterns` |
| **effect locality** (which moves get a deployment frequency) | **LLM** (generated once per vocab word, cached, designer-overridable) | `scoping.move_locality` |
| **surface** material stack (sheen/lighting/texture/bevel) | deterministic | `extract_focal_surface` |
| **magnitude** metrics (scale-contrast, weight, chroma, shadow depth, spacing, content-density) | deterministic (regex) | `type_extract`, `style_facets` |
| **discipline** metrics (`spacing_discipline`, `palette_coherence`) | deterministic | `style_facets` |
| **absences** — capture: registry (built-in + learned) vs a generated generic twin | deterministic reading; twin is generated | `subtractions.classify` |
| **absences** — open omission survey: product code vs generic-twin code | **LLM** to see (deterministic triage); learned detectors to gate | `absences.observe_absences` |
| **composition** archetype + focal anchor | **LLM** | `infer_composition` |
| **dispositions** (the "why") | **LLM** (generated, then optionally designer-refined) | `orchestrate.generate_disposition` |

`DETERMINISTIC_FACETS = {ambient, density, elevation}`; typography is the hybrid; `color` is the one
fully-semantic facet (`TYPOGRAPHY_SEMANTIC = {"detailed-face"}` is the only LLM typography move).

## The move vocabulary (deterministic signatures)

- **ambient** — perpetual-loop, breathing-pulse, rotation-spin, drift-scroll, physics-loop,
  orchestrated-stagger, ambient-restraint, presence-signal
- **density** — full-bleed-canvas, floating-overlays, generous-hero-space, information-dense,
  dynamic-density, safe-area-mobile
- **elevation** — soft-floating-shadows, flat-bordered, backdrop-blur, layered-overlays,
  dramatic-shadow, inset-depth, colored-shadow
- **typography (mechanical 6)** — custom-display-face, distinct-body-face, expressive-weight,
  extreme-scale-contrast, treated-microtype, type-as-graphic
- **interaction patterns** (`components.detect_patterns` — the *response-pattern* channel: what an
  interaction structurally IS, distinct from how it animates) — sequential-traverse (carousel:
  index-stepping + spatial motion, or an explicit carousel lib), staged-disclosure (progressive
  reveal: multiple step-gates, an expanded-set, or show-more + slice), pointer-authoring (drawing:
  pointer tracking + accumulated geometry/canvas path), spotlight-filter (select one member of a
  rendered collection → the rest demote in place). Each is conjunctive on purpose: a lone index
  (tabs), a single accordion, or a drag slider must NOT match. Patterns ride on component roles
  (group-checked, decomposition-safe), rank components into the behavior-extraction budget, and
  count as identity-bearing on their own — a quiet carousel is identity even with zero choreography.

The vocabulary is **open**: a compile can surface a novel move the vocab has no word for (a
"tear-escape"), which a designer promotes via the human loop (`learned.json`). See the README.

## Absences — one mechanism for every omission

Omission is identity as much as addition, so it gets the same open → closed trajectory — and there
are no privileged "seeds". An **absence detector** is data in one of two forms: a *pattern* spec
(as above, presence = match) or a *measure* spec `{"measure", "zeroed", "added"}` over a closed set
of deterministic primitives (`subtractions.MEASURES`: shadow blur, hue families, typefaces, font
weights, radius, gradients, ambient motion, transitions…) for omissions about **amount**, which a
regex can't express. The gap between `zeroed` and `added` prevents borderline flip-flop.

The **registry** (`subtractions.registry`) = seven built-in starter entries (`BUILTINS`) + every
active learned `absence:*` detector; a learned entry overrides a built-in of the same name, or
revokes it with status `revoked`. Every entry is captured by **one rule** against the **generic
twin** — an undirected full build generated from the product's **jobs**, not its structure
(`absences.extract_jobs` → `generate_twin`), materialized with the product's layout so every reading
runs on it through the same code. Jobs, not structure, because **a substitute *is* structure**: a
twin built from file names like `UndoRow.tsx`/`SyncStatus.tsx` rebuilds the product's own
substitutes and goes blind to what it refused (measured: 0/5 on the omissions fixture). Jobs are
verbs on domain objects with every mechanism stripped by prompt, and the product's component names
(minus its domain nouns) are scrubbed out deterministically (`absences.scrub`).

- product zeroed **and** twin has more of it, outside the zeroed range → **captured**;
- product zeroed, twin lacks it too → **uncertain** → `confirm_intent` in the review file, NOT
  captured unless the designer marks `capture` (a refusal and a never-needed look identical in code);
- no twin (no API key) → captured, marked `baseline: unavailable`.

**One measurement source, every spelling.** Measures read `subtractions.measure_source`: every
style-bearing file under the source dirs (`.ts` theme constants too, not only `.tsx`) plus a
Tailwind config, with custom properties and numeric constants resolved (`resolve.resolve_values`)
and Tailwind utilities translated into the equivalent CSS (`tailwind_as_css`: radius, shadow,
gradients, weights, named faces, hue families, `animate-*`). A literal-only reader made a
token-based product read as "no rounding" — a false refusal at capture and a missed add-back at
check (a flat system couldn't see `shadow-lg`). The eval requires literal / token / inline /
Tailwind spellings of the same styling to measure identically. The typeface count returns
*unknown* (None) when no face is named, never a silent "one face"; a measure detector's generic
exemplars must positively read as `added`, since unknown is not "has it". The flat-system
add-back threshold is 12px blur (standard drop shadows such as Tailwind `shadow-lg`, 15px, count).

Records embed their detector, so `check_subtractions` is self-contained and LLM-free; manifests
from before the unification (built-ins stored by name) resolve through `BUILTINS`. The open
channel (`absences.py`) finds what the registry doesn't know yet:

1. **Baseline** — the same generic twin (one baseline for capture and survey).
2. **Seen** — the survey diffs the product's code against the twin's (product chunked on file
   boundaries, no truncation; an omission must hold in every chunk). Each finding names the thing
   omitted, the twin code that has it (→ a generic exemplar), the product **host** it would apply
   to, what the product does **instead** (a *different mechanism* — restating the absence doesn't
   count), and anything **against** it (an unused token, half-wired state). Missing
   accessibility/error handling/security is excluded: a defect, never identity. **Triage is
   deterministic** (`absences.triage`): an ungrounded host is dropped as inapplicable, unsystematic
   and known/discarded findings never surface, and confidence = substitute & no counter-evidence →
   high, counter-evidence & no substitute → low, else medium; the review file lists high first.
3. **Instructed** — a promoted absence enters the checklist as `SUBTRACTION/<name> (unverified)`.
4. **Gated** — promotion proposes a detector (pattern or measure) with **inverted admission**
   (`detectors.admit_absence`): well-formed, does **not** match the calibration product (it omits
   the thing), and **does** match every generic exemplar (exemplars for open "other" sightings are
   generated in a separate call, so the proposer never grades itself). A measure spec is admitted by
   reading: the calibration repo zeroed, the exemplars (materialized as a repo) not. Once active it
   joins the registry and is captured by the one rule above.

An absence detector must police the *thing* being reintroduced, not one trait of it, and a false
fire here FAILS an honest build (for additive detectors it only wrongly passes). Three guards:
- **Construct-diverse exemplars** — 2–3 generic implementations that differ in form and technique
  (a Tailwind pill, an inline square chip, MUI `<Chip>`), so a shape-only spec can't match them all.
- **Near-miss probes** — generated code sharing a trait with the thing but not it (a round avatar,
  a rounded button); admission rejects any spec that fires on one, and requires at least one probe.
- **`scope: "element"`** — the conjuncts must co-occur inside ONE JSX tag or CSS rule
  (`detectors.element_units`), so a fill on one element, tight padding on another and small text on
  a third can't jointly "add a badge". `"source"` (the default, and what additive specs use) stays
  for signals that legitimately span elements, like an icon-library import plus its usage.

## The generic baseline (jobs → twins) and the gesture layer

The twin baseline is built once per compile for designed products (`absences.build_baseline`) and
shared by the subtractive channel and the component gesture check:

- **Jobs** — what the product is *for*, mechanism-free (`extract_jobs`), then **rewritten to the
  underlying need** (`rewrite_to_needs`): "view the board's past states" → "understand how the project
  changed over time". The rewrite keeps the product **category** ("a kanban board" — its conventions
  *are* the generic defaults) and rewrites only this product's choices within it; component names are
  scrubbed (full names only from the kind, so a `Board` component can't strip the category noun).
- **Sticky** — jobs persist per repo (`.cache/jobs_memory.json`): later compiles ask the model only
  for real *changes* (added/removed capabilities) and code keeps the rest verbatim
  (`apply_jobs_delta`); the first compile runs that check once against its own extraction so it
  settles immediately. An edit with no design meaning leaves the jobs identical, so every downstream
  generation hits its cache and no decision moves.
- **Designer overrides** — the review file's `baseline_jobs` shows each original job and its need;
  `strike` it or write a better need (stored per repo in `learned.json` `job_overrides`).
- **Three twins** (`TWIN_FRAMINGS`: default / component-library / hand-written) — the model takes no
  temperature, so variety comes from the framing. Registry omissions are **voted**: captured when a
  majority of twins have it; the survey reads the twin closest to the majority.

**The gesture layer** (`absences.check_component_gestures`). A distinctive gesture or a structural
pattern makes a component identity on its own (`components._identity_bearing`) — context-blind: drag
between columns is the *default* for a kanban board. Each captured component is matched to the twin
files that together serve the **same purpose** (a model call — purpose is semantic; one product file
may map to several twin files), and their gestures/patterns are read with the same deterministic
detectors, per file. A gesture/pattern a majority of twins use for that purpose is default; a
component whose identity rested only on such defaults goes to **review** (`confirm_intent`,
`component:<role>`), never silently out — the twin can only downgrade a capture to a question. The
**feel** layer (treatments, timings, material) keeps its global per-moment baselines, which can't
leak. Drag via library idioms (dnd-kit, react-beautiful-dnd / `@hello-pangea/dnd`, react-dnd,
react-draggable, framer-motion `drag`, use-gesture) reads as the same gesture as native drag.

**Measuring the survey.** Its judgment is a model call, so the eval guards only the deterministic
triage; the judgment is *measured* by `tests/probe_absence_survey.py` against
`tests/fixtures/rubrick-omissions/` (a task list with planted omissions, each with a substitute, plus
decoys: defaults it has, an unfinished-looking gap, inapplicable features; key in `ANSWERS.json`,
outside `src/`). Recall is **twin-relative** — a labeled omission only counts when the twin actually
includes it, because the agent's defaults (not ours) decide what's a delta — and *baseline
independence* reports how many labeled defaults the twin includes at all. 2026-11-12, one cached
sample each: structure-built baseline 0/5 recall · jobs twin 1/1 (independence 1/5) · uncompressed
jobs twin 3/3 (independence 3/5), 0 errors throughout after the redesign; with need-rewrite + three
twins 2/2 (the default twin now serves "recover from a mistaken removal" with an undo toast, so the
product's refusal reads as `toast`), 0 errors, the unfinished hover surfaced at *low*.

**Measuring the gesture layer and stability.** `tests/probe_gestural.py` scores
`tests/fixtures/rubrick-gestural/` (a kanban board: drag-between-columns = the category default,
must go to review; a drag-to-scrub history track = the signature, must be captured; no mechanism
words may reach the twins). 2026-11-12: before — both components auto-captured on drag alone; after
— 2/2, 0 leaks, 3/3 twins serve history by click. `tests/probe_stability.py` recompiles each labeled
fixture after edits with no design meaning (a comment, a renamed local) and counts flipped
decisions: 2 flips before sticky jobs (every twin regenerated — majority voting couldn't help), 0
after, with one twin or three. (Stability came from sticky jobs; three twins guard against a single
generation's quirk deciding a capture, which this probe doesn't isolate.)

## What the detectors read (coverage)

All scanners consume **one shared discovery list** — `discover_components` in
[`src/rubrick/discover.py`](src/rubrick/discover.py): every `.tsx` under the components dir **plus**
`src/app`, `src/lib`, `src/styles` (and root-level `app`/`components`/`lib`), in deterministic
order, with **no truncation**. Identity living in a page (`src/app/foo/page.tsx`) is as observable
as identity in a component. Anything with a per-file LLM budget ranks by relevance first and caps
after — never `sorted(...)[:40]`, which silently drops files alphabetically. Compile and check use
the same list, which is part of why self-conformance is exact. If you add a scanner, consume this
list; don't glob a directory yourself.

## Deployment prevalence (the over-application channel)

*Where* a move is deployed is part of its identity: a source that reserves a crosshatched texture
or a colored glow for the focal object made a restraint decision, and a build that applies the same
move everywhere produces noise, not identity. Which moves get a frequency is decided by
**generated effect-locality metadata** ([`src/rubrick/scoping.py`](src/rubrick/scoping.py)):
element-local moves (a texture, a glow, a loop — more deployments = more effect) are scoped;
page-global postures (`full-bleed-canvas`, `information-dense` — one declaration shapes the whole
page) are not. Locality is a property of the *vocabulary word*, so the model classifies each word
once (globally cached, designer-overridable via `learned.json` `locality_overrides` — the same
generate-then-refine pattern as disposition rationales), and words promoted through the human loop
are classified **at promotion time**, so self-extended vocabulary is covered automatically. The
measurable universe is `MEASURABLE_MOVES` (every move with a per-file signature);
`measure_move_prevalence` runs those signatures **per file** and records the fraction of source
files carrying each — classification runs only on the compile path, while the check path measures
exactly the moves a system stored, so the gate stays deterministic. `material_prevalence`
(`extract_css.py`) does the same for rich material stacks.

Compile stores these on the records; the manifest emits them as **DEPLOYMENT** notes on the
checklist ("reserve it — ~8% of source files") plus a `_guide` principle; and `check_prevalence` /
the surface `spread` check gate a **clear** over-application (candidate beyond
`sys × _SPREAD_MULT + _SPREAD_PAD`, only when the system itself is reserved, `≤ _RESERVED_MAX`).
Both sides measure with the same signatures, so the source self-conforms exactly — this is the
symmetric **ceiling** to the magnitude **floors** in `check_metrics` (which only flag a build
*quieter* than the identity; this flags one *noisier*).

## Adding or auditing a signature — the discipline

A detector recognizes a **disposition**, not one product's construct. A signature calibrated on a
single product's specific code is a **false-negative waiting to happen** — it drops honest alternative
implementations of the same disposition. (Real example: `dynamic-density` was once just
`flex-grow + transition`, learned from one product's zoom canvas, and it failed an honest calendar
that carried the disposition five other ways.)

**Single-construct = suspect.** When you add or broaden a signature, verify it **four ways** — this
is the guard `eval_harness.py` enforces:

1. the **calibration product still matches** (self-conformance holds),
2. a **fresh build** that honestly carries the disposition **now matches** (the false-negative is gone),
3. **generic does NOT match** — stay discriminating; require strong signals, not bare responsiveness,
4. the **eval harness stays green** (elevation-above-generic preserved).

This rule is also documented inline at `_MOVE_SIGNATURES` in `facet_signatures.py` (kept in both
places on purpose). A signature that only fires on one construct, or that starts matching generic,
is the thing to fix.

> When a build agent honestly reports a stable conformance FAIL it can't clear without gaming the
> signature, suspect the **detector** (a false-negative) before the build — investigate the signature
> first, run the four-way check, and generalize it if it's overfit.

## Library-aware detection & the capability channel (anti-flatness)

Real React choreography is often declared through motion libraries, not CSS — and a detector
layer that only reads CSS compiles those products **flat**, so consuming agents build flat.
Two mechanisms close this:

**Library-aware signature branches.** `AnimatePresence` + an exit spec IS multi-phase; a
`variants` graph with distinct poses IS multi-phase; `staggerChildren`/GSAP `stagger:` IS
orchestrated-stagger; `type:"spring"`/`stiffness`/`bounce` IS spring-physics; `repeat: Infinity`
/`repeat: -1` IS an infinite loop; unitless `duration: 0.45` (framer/GSAP seconds, anime ms —
disambiguated by magnitude) feeds `detect_timings`. Every branch is a **pure addition** — an OR on
tokens CSS-built products don't contain — so systems compiled before these branches existed remain
exactly self-conformant, no recompile required. The richness ranker counts the same markers, so a
framer-heavy component ranks into the extraction budget like its CSS twin.

**The capability channel** (`capabilities.py`). The *library name* is implementation (posture mode
abstracts it, like fonts); the *capability class* the identity rides on is disposition-level fact:
physics-motion-runtime, timeline-choreography, vector-animation, 3d-scene, 2d-canvas-engine,
expressive-dataviz. Detection is deterministic (package.json deps × actual import specifiers on
the shared discovery list; a declared-never-imported dependency doesn't count, and generic-default
libraries aren't classes at all). Emission is two-tier, matching posture/native:
- **POSTURE — instructed, never gated**: `CAPABILITY/…` checklist lines + a
  `capability_requirements` guide block tell the agent the no-dependency approximation is wrong
  here; a build that hand-rolls the capability conforms via the treatment checks.
- **NATIVE — gated** (`check_native_capabilities`, reported as `native:capabilities`): the feature
  must ride the product's *actual* runtime per class — same logic as the typeface anchors.

## What the detectors *cannot* see (the honest ceiling)

Detectors read **declared** DOM/CSS, never the **rendered/animated** result. So craft execution —
motion smoothness (jank), colour harmony as seen, type-layout cleanliness, material glossiness,
WebGL — is **out of reach of any signature**. Rubrick handles that by *instructing* it (the `_guide`
block in the manifest) rather than gating it. Closing that loop would need a separate render+vision
layer, never folded into this deterministic gate.
