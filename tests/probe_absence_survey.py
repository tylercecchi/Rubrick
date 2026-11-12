"""Score the open absence survey against a labeled answer key.

    .venv/bin/python tests/probe_absence_survey.py [fixture]   (default: rubrick-omissions)

The survey's judgment is a model call, so it isn't in the regression guard; this probe
MEASURES it. The fixture's ANSWERS.json (outside src/, never read by discovery) lists the
deliberate omissions (each with a visible substitute) and the decoys a good survey must
NOT report: defaults the product actually has, an unfinished-looking gap, and features
with nothing to host them. Results are content-cached, so re-runs are free and stable.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _matches(entry: dict, finding: dict) -> bool:
    text = f"{finding.get('name', '')} {finding.get('instead', '')}".lower()
    name = finding.get("name", "").lower()
    return any(all(tok in (name if len(ts) == 1 else text) for tok in ts)
               for ts in entry["match"])


def score(findings: list[dict], answers: dict, twin_source: str = "") -> dict:
    import re
    in_twin = {k for k, e in answers["deliberate"].items()
               if e.get("twin_pattern") and re.search(e["twin_pattern"], twin_source)}
    found, errors, unlabeled = {}, [], []
    for f in findings:
        hit = False
        for key, ent in answers["deliberate"].items():
            if _matches(ent, f):
                found.setdefault(key, f["name"])
                hit = True
        for key, ent in answers["decoys"].items():
            if _matches(ent, f):
                hit = True
                low = f.get("confidence") == "low"
                if ent["kind"] != "accident" or not low:
                    errors.append(f"{f['name']} -> decoy:{key} ({ent['kind']}"
                                  f"{', conf=' + f.get('confidence', '?') if ent['kind'] == 'accident' else ''})")
        if not hit:
            unlabeled.append(f["name"])
    n = len(answers["deliberate"])
    return {"recall": f"{len(set(found) & in_twin)}/{len(in_twin)}",
            "independence": f"{len(in_twin)}/{n}", "found": found,
            "missed": sorted(in_twin - set(found)),
            "not_a_delta": sorted(set(answers["deliberate"]) - in_twin),
            "errors": errors, "unlabeled": unlabeled}


def run(fixture: str = "rubrick-omissions") -> dict:
    from rubrick.absences import observe_absences
    fx = ROOT / "tests" / "fixtures" / fixture
    answers = json.loads((fx / "ANSWERS.json").read_text())
    r = observe_absences(str(fx), "src/app/globals.css", "src/components", designed=True)
    findings = [{"name": p["name"], "instead": p.get("instead", ""),
                 "confidence": p.get("confidence", "unrated"),
                 "host": p.get("host", ""), "against": p.get("against", "")}
                for p in r["pending"]]
    for line in r["log"]:
        if "survey" in line or "dropped" in line:
            print("  log:", line[:200])
    for f in findings:
        print(f"  - {f['name']:<28} conf={f['confidence']:<8} instead={f['instead'][:60]!r}"
              + (f" against={f['against'][:50]!r}" if f["against"] else ""))
    from rubrick.absences import _twin_source, generate_twin, materialize_twin
    twin_repo = materialize_twin(generate_twin(str(fx), "src/app/globals.css", "src/components"),
                                 "src/app/globals.css", "src/components")
    s = score(findings, answers, _twin_source(twin_repo, "src/app/globals.css", "src/components")
              if twin_repo else "")
    print(f"\n  baseline independence {s['independence']} (labeled defaults the twin includes;"
          f" not a delta vs this twin: {s['not_a_delta']})")
    print(f"  recall {s['recall']} (twin-relative)  found={s['found']}  missed={s['missed']}")
    print(f"  errors ({len(s['errors'])}): {s['errors']}")
    print(f"  unlabeled: {s['unlabeled']}")
    return s


if __name__ == "__main__":
    run(*sys.argv[1:])
