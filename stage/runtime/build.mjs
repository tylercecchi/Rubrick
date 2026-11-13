// Bundles runtime/entry.tsx into src/rubrick/ui/stage/runtime.{js,css} (shipped with the
// package; Node is only needed to rebuild). Run: cd stage && npm install && npm run build
import { build } from 'esbuild'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
const here = path.dirname(fileURLToPath(import.meta.url))
const out = path.resolve(here, '../../src/rubrick/ui/stage')
await build({
  entryPoints: { runtime: path.join(here, 'entry.tsx') },
  bundle: true, minify: true, format: 'iife', target: 'es2020', outdir: out,
  jsx: 'automatic', loader: { '.svg': 'dataurl' },
  define: { 'process.env.NODE_ENV': '"production"' },
  legalComments: 'eof', logLevel: 'info',
})
console.log('built', out)
