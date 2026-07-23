"""Dynamic-value resolution — see through the indirection idiomatic code uses for values.

Metrics read literals (16px, #3b82f6, 400ms), but real products name their values: CSS custom
properties (`--space-4: 16px; padding: var(--space-4)`) and JS/TS constants (`const GAP = 16`).
A literal-only reader is blind to them — which is worst for the DISCIPLINE metrics, since a
token scale is the idiomatic expression of the very rigor they measure. This resolves both to
literals so spacing / color / timing metrics see the real values. Deterministic; same input →
same output.
"""

from __future__ import annotations

import re

_VAR_DECL = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}\n]+)")
_VAR_USE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,[^)]*)?\)")
# a numeric constant declaration — REQUIRES const/let/var so it never mistakes a CSS
# `property: value` (padding: 16) for a constant and clobbers the property name.
_NUM_CONST = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(-?\d+(?:\.\d+)?)(?:px|rem|em)?\b")


def _var_map(decls: str) -> dict:
    m: dict[str, str] = {}
    for name, val in _VAR_DECL.findall(decls):
        m.setdefault(name, val.strip())
    # resolve vars that reference other vars (a few shallow passes)
    for _ in range(3):
        changed = False
        for k, v in list(m.items()):
            nv = _VAR_USE.sub(lambda mt: m.get(mt.group(1), mt.group(0)), v)
            if nv != v:
                m[k], changed = nv, True
        if not changed:
            break
    return m


def resolve_values(source: str, decls: str = "") -> str:
    """Substitute `var(--x)` and numeric constants with their literal values. `decls` supplies
    custom-property declarations when they live outside `source` (e.g. a theme file)."""
    vmap = _var_map(source + "\n" + decls)
    out = _VAR_USE.sub(lambda mt: vmap.get(mt.group(1), mt.group(0)), source) if vmap else source
    cmap = {n: v for n, v in _NUM_CONST.findall(out)}
    if cmap:
        pat = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(cmap, key=len, reverse=True)) + r")\b")
        out = pat.sub(lambda mt: cmap.get(mt.group(1), mt.group(0)), out)
    return out
