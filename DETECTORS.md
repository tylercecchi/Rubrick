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
| **behavior** treatments + timings | deterministic | `detect_treatments`, `detect_timings` |
| **interaction patterns** (carousel, staged disclosure, pointer drawing, spotlight) | deterministic | `components.detect_patterns` |
| **effect locality** (which moves get a deployment frequency) | **LLM** (generated once per vocab word, cached, designer-overridable) | `scoping.move_locality` |
| **surface** material stack (sheen/lighting/texture/bevel) | deterministic | `extract_focal_surface` |
| **magnitude** metrics (scale-contrast, weight, chroma, shadow depth, spacing, content-density) | deterministic (regex) | `type_extract`, `style_facets` |
| **discipline** metrics (`spacing_discipline`, `palette_coherence`) | deterministic | `style_facets` |
| **subtractions** (identity by omission) | deterministic | `detect_subtractions` |
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

## What the detectors *cannot* see (the honest ceiling)

Detectors read **declared** DOM/CSS, never the **rendered/animated** result. So craft execution —
motion smoothness (jank), colour harmony as seen, type-layout cleanliness, material glossiness,
WebGL — is **out of reach of any signature**. Rubrick handles that by *instructing* it (the `_guide`
block in the manifest) rather than gating it. Closing that loop would need a separate render+vision
layer, never folded into this deterministic gate.
