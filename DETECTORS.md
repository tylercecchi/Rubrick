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

The vocabulary is **open**: a compile can surface a novel move the vocab has no word for (a
"tear-escape"), which a designer promotes via the human loop (`learned.json`). See the README.

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
