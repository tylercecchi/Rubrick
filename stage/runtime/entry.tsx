// Rubrick's faux-UI runtime: React + the vendored Stageshow kit + a JSX transform, so a
// scene Claude writes (JSX source, no imports) can be mounted in a sandboxed frame.
import * as React from 'react'
import { createRoot } from 'react-dom/client'
import { transform } from 'sucrase'
import * as Kit from '../stageshow/kit'

type Scene = { code: string; css?: string; tokens?: Record<string, string> }

// Kit components and helpers a scene may use by name (values only; types are erased).
const SCOPE: Record<string, unknown> = { React, ...Kit }
for (const k of ['useState', 'useEffect', 'useRef', 'useMemo', 'useCallback', 'useLayoutEffect', 'Fragment'])
  SCOPE[k] = (React as any)[k]

export function compile(code: string): React.ComponentType {
  const js = transform(code, { transforms: ['jsx', 'typescript'], production: true }).code
  const names = Object.keys(SCOPE)
  // eslint-disable-next-line no-new-func
  const make = new Function(...names, `"use strict";\n${js}\nreturn typeof Scene !== "undefined" ? Scene : undefined;`)
  const C = make(...names.map((n) => SCOPE[n]))
  if (typeof C !== 'function') throw new Error('the scene must define function Scene()')
  return C
}

class Boundary extends React.Component<{ children: React.ReactNode }, { error: string | null }> {
  state = { error: null as string | null }
  static getDerivedStateFromError(e: unknown) { return { error: String((e as Error)?.message || e) } }
  componentDidCatch(e: unknown) { report(String((e as Error)?.message || e)) }
  render() { return this.state.error ? null : this.props.children }
}

function report(error: string) {
  console.error('scene error: ' + error)
  ;(window as any).__rubrickSceneError = error
  document.documentElement.setAttribute('data-scene-error', error.slice(0, 300))
  try { parent.postMessage({ rubrickScene: 'error', error }, '*') } catch {}
}

export function mount(el: HTMLElement, scene: Scene) {
  try {
    if (scene.tokens) for (const [k, v] of Object.entries(scene.tokens)) document.documentElement.style.setProperty(`--p-${k}`, v)
    if (scene.css) { const s = document.createElement('style'); s.textContent = scene.css; document.head.appendChild(s) }
    const C = compile(scene.code)
    createRoot(el).render(<Boundary><C /></Boundary>)
    document.documentElement.setAttribute('data-scene', 'mounted')
    try { parent.postMessage({ rubrickScene: 'mounted' }, '*') } catch {}
  } catch (e) {
    report(String((e as Error)?.message || e))
  }
}

export const kitNames = Object.keys(SCOPE)
;(window as any).RubrickStage = { mount, compile, kitNames }
