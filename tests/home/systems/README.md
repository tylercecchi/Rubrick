# tests/home/systems/ — the eval's fixture systems

These `*.json` files are **compiled product systems** — the output of `compile_product_system(...)`.
They are **eval fixtures, NOT part of the distributed package**, and not anyone's working data.

- **The installed package ships none of these.** `pyproject.toml` ships only the `rubrick` package
  (`src/rubrick/`), so a built wheel carries no `systems/` — a user of Rubrick compiles **their own**
  product's system into their own data folder (`~/Rubrick` by default).
- **Why they're here:** `tests/home/` is the eval's own data folder (`RUBRICK_HOME` for the eval
  and the probes): these systems, a clean `learned.json`, and the model-call `.cache/` (untracked).
- **Why they're committed:** `eval_harness.py` (the regression guard) needs them as fixtures —
  `Beacon` (a synthetic RICH product, the *expression* end of the spectrum), `Restrained` (the
  *discipline* end), and `Generic` (the *floor*). Committing them lets the eval run on a fresh
  checkout without recompiling.
- **Provenance:** all three are compiled from the synthetic fixture products vendored in
  [`tests/fixtures/`](../../fixtures/), so the guard is fully self-contained — it depends on no
  external product copy.

To (re)compile one: `compile_product_system(<repo>, <name>, <globals_css>, <components_dir>)` via the
MCP tool, or the orchestrator directly. See the repo README for the workflow.
