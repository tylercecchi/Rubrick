"""Stability under irrelevant edits: does a change that shouldn't matter flip decisions?

    .venv/bin/python tests/probe_stability.py

Copies each labeled fixture, makes edits with no design meaning (a comment, a renamed
local variable), rebuilds the baseline (jobs -> twins), and compares every decision —
registry omissions (captured/uncertain) and component gesture fates — between original
and edit, once with ONE twin and once with the MAJORITY of all twins. Every model call
is content-cached; the edited copy pays for new calls only where its content differs.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
GCSS, COMPS = "src/app/globals.css", "src/components"

EDITS = {
    "rubrick-omissions": [("src/components/TaskList.tsx", r"\bdraft\b", "pending"),
                          ("src/components/TaskList.tsx", r"^", "// task list screen\n")],
    "rubrick-gestural": [("src/components/HistoryScrubber.tsx", r"\bseek\b", "scrubTo"),
                         ("src/components/Board.tsx", r"^", "// board view\n")],
}


def decisions(repo: str, twins_subset: str) -> dict:
    from rubrick.absences import build_baseline, check_component_gestures
    from rubrick.components import capture_components
    from rubrick.subtractions import classify
    base = build_baseline(repo, GCSS, COMPS)
    if twins_subset == "one":
        base = {**base, "twins": [t for t in base["twins"] if t[0] == "default"]}
    r = classify(repo, GCSS, COMPS, [t[1:] for t in base["twins"]], designed=True)
    out = {f"absence:{x['omits']}": "captured" for x in r["captured"]}
    out |= {f"absence:{x['omits']}": "uncertain" for x in r["uncertain"]}
    sigs = capture_components(repo, COMPS, (pathlib.Path(repo) / GCSS).read_text(), limit=10)
    gt = check_component_gestures(repo, sigs, base, COMPS, GCSS)
    out |= {f"component:{s['role']}": "captured" for s in gt["kept"]}
    out |= {f"component:{s['role']}": "review" for s in gt["review"]}
    return {"decisions": out, "jobs": base["jobs"].jobs if base["jobs"] else []}


def run() -> None:
    """A RECOMPILE of the same product after an edit: compile a copy, edit it IN PLACE,
    compile again (same repo path, so the sticky jobs memory applies as in real use)."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="rubrick-stability-"))
    for fx, edits in EDITS.items():
        src = ROOT / "tests" / "fixtures" / fx
        work = tmp / fx
        shutil.copytree(src / "src", work / "src")
        before = {m: decisions(str(work), m) for m in ("one", "majority")}
        for rel, pat, rep in edits:
            f = work / rel
            f.write_text(re.sub(pat, rep, f.read_text(), count=0 if pat != "^" else 1))
        print(f"=== {fx}")
        for mode in ("one", "majority"):
            a, b = before[mode], decisions(str(work), mode)
            flips = {k: (a["decisions"].get(k), b["decisions"].get(k))
                     for k in set(a["decisions"]) | set(b["decisions"])
                     if a["decisions"].get(k) != b["decisions"].get(k)}
            print(f"  [{mode:8}] jobs identical: {a['jobs'] == b['jobs']}   "
                  f"decisions: {len(a['decisions'])}   flips: {len(flips)} {flips or ''}")


if __name__ == "__main__":
    run()
