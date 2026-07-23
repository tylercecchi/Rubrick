"""The SUBTRACTIVE axis — identity by deliberate omission (negative space).

Everything else Rubrick captures is ADDITIVE: the moves a product adds beyond generic. But a
huge amount of identity is what a product deliberately REFUSES — one accent and no more, no
drop shadows, no ambient motion, no rounded corners. The stripping IS the identity (Linear,
brutalist/editorial work). An additive-only reader is blind to it: a deliberately shadowless
product looks the same as one that just forgot shadows.

Two sides:
  - CAPTURE — record a category the product systematically ZEROES while generic products have
    it. Only for DESIGNED products (they have other identity), so a generic app's omissions —
    which are just genericness — aren't mistaken for intent.
  - CHECK — the sharp one: conformance is otherwise presence-only, so a build can PASS while
    piling on everything the product refuses. This flags VIOLATION BY EXCESS — added
    elevation / color / motion / gradient / rounding the identity deliberately never uses.

Each omission is a `measure(repo, gcss, comps)` (the SAME reading at compile and check, so it
self-conforms exactly), a `zeroed` test (is the category absent?), and an `added` test (did a
candidate add it back?). Gaps between the two avoid borderline flip-flop.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

from rubrick.style_facets import (_all_colors, _hex_hue, gather_facet_source, max_shadow_blur,
                          palette_max_chroma, source_dirs)

_GENERIC_FALLBACK_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "inherit",
                           "-apple-system", "blinkmacsystemfont", "ui-sans-serif", "ui-monospace"}


def _ambient_motion(source: str) -> bool:
    return bool(re.search(r"@keyframes|animation\s*:|animation-name|\binfinite\b", source, re.I))


def _saturated_hue_families(source: str) -> set:
    fams = set()
    for h in _all_colors(source):
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        if max(r, g, b) - min(r, g, b) >= 32:  # saturated
            fams.add(int(_hex_hue(h) // 30))
    return fams


def _grep(pattern: str, repo: str, gcss: str, comps: str) -> str:
    r = pathlib.Path(repo)
    targets = source_dirs(repo, comps)
    if (r / gcss).exists():
        targets.append(str(r / gcss))
    try:
        return subprocess.run(["grep", "-rhoE", pattern, *targets],
                              capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""


def _max_radius(repo: str, gcss: str, comps: str):
    out = _grep(r"(border-radius|borderRadius)\s*:\s*[^,;}]+", repo, gcss, comps)
    vals = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)", out)]
    vals = [v for v in vals if v <= 200]
    return max(vals) if vals else None


def _font_families(repo: str, gcss: str, comps: str) -> int:
    from rubrick.type_extract import gather_type_source
    src = gather_type_source(repo, gcss, comps)
    fams = set()
    for m in re.findall(r"font-?family\s*:\s*[\"']?([^;,\"'\n}]+)", src, re.I):
        fams.add(m.strip().lower())
    fams = {f for f in fams if f and f not in _GENERIC_FALLBACK_FONTS}
    return len(fams) if fams else 1  # system-font-only reads as a single (system) voice


def _color_src(repo, gcss, comps):
    return gather_facet_source(repo, gcss, comps, "color")


# name -> {measure, zeroed, added, note, violation}. `added` receives the candidate's measure.
_OMISSIONS = {
    "elevation-shadow": {
        "measure": lambda r, g, c: max_shadow_blur(gather_facet_source(r, g, c, "elevation")),
        "zeroed": lambda v: v is None or v < 8,
        "added": lambda v: v is not None and v >= 20,
        "note": "deliberately FLAT — no drop-shadow depth (separation by hairlines, not elevation)",
        "violation": "the system is deliberately flat (no drop-shadow depth), but the build adds "
                     "{v}px shadows — elevation the identity refuses (violation by excess)",
    },
    "saturated-color": {
        "measure": lambda r, g, c: palette_max_chroma(_color_src(r, g, c)),
        "zeroed": lambda v: v is None,
        "added": lambda v: v is not None and v >= 60,
        "note": "MONOCHROMATIC — neutrals only, no saturated accent",
        "violation": "the system is monochromatic (neutrals only), but the build adds saturated "
                     "color (chroma {v}) — color the identity refuses",
    },
    "single-hue": {
        "measure": lambda r, g, c: len(_saturated_hue_families(_color_src(r, g, c))),
        "zeroed": lambda v: v == 1,        # exactly one accent hue family (monochrome is separate)
        "added": lambda v: v >= 2,
        "note": "SINGLE-HUE — one accent hue family only, no multi-color palette",
        "violation": "the system is single-hue (one accent family), but the build uses {v} hue "
                     "families — a second color the identity refuses",
    },
    "flat-color": {
        "measure": lambda r, g, c: bool(re.search(r"gradient\(", _color_src(r, g, c), re.I)),
        "zeroed": lambda present: not present,
        "added": lambda present: present,
        "note": "FLAT-COLOR — solid fills only, no gradients",
        "violation": "the system uses flat color (no gradients), but the build adds gradient fills "
                     "— decoration the identity refuses",
    },
    "sharp-corners": {
        "measure": _max_radius,
        "zeroed": lambda v: v is None or v <= 2,
        "added": lambda v: v is not None and v >= 8,
        "note": "SHARP-CORNERS — square/precise edges, no border-radius",
        "violation": "the system has sharp corners (no radius), but the build rounds to {v}px — "
                     "softening the identity refuses",
    },
    "single-face": {
        "measure": _font_families,
        "zeroed": lambda v: v == 1,
        "added": lambda v: v >= 2,
        "note": "SINGLE-FACE — one typeface, no display/body pairing",
        "violation": "the system commits to a single typeface, but the build introduces {v} faces "
                     "— type-pairing the identity refuses",
    },
    "ambient-motion": {
        "measure": lambda r, g, c: _ambient_motion(gather_facet_source(r, g, c, "ambient")),
        "zeroed": lambda present: not present,
        "added": lambda present: present,
        "note": "STATIC — no ambient / perpetual motion",
        "violation": "the system is static (no ambient motion), but the build adds ambient "
                     "animation — motion the identity refuses",
    },
}


def detect_subtractions(repo: str, gcss: str, comps: str, *, designed: bool) -> list[dict]:
    """Deliberate omissions this product maintains. Only for DESIGNED products — a generic
    app's absences are genericness, not identity."""
    if not designed:
        return []
    out = []
    for omit, spec in _OMISSIONS.items():
        if spec["zeroed"](spec["measure"](repo, gcss, comps)):
            out.append({"omits": omit, "note": spec["note"]})
    return out


def check_subtractions(subs: list[dict], repo: str, gcss: str, comps: str) -> list[str]:
    """Violation by EXCESS — the build adds a category the system deliberately omits."""
    v = []
    for s in subs:
        spec = _OMISSIONS[s["omits"]]
        val = spec["measure"](repo, gcss, comps)
        if spec["added"](val):
            v.append("subtraction: " + spec["violation"].format(v=val))
    return v
