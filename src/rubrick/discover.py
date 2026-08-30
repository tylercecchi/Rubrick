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
