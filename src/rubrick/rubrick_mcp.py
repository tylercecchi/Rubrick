"""Rubrick MCP server — the shippable unit.

Exposes the product-system engine as tools a coding agent calls in its build loop:
  - list / get a product system (the identity, as context)
  - check_conformance (the VERIFIED GATE — re-observes the agent's output and returns
    objective violations, not the agent's self-report)
  - compile a product system from a repo (slow; run once, then the rest is fast)

Run:  the `rubrick-mcp` console script (installed via `pip install -e .`), or
      `python -m rubrick.rubrick_mcp` — stdio transport; register with an MCP client. Set
      RUBRICK_HOME to the directory holding your systems (data home; defaults to cwd).
"""

from __future__ import annotations

import pathlib
from rubrick import paths

from mcp.server.fastmcp import FastMCP

from rubrick.conform import check_conformance as _check_conformance
from rubrick.conform import format_report
from rubrick.orchestrate import compile_product_system as _compile
from rubrick.product_system import load_product_system, save_product_system

SYSTEMS = paths.systems_dir()

_INSTRUCTIONS = """Rubrick codifies a product's PRODUCT SYSTEM — the intent-bearing
deltas that make it itself (its typographic voice, color sentiment, material posture,
motion ceremony), NOT a token palette or component library.

Workflow when building UI to match an existing product:
  1. Call `list_product_systems`, then `get_product_system(name)` to load the identity
     as context BEFORE generating. Reproduce the identity_posture with YOUR OWN
     fonts/colors/spacing — never copy specific values.
  2. Generate the UI.
  3. Call `check_conformance(name, candidate_repo)` on your output. This RE-OBSERVES
     your code and returns objective violations — it is a verified gate, not your own
     self-report. Read `_formatted` for a human-readable summary.
  4. Resolve every FAIL (add the missing identity move), then re-check. SKIP means the
     candidate has no comparable element — not a failure. Finish only when no FAILs remain.

`compile_product_system` is slow (many model calls); run it once per product, then the
read/check tools are fast."""

mcp = FastMCP("rubrick", instructions=_INSTRUCTIONS)


def _path(name: str) -> pathlib.Path:
    return SYSTEMS / f"{name}.json"


def _validate_target(repo: str, gcss: str, comps: str) -> str | None:
    """A clear, actionable message if the target repo can't be observed — else None.
    Rubrick reads DECLARED source (a globals CSS + a components dir), so those must resolve."""
    r = pathlib.Path(repo).expanduser()
    if not r.exists():
        return f"repo path not found: {repo!r}. Pass an absolute path to the project directory."
    if not r.is_dir():
        return f"repo path is not a directory: {repo!r}."
    if not (r / gcss).is_file():
        found = [str(p.relative_to(r)) for p in r.rglob("*.css")
                 if "node_modules" not in p.parts][:5]
        hint = f" Found these CSS files: {found}." if found else " No .css files found under the repo."
        return (f"globals CSS not found at {gcss!r} (relative to the repo).{hint} "
                f"Pass the correct globals_css.")
    if not (r / comps).is_dir():
        return (f"components dir not found at {comps!r} (relative to the repo). "
                f"Pass the correct components_dir.")
    return None  # empty components dir is non-fatal — the system just degrades (no surface/behavior)


def _key_error() -> str | None:
    """A clear message if no Anthropic key is resolvable (compile + check need model calls)."""
    from rubrick.baseline import load_key
    if not load_key():
        return ("no ANTHROPIC_API_KEY found. Set the ANTHROPIC_API_KEY env var (how the MCP "
                "server is normally configured), or RUBRICK_ENV_FILE, or add a .env.local under "
                "RUBRICK_HOME. Rubrick needs it for the model calls that observe a product.")
    return None


@mcp.tool()
def list_product_systems() -> list[str]:
    """List the compiled product systems available to build against."""
    return sorted(p.stem for p in SYSTEMS.glob("*.json"))


@mcp.tool()
def get_product_system(name: str) -> dict:
    """Get a product system's identity as build context: the dispositions (the 'why')
    plus the identity moves per facet (typography / color / density / ambient, and any
    surface / behavior records) that a conforming product must carry. Pull this before
    generating UI for this product."""
    if not _path(name).exists():
        return {"error": f"no product system named {name!r}", "available": list_product_systems()}
    return load_product_system(str(_path(name))).emit_manifest()


@mcp.tool()
def check_conformance(name: str, candidate_repo: str,
                      globals_css: str = "src/app/globals.css",
                      components_dir: str = "src/components",
                      native: bool = False) -> dict:
    """Measure a candidate (your just-generated output, as a repo path) against a
    product system. Returns objective per-facet violations — a VERIFIED GATE, not a
    self-report. Call this after generating UI and resolve the violations before
    finishing. `_formatted` is a human-readable summary.

    Two modes: POSTURE (default) checks the transferable identity moves — use it when
    building a NEW product in this product's spirit (reproduce the moves with your own
    fonts/colors). NATIVE (native=True) ALSO checks that you reused this product's
    ACTUAL faces/palette — use it when building a NEW FEATURE for THIS product, where
    the new work must be indistinguishable from what's already there."""
    if not _path(name).exists():
        return {"error": f"no product system named {name!r}", "available": list_product_systems()}
    if err := _validate_target(candidate_repo, globals_css, components_dir):
        return {"error": err}
    if err := _key_error():
        return {"error": err}
    try:
        ps = load_product_system(str(_path(name)))
        report = _check_conformance(candidate_repo, globals_css, components_dir,
                                    f"conform:{name}:{candidate_repo}", ps, native=native)
        report["_formatted"] = format_report(report)
        return report
    except Exception as e:  # extraction / model / parse failure — report, don't crash the server
        return {"error": f"conformance check failed: {type(e).__name__}: {e}"}


@mcp.tool()
def compile_product_system(repo: str, name: str,
                           globals_css: str = "src/app/globals.css",
                           components_dir: str = "src/components",
                           sample_components: list[str] | None = None) -> dict:
    """Compile a product system from a repo and save it under `name`. SLOW — many
    model calls; run once, after which get_product_system / check_conformance are fast.
    Returns the compiled manifest."""
    if not name or not name.strip():
        return {"error": "name is required — the product system is saved under it."}
    if err := _validate_target(repo, globals_css, components_dir):
        return {"error": err}
    if err := _key_error():
        return {"error": err}
    try:
        ps = _compile(repo, globals_css, components_dir, sample_components or [], name)
        save_product_system(ps, str(_path(name)))
        from rubrick.review import emit_review
        review_path = str(SYSTEMS / f"{name}.review.json")
        n = emit_review(ps, name, review_path)
        manifest = ps.emit_manifest()
        if n:
            manifest["_review"] = (f"{n} novel move(s) the model found have no vocabulary word yet "
                                   f"— review {review_path} (mark promote/discard) then apply_review.")
        return manifest
    except Exception as e:  # model / extraction / IO failure — report, don't crash the server
        return {"error": f"compilation failed: {type(e).__name__}: {e}"}


@mcp.tool()
def list_learned() -> dict:
    """Inspect what the tool has learned across all products (the managed store):
    promoted vocabulary, refined dispositions, intent decisions, moment corrections,
    and discards. All global, compounding, and git-tracked in learned.json."""
    from rubrick.review import inspect_learned
    return inspect_learned()


@mcp.tool()
def apply_review(name: str) -> dict:
    """Apply a resolved review file (systems/<name>.review.json) to the learning store:
    promote novel moves into recognized vocabulary (compounds across all future compiles)
    or discard them (stop re-surfacing). Run after editing the review file's decisions."""
    rp = SYSTEMS / f"{name}.review.json"
    if not rp.exists():
        return {"error": f"no review file for {name!r} — compile it first"}
    from rubrick.review import apply_review as _apply
    return _apply(str(rp))


def main() -> None:
    """Console-script entry point (`rubrick-mcp`): launch the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
