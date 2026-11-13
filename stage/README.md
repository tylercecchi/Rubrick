# stage/ — Rubrick's faux-UI toolchain

- The vendored Stageshow kit, skill docs, gold examples and film tools live inside the
  package at `src/rubrick/stageshow/` (MIT; see `VENDORED.md` there), so an installed
  Rubrick has them too.
- `runtime/` — builds `src/rubrick/ui/stage/runtime.{js,css}`: React, the kit and a JSX
  transform in one browser bundle, so a scene Claude writes can mount without a build step.
  The built files are committed; Node is only needed to rebuild them.
- Filming doesn't need this folder: on the first rehearsal Rubrick sets up its own filming
  folder (`~/.rubrick/film`) with Stageshow's film scripts and `playwright-core`.

```sh
cd stage && npm install && npm run build   # only to rebuild the runtime
```
