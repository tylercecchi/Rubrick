# stage/ — Rubrick's faux-UI toolchain

- `stageshow/` — the vendored Stageshow kit, skill docs, gold examples and film tools
  (MIT; see `VENDORED.md` for what was left out).
- `runtime/` — builds `src/rubrick/ui/stage/runtime.{js,css}`: React, the kit and a JSX
  transform in one browser bundle, so a scene Claude writes can mount without a build step.
  The built files are committed; Node is only needed to rebuild them.
- `npm install` here also installs `playwright-core`, which `scenes.py` uses (through
  `stageshow/scripts/film.mjs --gate`) to rehearse every scene in headless Chrome.

```sh
cd stage && npm install && npm run build
```
