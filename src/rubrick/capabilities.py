"""Capability channel — the runtime classes a product's identity depends on.

The felt gap this closes: a consuming agent defaults to the least-dependency path (bare
CSS tweens for a framer-motion product, a div grid for a WebGL scene), and nothing in the
manifest ever said "this identity NEEDS a physics-motion runtime." The tech stack itself
is implementation (like fonts and hex values — posture mode rightly abstracts it), but
the CAPABILITY CLASS the identity rides on is a disposition-level fact:

  - POSTURE: capabilities are INSTRUCTED, never gated — the checklist/guide say "bring an
    equivalent runtime; CSS transitions alone cannot reproduce this," and a build that
    honestly hand-rolls the capability conforms via the treatment checks, not this list.
  - NATIVE: the concrete libraries gate like the typeface anchors — a feature meant to be
    indistinguishable from the product should use the product's actual libraries.

Detection is fully deterministic (package.json deps + import specifiers across the shared
discovery list), and a library only counts when it is actually IMPORTED by observed
source — a dependency rotting in package.json is not identity. The class map is small and
identity-biased on purpose: generic-default libraries (a stock chart kit, a UI kit) are
NOT capabilities; per the thesis, only what a competent generic build would NOT reach for
belongs in the system.
"""

from __future__ import annotations

import json
import pathlib
import re

# capability class -> {library specifier prefixes}. Matched against BOTH package.json
# dependency names and import specifiers ("@react-three/fiber" matches prefix
# "@react-three/"). Kept identity-biased: see the module docstring.
CAPABILITY_LIBRARIES = {
    "physics-motion-runtime": {"framer-motion", "motion", "react-spring", "@react-spring/",
                               "@use-gesture/", "popmotion", "react-use-gesture"},
    "timeline-choreography": {"gsap", "animejs", "@gsap/"},
    "vector-animation": {"lottie-web", "lottie-react", "react-lottie", "@rive-app/",
                         "@lottiefiles/"},
    "3d-scene": {"three", "@react-three/", "babylonjs", "@babylonjs/", "ogl", "regl"},
    "2d-canvas-engine": {"pixi.js", "@pixi/", "konva", "react-konva", "p5", "fabric",
                         "paper", "two.js"},
    "expressive-dataviz": {"d3", "d3-", "@visx/", "visx", "echarts"},
}

CAPABILITY_INSTRUCTIONS = {
    "physics-motion-runtime": ("motion here is PHYSICS-DRIVEN (springs, momentum, gesture-"
                               "coupled values), not tween-driven — bring a real motion runtime "
                               "or an equivalent; bare CSS transitions will read flat"),
    "timeline-choreography": ("motion is TIMELINE-CHOREOGRAPHED (sequenced, overlapping tweens) "
                              "— bring a timeline-capable runtime or equivalent sequencing; "
                              "isolated one-shot transitions will read flat"),
    "vector-animation": ("identity motion is authored VECTOR ANIMATION (Lottie/Rive-class) — "
                         "static icons or CSS approximations will read flat"),
    "3d-scene": ("the focal surface is a REAL-TIME 3D SCENE — a styled div cannot stand in "
                 "for it; bring a 3D runtime"),
    "2d-canvas-engine": ("the focal surface is a programmatic 2D CANVAS — DOM elements alone "
                         "cannot reproduce its rendering"),
    "expressive-dataviz": ("data graphics are CUSTOM-BUILT (d3-class), not a stock chart kit — "
                           "identity lives in the bespoke encoding"),
}

_IMPORT = re.compile(r"""(?:import\s[^;'"]*?from\s*|import\s*\(\s*|require\s*\(\s*)['"]([^'"]+)['"]""")


def _lib_matches(spec: str, prefixes: set[str]) -> str | None:
    """The matched library name, or None. A prefix ending in '/' or '-' matches a
    namespace; otherwise the spec must BE the package (or a subpath of it) — 'motion'
    must not match 'motion-blur-utils'."""
    for p in prefixes:
        if p.endswith(("/", "-")):
            if spec.startswith(p):
                return p.rstrip("/-")
        elif spec == p or spec.startswith(p + "/"):
            return p
    return None


def detect_capabilities(repo: str, comps: str) -> list[dict]:
    """The capability classes this product's observed source depends on — deterministic.
    A library counts only if it is (a) declared in package.json AND (b) imported somewhere
    on the shared discovery list; import evidence alone also counts (monorepos hoist deps),
    but a declared-never-imported dependency does not."""
    from rubrick.discover import discover_components
    declared: set[str] = set()
    pj = pathlib.Path(repo) / "package.json"
    if pj.exists():
        try:
            d = json.loads(pj.read_text())
            declared = set(d.get("dependencies", {})) | set(d.get("devDependencies", {}))
        except Exception:
            pass
    imported: set[str] = set()
    files_by_spec: dict[str, int] = {}
    for f in discover_components(repo, comps):
        try:
            text = pathlib.Path(f).read_text()
        except Exception:
            continue
        specs = {s for s in _IMPORT.findall(text) if not s.startswith((".", "@/", "~"))}
        imported |= specs
        for s in specs:
            files_by_spec[s] = files_by_spec.get(s, 0) + 1
    out = []
    for cls, prefixes in sorted(CAPABILITY_LIBRARIES.items()):
        libs: dict[str, int] = {}
        for spec in sorted(imported):
            lib = _lib_matches(spec, prefixes)
            if lib:
                libs[lib] = libs.get(lib, 0) + files_by_spec.get(spec, 0)
        if libs:
            out.append({"class": cls, "libraries": sorted(libs),
                        "evidence": f"imported in {sum(libs.values())} source file(s)"
                                    + ("" if not declared or (set(libs) & declared) or any(
                                        _lib_matches(d, prefixes) for d in declared)
                                       else " (not in package.json — hoisted?)")})
    return out


def check_native_capabilities(system_caps: list[dict], candidate_caps: list[dict]) -> list[str]:
    """NATIVE gate: the candidate must reuse the product's actual runtime per capability
    class — same logic as the typeface anchors. Posture mode never calls this."""
    cand = {c["class"]: set(c["libraries"]) for c in candidate_caps}
    v = []
    for sc in system_caps:
        want = set(sc["libraries"])
        have = cand.get(sc["class"], set())
        if not (want & have):
            v.append(f"capability/{sc['class']}: the product builds this on {sorted(want)} but "
                     f"the feature {'uses ' + str(sorted(have)) if have else 'imports none of it'}"
                     f" — a native feature should ride the product's actual runtime, not a "
                     f"parallel one")
    return v
