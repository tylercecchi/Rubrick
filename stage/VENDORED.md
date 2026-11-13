# Vendored: Stageshow

`stage/stageshow/` is a copy of [Stageshow](https://github.com/benjitaylor/skills/tree/main/stageshow)
by Benji Taylor, MIT licensed (`stageshow/LICENSE`, `stageshow/NOTICE.md`), taken at commit
`299140fafd08df55a9c234e610c3f64af3f45531` (2026-11-04).

Rubrick uses it to draw its faux UI: the header bento's stills and each item's
"this product vs a typical build" drawing. Claude writes each scene against the kit, the
scene is filmed with Stageshow's own `scripts/film.mjs --gate`, and only scenes that pass
(or the best attempt, marked unrehearsed) are kept.

What was changed or left out:

- `kit/brands/` — **no brand artwork.** The SVG marks are not covered by the MIT license, so
  the registry is an empty stub (`kit/brands/index.ts`). Scenes draw the product's own UI and
  never another company's mark.
- `assets/app-icons.ts` — **not copied** (app artwork, not MIT). `examples/bento` still
  imports it; the examples here are reference material for the generator prompt, not built.
- `examples/` — only the gold examples the generator learns from.
- `teaching/` and `playground/` — not copied.

Everything else (`kit/`, `references/`, `scripts/`, `SKILL.md`) is unmodified. To update,
re-copy from upstream and re-apply the brands stub, then rebuild the runtime
(`stage/README.md`).
