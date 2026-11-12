"""Score the GESTURE layer + job rewriting against a labeled fixture.

    .venv/bin/python tests/probe_gestural.py [fixture]   (default: rubrick-gestural)

Checks, against the fixture's ANSWERS.json (outside src/):
  - leaks: mechanism words in the jobs handed to the twins (should be none),
  - components: each role's fate (captured vs review) after the twin check,
  - twins: what each twin uses for the history purpose (should not be the product's drag).
Model calls are content-cached, so re-runs are free and stable.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run(fixture: str = "rubrick-gestural") -> dict:
    from rubrick.absences import build_baseline, check_component_gestures, match_counterparts
    from rubrick.components import capture_components, detect_gesture
    fx = ROOT / "tests" / "fixtures" / fixture
    gcss, comps = "src/app/globals.css", "src/components"
    ans = json.loads((fx / "ANSWERS.json").read_text())
    base = build_baseline(str(fx), gcss, comps)
    jobs = base["jobs"]
    bad = ans["leaks"]["forbidden_in_jobs"]
    print(f"  kind: {jobs.product_kind}")
    leaks = []
    for o, n in zip(jobs.raw_jobs, jobs.needs):
        hit = [w for w in bad if w in n.lower()]
        leaks += hit
        print(f"  job: {o!r:48} -> {n!r}" + (f"   <-- LEAK {hit}" if hit else ""))
    sigs = capture_components(str(fx), comps, (fx / gcss).read_text(), limit=10)
    gt = check_component_gestures(str(fx), sigs, base, comps, gcss)
    for line in gt["log"]:
        print("  " + line)
    fate = {s["role"]: "captured" for s in gt["kept"]} | {s["role"]: "review" for s in gt["review"]}
    right = {r: fate.get(r) == e["expect"] for r, e in ans["components"].items()}
    hist = ans["twin"]
    roles = {"history-scrubber": str(fx / comps / "HistoryScrubber.tsx")}
    cps = []
    for name, root, tg, tc in base["twins"]:
        files = match_counterparts(str(fx), roles, root, tg, tc)["history-scrubber"]
        gs = sorted({detect_gesture(f) for f in files})
        g = "drag" if "drag" in gs else (",".join(gs) or "(no counterpart)")
        cps.append(g)
        print(f"  twin[{name}] history counterpart gesture: {g}")
    twin_ok = sum(g != hist["history_counterpart_gesture_not"] for g in cps)
    print(f"\n  leaks: {len(leaks)}   components right: {sum(right.values())}/{len(right)} {right}"
          f"   twins not using drag for history: {twin_ok}/{len(cps)}")
    return {"leaks": leaks, "components": right, "twins_ok": f"{twin_ok}/{len(cps)}"}


if __name__ == "__main__":
    run(*sys.argv[1:])
