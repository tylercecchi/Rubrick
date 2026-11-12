# tests/fixtures/ — vendored eval fixtures

Synthetic source products the regression guard (`eval_harness.py`) observes. They are **vendored
here so the guard is fully self-contained** — it reaches into no external directory, so nothing can
be deleted out from under it. They span the differentiation spectrum:

- **`rubrick-beacon/`** — a synthetic RICH product (a fictional "live-signals console"): expressive
  type, entity/status color, dense floating layout, ambient life, dramatic elevation, a lit focal
  object, multi-phase interactions, and a central-canvas spine. The **EXPRESSION end** — it exercises
  *every* record family (styles×5 + surface + behavior + composition + components + native), so a
  regression in any structural detector is caught. (Replaced the external real-product copies the
  guard used to depend on, so it needs nothing outside the repo.) Its sweep-history scrubber lives
  in `src/app/page.tsx` **on purpose** — outside the components dir — so the guard also catches any
  regression to components-dir-only scanning (the shared-discovery coverage contract).
- **`rubrick-restrained/`** — a clean, disciplined (Linear-ish) product whose identity is
  *systematicity*, not loud differentiation. The **discipline-axis fixture**: self-conforms, elevates
  above generic, and yields a *meaningful* system (~7 records > generic's 1) — proving a restrained
  product isn't mistaken for generic.
- **`rubrick-generic/`** — a deliberately ad-hoc, low-identity build. The **elevation floor**: it
  scores ~0% against every product's system, proving captured identity is *differentiated from
  generic*, not universal noise. ~1 record.

- **`rubrick-omissions/`** — a small task list with **planted deliberate omissions** (confirm
  dialogs, icons, count badges, toasts, spinners — each with a visible substitute) and **decoys** (defaults
  it does have, an unfinished-looking hover token, features with nothing to host them). The answer key
  is `ANSWERS.json`, outside `src/` so discovery never reads it; the source carries no intent
  comments. Not in the regression guard — it *measures* the open absence survey via
  `tests/probe_absence_survey.py`.

- **`rubrick-gestural/`** — a kanban board whose drag-between-columns is the **category default**
  (must go to review, not be auto-captured) and whose drag-to-scrub history track is the **signature
  gesture** (must be captured); its jobs are phrased so a mechanism could leak into the twin. Key in
  `ANSWERS.json`; measured by `tests/probe_gestural.py`. Both labeled fixtures also feed
  `tests/probe_stability.py` (decision flips under edits with no design meaning).

They're small and are **read, never built**. See `DETECTORS.md` for what the detectors capture.
