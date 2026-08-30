# Rubrick

**A product-system compiler.** Rubrick reads a designed product from its source and
codifies its _product system_ — the taste, dispositions, and structural moves that make it
feel like one mind — into a runnable schematic that a coding agent can build new products
against and validate conformance to.

> A **product system**, not a design system. A design system is a component library plus
> tokens. A product system is the _decisions and dispositions_ that would let you design a
> new component that still belongs. Rubrick captures the second, never the first — it emits
> identity **postures** ("a distinctive display face as the product's voice"), not token
> values ("use RuderPlakat, #7a1e2b, 16px").

## The thesis

> **A product system is the intent-filtered diff between a product and the consumer agent's
> own defaults.**

A coding agent already knows generic-good design. So the only thing worth capturing is the
**delta from generic** — what a competent-but-anonymous build would _not_ do by default.
Rubrick makes that concrete: it asks the same class of agent that will _consume_ the system
to generate the generic default, diffs the real product against it, and keeps the
intent-filtered difference.

Status: the **engine** is validated across multiple independent products plus a native A/B — the
same app built to two different systems produced opposite souls. Nothing left is research risk; the
remaining work is packaging + docs.

---

## The loop

Candidates are expressed in the **same structural types used to observe**, so the thing that
reads a product and the thing that validates a new one speak one vocabulary.

```
OBSERVE ─▶ SALIENCE ─▶ ELICIT ─▶ LIFT ─▶ COMPILE ─▶ GENERATE · CHECK
```

1. **Observe** — read materials, behavior, and style from repo source.
2. **Baseline** — the consumer agent generates the generic default for the same role/moment.
3. **Salience** — diff (Axis A) × intent (Axis B) → `CAPTURE` / `ELICIT` / `DISCARD`.
4. **Elicit** — a human resolves only the uncertain, high-leverage cases; answers compound.
5. **Lift** — the captured delta _becomes_ the requirement, hung off a disposition.
6. **Compile** — `product_system.py`: a library + validator + blueprint.
7. **Generate · check** — build a new product to the system; validate its conformance.

---

## Core concepts

- **Two-channel discipline.** The _structural_ channel (an element's role, an interaction's
  moment) is inferred from **structure only** — placement, repetition, containment, triggers.
  The _surface_ channel (its material, its treatment) is diffed separately. Keeping them
  independent is what stops role/moment inference from being circular with the salience diff.

- **Delta-from-generic via a generated baseline.** "Special" is defined _relative to the
  consumer agent's own priors_ — it generates the default, and the diff is self-calibrating.
  If the agent would build it that way anyway, there's nothing to capture.

- **Salience = diff × intent.** Axis A is the structural delta; Axis B is intent. For
  behavior, intent splits into **deliberateness** (effort · specificity · coherence — "authored
  on purpose?") and **systematicity** (recurrence — "a system pattern or a one-off?").

- **Dispositions are operative, not decorative.** A disposition is the calibrated "why"
  (e.g. _"ceremony scales with how disorienting the reorientation is"_). It drives what
  `generate()` derives and what `check()` validates — quantitatively, not just by presence.

- **Self-extension.** The model **won't volunteer `"other"`** for novel things — it force-fits
  at low confidence. So a **tear** = low confidence _or_ **conflation** (two elements forced
  into one bucket despite different structure). A designer **promotes** the tear and the
  vocabulary grows — which requires open `str` types, not closed `Literal`s, on both the
  prompt _and_ the output schema. Dimensions without a promotable vocab get a **tear-escape**
  (`novel_features`) so novelty is captured, never silently dropped.

- **The gate self-extends too (seen → instructed → gated).** Observation is open — novelty
  surveys read every product with no fixed list, so an interaction pattern or move no detector
  anticipates still surfaces as a tear. Verification is closed — only deterministic detectors
  gate. Promotion bridges them: the model *proposes* a detector for the promoted word (a
  declarative regex spec stored in `learned.json`, not code), and it only starts gating after
  mechanically proving it matches the product it was seen in and does **not** match a generic
  build. Until then the word is instructed in the checklist but unverified. The hand-written
  signatures are the seed corpus, not the ceiling.

- **Deployment frequency is part of the delta.** *Where* a move is deployed is itself identity: a
  product that reserves its metal texture for the focal object made a restraint decision.
  Element-local moves (textures, glows, loops, display type — classified by generated
  effect-locality metadata, not a curated list, so promoted vocabulary is covered too) carry their
  observed frequency; the checklist says "reserve it" with the rate, and the gate flags clear
  over-application — the symmetric ceiling to the magnitude floors. A build that applies every
  captured move everywhere reads as noise, not identity, and now fails for it.

- **Interaction patterns are captured structurally.** Beyond choreography (timings, phases,
  symmetry), the tool detects what an interaction *is* — a carousel's sequential traversal,
  progressive disclosure, pointer drawing on a canvas, select-one-spotlight-the-rest — as
  deterministic signatures on component roles. A quiet-but-distinctive pattern is identity even
  with no animation, and a conforming build must carry the pattern somewhere in its focal group.

- **Human-assist: confidence is the scheduler.** The tool asks only where it's genuinely
  unsure _and_ the human is the only source, ranked by leverage. Every answer lands in
  `learned.json` as reusable structure, so confidence compounds — and it's **global**: rules
  learned on one product help on the next.

- **Disposition clustering (vertical abstraction).** Many manifestations → one prior. This
  lets recurrence be measured at the disposition level (where distinct treatments share a
  prior _without_ sharing literal features), scoped **within-product**.

---

## The four modalities

| Modality | Structural channel | Surface channel | Record |
|---|---|---|---|
| **Material** | role | layer stack (sheen/lighting/texture/bevel…) | `SurfaceRecord` |
| **Behavior** | moment + qualifiers | treatment features | `RuleRecord` |
| **Static style** | facet (typography/color/density) | identity moves | `StyleRecord` |
| **Ambient motion** | facet (ambient) | perpetual-loop qualities | `StyleRecord` |

All four run the full loop. `generate()` emits a conforming instance; `check(candidate)`
returns violations. For style/ambient, `generate()` emits the identity **posture**
(feature-agnostic) — a new product reproduces the posture with its own fonts/colors.

---

## Module map

The **shipped core modules** are the `rubrick` package under [`src/rubrick/`](./src/rubrick/); the
regression guard is `eval_harness.py` in the repo root. Key entry points:

- **`rubrick_mcp.py`** — the MCP server (the interface + `main()` for `rubrick-mcp`).
- **`orchestrate.py`** — the compile pipeline (observe → salience → lift → calibrate).
- **`conform.py`** — the verified gate (re-observe candidate → violations).
- **`product_system.py`** — the emitted artifact (`Disposition` / records / `check` / `check_native`
  / `emit_manifest` with `_checklist` + `_guide`).
- **`facet_signatures.py`** — deterministic facet detectors + `capture_face_roles`.
- **Extraction:** `type_extract`, `style_facets`, `extract_css`, `extract_behavior`,
  `detect_treatments`, `ambient_extract`, `components`, `subtractions`, `infer_composition`,
  `infer_moment`, `resolve`, `tailwind`, `material`.
- **`learned.py`** — the human-loop store (global, compounding); `review.py` is the review→apply surface.

---

## Requirements & what it works on

- **React (`.tsx`)** — Next.js or Vite/CRA (paths are configurable). Vue / Svelte / Angular are out
  of scope for now.
- **A styling source Rubrick can read** — plain **CSS files**, **inline style objects**
  (`style={{…}}`), or **Tailwind** (the `tailwind.config` theme + utility classes). No particular one
  is required; Tailwind is supported but optional (a graceful no-op if you don't use it).
- **Inputs** — a globals CSS file and a components directory. Defaults are `src/app/globals.css` and
  `src/components`; pass `globals_css` / `components_dir` if yours differ. Coverage goes beyond the
  components dir: every scanner reads one shared discovery list — the components dir **plus**
  `src/app`, `src/lib`, and `src/styles` — so identity living in a page or shared module is observed
  too, and a recompile after new pages/components are added can't silently miss them (the compile
  log's `coverage:` line shows exactly what was read).

### Best practices — for a richer system
- **Point it at a product with real identity.** Rubrick captures the *delta from generic* — a plain
  scaffold yields almost nothing (that's correct, not a bug). The more a product genuinely departs
  from the baseline, the more there is to capture.
- **Declare your typefaces** (`@font-face` or `next/font`) if you want native mode to reuse the actual faces.
- **Give it composed, identity-bearing components** — that's where the surface, behavior, and
  composition records come from, not just the style facets.
- **Review what it captured.** Compile is the design step: read the checklist, sharpen the *why*
  behind each move, and promote any novel ones. Judgment lives with you, not the agent.

### What it can't see
Rubrick reads *declared* DOM/CSS, not the rendered result — so runtime-only qualities (WebGL scenes,
motion smoothness, pixel-level craft) are out of reach. It **instructs** those in the manifest's
`_guide` rather than verifying them.

---

## Getting started

Rubrick ships as an **MCP server** — coding agents pull a product system and self-check against
it over the Model Context Protocol.

### 1. Install

**To use it** — install straight from GitHub, no clone needed:

```bash
pip install git+https://github.com/tylercecchi/rubrick.git
```

**To develop it** — clone and install editable (source stays linked, so edits take effect live):

```bash
git clone https://github.com/tylercecchi/rubrick.git
cd rubrick
python3 -m venv .venv
./.venv/bin/pip install -e .        # installs deps + the `rubrick-mcp` launcher
```

Either way you get the `rubrick-mcp` command. Set your Anthropic key via any of: the
`ANTHROPIC_API_KEY` env var, a `RUBRICK_ENV_FILE` path, or a project `.env.local` / `.env`
(see `.env.example`).

### 2. Register the MCP server with a client

Point your MCP client (Claude Code / Desktop) at the `rubrick-mcp` command:

```json
{
  "mcpServers": {
    "rubrick": {
      "command": "rubrick-mcp",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "RUBRICK_HOME": "/path/to/your/rubrick-data"
      }
    }
  }
}
```

**`RUBRICK_HOME`** is Rubrick's data root — where `systems/`, `learned.json`, and `.cache/` live.
It defaults to the current working directory, but the MCP server's cwd is client-controlled, so
set it explicitly to the directory that holds your compiled systems. Tools exposed:
`list_product_systems`, `get_product_system`, `check_conformance`, `compile_product_system`,
`apply_review`, `list_learned`.
_After any code change, restart the server — it's a stdio subprocess that caches modules._

### 3. Compile a product system (one-off, slow — many model calls)

```
compile_product_system(repo="/path/to/DesignedProduct", name="MyProduct",
                       globals_css="src/app/globals.css", components_dir="src/components")
```

Compiling observes the product and writes `systems/MyProduct.json`. Afterwards
`get_product_system` / `check_conformance` are fast. (Compile surfaces novel moves for optional
designer review → `apply_review`; see `learned.json`.)

**Sample prompt** (paste to a coding agent with the Rubrick MCP server registered):

> Using the Rubrick MCP server, compile a product system from the designed product at
> `/path/to/DesignedProduct` — call `compile_product_system` with `name="MyProduct"`,
> `globals_css="src/app/globals.css"`, `components_dir="src/components"`. It's slow (many model
> calls); run it once. When it finishes, show me the `_checklist` and the dispositions so I can see
> what identity it captured. If it returns a `_review` (novel moves with no vocabulary word yet),
> list them so I can decide which to promote via `apply_review`.

### 4. Consume it (the build loop)

An agent calls `get_product_system("MyProduct")` and reads the `_checklist` (every requirement,
each with a **WHY**) + the `_guide` (build order, the craft the gate can't verify, how to read
the gate). It builds, then calls `check_conformance("MyProduct", <repo>)` and resolves the
violations until conformant.

- **Posture** (default) — reproduce the product's dispositions with **your own** fonts/colors/
  content. For building a *new product* that shares the soul.
- **Native** (`check_conformance(..., native=True)`) — reuse the product's **actual** faces and
  palette. For a *new feature that looks native* to the product.

**Sample prompt** (paste to a coding agent with the Rubrick MCP server registered):

> Build a settings page using the **MyProduct** product system from the Rubrick MCP server.
> First call `get_product_system("MyProduct")` and read its `_checklist` — every requirement, each
> with a **WHY** — and its `_guide` (build order, the craft the gate can't verify, and how to read
> the gate). Build to the WHY, not just to pass the checks. Reproduce the identity with your **own**
> fonts, colors, and content (this is POSTURE).
>
> Then call `check_conformance("MyProduct", "<this repo path>")`, read the `_formatted` report,
> resolve every FAIL, and re-check until none remain. Conformance is the floor, not the finish — also
> make the motion smooth, the palette harmonious, and the type layout clean (the gate can't check
> those; you own them). Show me the report before and after.
>
> _For a **native** feature instead — one that must look like it already ships inside MyProduct —
> add: "Reuse MyProduct's actual faces and palette from the `concrete` anchors, and call
> `check_conformance(..., native=True)`."_

---

## Development

The regression guard is **`eval_harness.py`** in the repo root — fully self-contained (it observes
the vendored `tests/fixtures/` products and depends on nothing external). It's not part of the
shipped package. LLM calls cache under `.cache/` (gitignored).

```bash
./.venv/bin/python eval_harness.py    # the regression guard (self-contained)
```

---

## Also in this repo

- [`DETECTORS.md`](./DETECTORS.md) — how the detection layer works (deterministic vs LLM; adding a signature).
- The published **system-map** artifact (`rubrick-system.html`) — a visual architecture +
  validation overview.
