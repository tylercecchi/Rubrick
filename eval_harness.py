"""Eval harness — the trust layer. Run: python eval_harness.py

Guards the "LLM grades LLM" concern. Self-conformance proves CONSISTENCY (same source →
same read), not CORRECTNESS. Correctness proxy, no human labels needed:

  - ELEVATION ABOVE GENERIC (the real correctness test): a deliberately-generic build must
    sit well BELOW each product on that product's own system. The identity moves are
    differentiated from the GENERIC floor, not from other products.
  - SPECTRUM: the tool makes a MEANINGFUL system across the differentiation range — generic
    stays thin, restrained gets a real system via the discipline axis.
  - CROSS-PRODUCT is an informational OVERLAP MAP, NOT a discrimination target. Products
    SHARE facets and that's expected; identity = differentiation-from-generic.

Assertions (the regression guard): every product self-conforms; every product sits well
above generic on its own system; restrained yields a non-empty system; generic stays thin.
"""

from __future__ import annotations

import pathlib

from rubrick.conform import check_conformance
from rubrick.orchestrate import compile_product_system
from rubrick.product_system import load_product_system, save_product_system

_SYS = pathlib.Path(__file__).parent / "systems"
_FIX = pathlib.Path(__file__).parent / "tests" / "fixtures"  # vendored fixtures
_COMPS = "src/components"

# (repo, globals-css) across the differentiation spectrum — ALL vendored under tests/fixtures/, so
# the guard is FULLY SELF-CONTAINED (no external dependency, nothing to delete out from under it):
#   Beacon      = a synthetic RICH product — the EXPRESSION end. Exercises every record family
#                 (styles×5 + surface + behavior + composition + components + native), so a
#                 regression in any structural detector is caught. (Replaces the old real-product fixtures.)
#   Restrained  = the DISCIPLINE end (identity via systematicity).
#   Generic     = the FLOOR (should score ~0 against the others).
PRODUCTS = {
    "Beacon":     (str(_FIX / "rubrick-beacon"), "src/app/globals.css"),
    "Restrained": (str(_FIX / "rubrick-restrained"), "src/app/globals.css"),
    "Generic":    (str(_FIX / "rubrick-generic"), "src/app/globals.css"),
}


def ensure_system(name: str):
    p = _SYS / f"{name}.json"
    if not p.exists():
        repo, gcss = PRODUCTS[name]
        save_product_system(compile_product_system(repo, gcss, _COMPS, [], name), str(p))
    return load_product_system(str(p))


def _rate(candidate: str, gcss: str, ps, key: str) -> float:
    r = check_conformance(candidate, gcss, _COMPS, key, ps, native=False)
    s = r["_summary"]
    return s["conforming"] / s["records_checked"] if s["records_checked"] else 0.0


def _record_count(ps) -> int:
    return (len(ps.styles) + len(ps.surfaces) + len(ps.rules) + (1 if ps.composition else 0)
            + len(ps.components) + len(ps.subtractions))


def _detector_mechanics_ok() -> bool:
    """Deterministic guard on the self-extension mechanics: a well-formed spec that
    matches Beacon is admitted; a loose spec is rejected by the generic floor — and the
    EMBEDDED floor must agree with the real vendored Generic fixture (kept in sync)."""
    from rubrick.detectors import admit, run_spec
    from rubrick.facet_signatures import raw_source
    beacon = raw_source(*PRODUCTS["Beacon"], _COMPS)
    generic = raw_source(*PRODUCTS["Generic"], _COMPS)
    tight = {"all": [r"conic-gradient", r"sweep"], "none": []}
    loose = {"all": [r"padding"], "none": []}
    return (admit(tight, beacon) is None
            and "generic floor" in (admit(loose, beacon) or "")
            and run_spec(loose, generic)          # embedded floor agrees with the fixture
            and "calibration" in (admit({"all": [r"never-in-beacon-xyz"]}, beacon) or ""))


def _learned_pickup_ok() -> bool:
    """An ACTIVE learned detector extends detect_patterns deterministically; a rejected
    one never gates. Runs against a temp learned store (the real learned.json untouched)."""
    import pathlib as _pl
    import tempfile
    from rubrick import detectors, learned
    from rubrick.components import detect_patterns
    src = 'onScroll={(e) => { other.current.scrollTop = e.currentTarget.scrollTop }}'
    spec = {"all": [r"onScroll", r"scrollTop\s*="], "none": []}
    orig = learned._F
    learned._F = _pl.Path(tempfile.mkdtemp()) / "learned.json"
    detectors._memo["mtime"] = "stale"
    try:
        before = "sync-scroll" not in detect_patterns(src)
        detectors.record_detector("pattern", "sync-scroll", spec, "active", "eval")
        active = "sync-scroll" in detect_patterns(src) and "sync-scroll" not in detect_patterns("plain")
        detectors.record_detector("pattern", "rejected-one", None, "rejected", "eval", reason="x")
        rejected = "rejected-one" not in detect_patterns(src)
        return before and active and rejected
    finally:
        learned._F = orig
        detectors._memo["mtime"] = "stale"


def run() -> bool:
    systems = {n: ensure_system(n) for n in PRODUCTS}
    ok = True

    print("=== SELF-CONFORMANCE (consistency) ===")
    self_rate = {}
    for n in ("Beacon", "Restrained"):
        repo, gcss = PRODUCTS[n]
        self_rate[n] = _rate(repo, gcss, systems[n], f"eval:{n}:self")
        print(f"  {n:12} {self_rate[n]:.0%}")

    print("\n=== ELEVATION ABOVE GENERIC (correctness: generic must sit BELOW products) ===")
    grepo, ggcss = PRODUCTS["Generic"]
    elevation = {}
    for n in ("Beacon", "Restrained"):
        g = _rate(grepo, ggcss, systems[n], f"eval:generic:{n}")
        elevation[n] = self_rate[n] - g
        print(f"  generic vs {n:12} {g:.0%}   (product {self_rate[n]:.0%} → elevation {elevation[n]:+.0%})")

    print("\n=== SYSTEM RICHNESS across the spectrum ===")
    for n in ("Beacon", "Restrained", "Generic"):
        ps = systems[n]
        facets = [s.facet for s in ps.styles]
        print(f"  {n:12} {_record_count(ps)} records  · styles={facets}"
              f" · composition={'yes' if ps.composition else 'no'}")

    print("\n=== ASSERTIONS (regression guard) ===")
    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    for n in ("Beacon", "Restrained"):
        check(f"{n} self-conforms ≥85% ({self_rate[n]:.0%})", self_rate[n] >= 0.85)
    for n in ("Beacon", "Restrained"):
        check(f"{n} sits ≥30pts above generic (elevation {elevation[n]:+.0%})", elevation[n] >= 0.30)
    rest_n, gen_n = _record_count(systems["Restrained"]), _record_count(systems["Generic"])
    check(f"Restrained yields a meaningful system, richer than generic ({rest_n} > {gen_n})",
          rest_n >= 2 and rest_n > gen_n)
    # Beacon must keep exercising the STRUCTURAL detectors — the coverage that used to come from
    # real-product fixtures. If a recompile ever loses surface/behavior/composition/components, catch it.
    b = systems["Beacon"]
    check("Beacon exercises the full engine (surface + behavior + composition + components)",
          bool(b.surfaces) and bool(b.rules) and b.composition is not None and bool(b.components))
    # COVERAGE: identity outside the components dir must be observed. Beacon's scrubber lives in
    # src/app/page.tsx on purpose — the shared discovery list must surface it, and component capture
    # must carry it through to a role. A comps-only scan regression fails both.
    from rubrick.discover import discover_components
    repo, _ = PRODUCTS["Beacon"]
    check("discovery reaches src/app (Beacon's page.tsx is on the shared list)",
          any(p.endswith("src/app/page.tsx") for p in discover_components(repo, _COMPS)))
    check("Beacon captures the src/app scrubber as a component role ('page', drag)",
          any(c.role == "page" and c.gesture == "drag" for c in b.components))
    # DEPLOYMENT PREVALENCE: the over-application channel must be captured — scoped style moves
    # carry a frequency (per GENERATED effect-locality metadata, rubrick.scoping), and the
    # surface record carries its reservedness.
    check("Beacon captures deployment prevalence (styles and surface)",
          any(s.prevalence for s in b.styles)
          and all(s.prevalence is not None for s in b.surfaces))
    # INTERACTION PATTERNS: the response-pattern channel (what an interaction structurally IS —
    # carousel/disclosure/drawing/spotlight). BeaconCanvas's card spotlight must be captured on
    # a component role; a regression to choreography-only capture loses it.
    check("Beacon captures the spotlight-filter interaction pattern on a component role",
          any("spotlight-filter" in c.patterns for c in b.components))
    # LEARNED DETECTORS (the gate's self-extension): spec admission mechanics + pickup.
    check("detector admission: matches calibration, rejects the generic floor",
          _detector_mechanics_ok())
    check("an active learned detector gates; a rejected one never does",
          _learned_pickup_ok())

    print(f"\n=== {'ALL PASS ✓' if ok else 'FAILURES ✗'} ===")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
