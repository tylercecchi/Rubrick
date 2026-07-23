"""Tailwind support for the gathers.

Tailwind utilities have NO CSS in the repo (they're generated at build), so the
CSS/inline gathers never see them — a Tailwind product's identity is invisible. But
the identity usually lives in two readable places: the `tailwind.config` theme (custom
palette / fonts / scale) and the `className` utilities components actually use.

We don't resolve utilities to values (brittle, and configs customize them). Instead we
surface the config theme + the used utilities and let the extractor interpret them —
the model knows Tailwind. Palette anchors still come from hexes via the same regex, now
that the config's hexes are in the gathered source.

Returns "" for non-Tailwind repos, so it's a no-op there (graceful).
"""

from __future__ import annotations

import pathlib
import re
import subprocess

_CONFIG_NAMES = ("tailwind.config.js", "tailwind.config.ts",
                 "tailwind.config.cjs", "tailwind.config.mjs")

# utility prefixes relevant to each facet (a token is kept if it starts with one).
# `text-` is intentionally in both type (text-xs) and color (text-orange-500) — the
# model disambiguates. Arbitrary values (bg-[#ff7411], text-[10px]) start with a prefix.
_PREFIXES = {
    "typography": ("font-", "text-", "tracking-", "leading-", "uppercase", "lowercase",
                   "capitalize", "italic", "tabular", "normal-case", "antialiased",
                   "whitespace-", "truncate", "decoration-"),
    "color": ("bg-", "text-", "border-", "fill-", "stroke-", "ring-", "from-", "via-",
              "to-", "decoration-", "divide-", "outline-", "shadow-", "accent-", "caret-"),
    "density": ("p-", "px-", "py-", "pt-", "pb-", "pl-", "pr-", "m-", "mx-", "my-", "mt-",
                "mb-", "ml-", "mr-", "gap-", "space-", "grid", "flex", "col-", "row-", "w-",
                "h-", "min-", "max-", "inset-", "top-", "bottom-", "left-", "right-",
                "absolute", "relative", "sticky", "fixed", "overflow-", "aspect-", "columns-",
                "basis-", "grow", "shrink", "order-", "place-", "items-", "justify-", "self-"),
    "ambient": ("animate-", "transition", "duration-", "ease-", "delay-", "motion-"),
    "elevation": ("shadow", "backdrop-", "blur-", "drop-shadow-", "z-", "ring-",
                  "inset", "border"),
}


def read_tailwind_theme(repo: str) -> str:
    for name in _CONFIG_NAMES:
        p = pathlib.Path(repo) / name
        if p.exists():
            return p.read_text()
    return ""


def _classname_tokens(repo: str, comps: str) -> set[str]:
    """All utility tokens used across className strings (static and template-literal)."""
    root = pathlib.Path(repo) / comps
    try:
        out = subprocess.run(
            ["grep", "-rhoE", r'className=("[^"]*"|\{`[^`]*`\}|\{"[^"]*"\})', str(root)],
            capture_output=True, text=True, timeout=20).stdout
    except Exception:
        out = ""
    tokens: set[str] = set()
    for line in out.splitlines():
        # tailwind tokens: word chars, dashes, colons (variants), slashes (opacity),
        # brackets/# (arbitrary values), dots (2.5), parens/%
        for tok in re.findall(r"[A-Za-z][\w:/\[\]#().%.-]*", line):
            tokens.add(tok)
    return tokens


def gather_tailwind(repo: str, comps: str, facet: str, *, max_tokens: int = 70) -> str:
    """Config theme + facet-relevant utility classes, for a facet's gather. "" if the
    repo isn't a Tailwind project (no-op for CSS/inline products)."""
    theme = read_tailwind_theme(repo)
    if not theme:
        return ""
    prefixes = _PREFIXES.get(facet, ())
    used = sorted(t for t in _classname_tokens(repo, comps)
                  if any(t.startswith(p) for p in prefixes))
    used = used[:max_tokens]
    return (
        "\n// tailwind.config theme — custom palette / fonts / scale live here (the "
        "identity source for a Tailwind app; interpret it):\n" + theme +
        f"\n\n// tailwind utility classes used ({facet}-relevant):\n" + " ".join(used))
