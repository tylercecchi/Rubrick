"""Source discovery — the ONE choke point for what a compile or check reads.

Every scanner (behavior discovery, component capture, focal-surface search, density
metrics, raw_source for signatures) consumes the same file list, so coverage is defined
once: the components dir PLUS the app shell/pages and shared style/lib modules. A
component that lives in src/app/foo/page.tsx is as observable as one in src/components.

Two disciplines this module owns:
  - DETERMINISM: dir-major, sorted order — compile and a later check of the same source
    walk the identical list, which is what keeps self-conformance exact.
  - NO SILENT TRUNCATION: discovery returns everything it finds; any budget cap belongs
    to the caller AFTER relevance ranking (never `sorted(...)[:40]`, which drops files
    alphabetically — the old behavior that made a newly added ZoomPanel.tsx invisible).
"""

from __future__ import annotations

import pathlib

_SKIP_DIRS = {"node_modules", ".next", "dist", "build", ".git"}


def source_dirs(root: str, comps: str) -> list[str]:
    """Directories to scan for a product's real source. Beyond the components dir,
    identity lives in the app shell (src/app — layout/page composition, and pages that
    ARE components) and shared style/lib modules. Existing, de-duped, deterministic order
    (components dir first, so ties in downstream rankings keep preferring it)."""
    r = pathlib.Path(root)
    out, seen = [], set()
    for c in (comps, "src/app", "src/lib", "src/styles", "app", "components", "lib"):
        p = r / c
        if p.exists() and str(p) not in seen:
            seen.add(str(p))
            out.append(str(p))
    return out


def discover_components(repo: str, comps: str) -> list[str]:
    """Every .tsx source file across the product's source dirs — the shared discovery
    list behind compile AND check. Complete (no cap): the scanners that consume this are
    cheap regex/parse passes; anything with a per-file LLM budget ranks by relevance
    first and caps after, so nothing is dropped before it can be ranked."""
    out, seen = [], set()
    for d in source_dirs(repo, comps):
        for f in sorted(pathlib.Path(d).rglob("*.tsx")):
            if _SKIP_DIRS.intersection(f.parts):
                continue
            s = str(f)
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


# ── layout detection: find the stylesheet and components folder so nobody has to type them ──

_CSS_NAMES = {"globals.css": 3, "global.css": 3, "index.css": 2, "app.css": 2, "main.css": 1,
              "styles.css": 1, "style.css": 1, "tailwind.css": 2}
_COMPONENT_DIRS = ("src/components", "components", "app/components", "src/app/components",
                   "src/ui", "ui", "src/lib/components", "lib/components")


def _walk(r: pathlib.Path, pattern: str):
    for f in r.rglob(pattern):
        rel = f.relative_to(r).parts
        if _SKIP_DIRS.intersection(rel) or any(p.startswith(".") for p in rel[:-1]):
            continue
        if f.is_file():
            yield f


def detect_layout(repo: str) -> dict:
    """Best guess at a product's global stylesheet and components folder, so a product can
    be added by pointing at its folder alone. {globals_css, components_dir, found:{...}} —
    paths relative to the repo; found says which ones were actually located (a guess that
    wasn't found still works: every reader treats a missing path as 'nothing here')."""
    r = pathlib.Path(repo)
    best, best_score = None, 0.0
    for f in _walk(r, "*.css"):
        if f.name.endswith(".module.css"):
            continue
        try:
            head = f.read_text(errors="ignore")[:20000]
        except OSError:
            continue
        s = _CSS_NAMES.get(f.name, 0)
        s += 4 if ("@tailwind" in head or 'tailwindcss"' in head or "tailwindcss'" in head
                   or "@theme" in head) else 0
        s += 2 if ":root" in head else 0
        s += 1 if "font-family" in head or "--font" in head else 0
        s -= 0.2 * len(f.relative_to(r).parts)
        if s > best_score:
            best, best_score = f, s
    comps = next((c for c in _COMPONENT_DIRS if (r / c).is_dir()), None)
    if comps is None:  # no conventional folder: the shallowest dir holding the most .tsx/.jsx
        counts: dict[pathlib.Path, int] = {}
        for f in list(_walk(r, "*.tsx")) + list(_walk(r, "*.jsx")):
            counts[f.parent] = counts.get(f.parent, 0) + 1
        if counts:
            d = max(counts, key=lambda p: (counts[p], -len(p.parts)))
            comps = str(d.relative_to(r)) or "."
    return {"globals_css": str(best.relative_to(r)) if best else "src/app/globals.css",
            "components_dir": comps or "src/components",
            "found": {"globals_css": best is not None, "components_dir": comps is not None}}
