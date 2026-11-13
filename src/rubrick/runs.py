"""Check runs — every conformance check, kept, so each switch can show how builds did on it.

Stored per product under <RUBRICK_HOME>/runs/<product>.json (newest first, last 50). A run is
the report check_conformance returns plus when, what was checked, and in which mode. Item
results are derived from a run's records, keyed the same way as the manifest catalog.
"""

from __future__ import annotations

import datetime
import json
import pathlib

from rubrick import paths

_KEEP = 50


def _file(product: str) -> pathlib.Path:
    d = paths.home() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in product)
    return d / f"{safe}.json"


def record_run(product: str, candidate_repo: str, native: bool, report: dict,
               label: str = "") -> dict:
    run = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "candidate": candidate_repo, "label": label or pathlib.Path(candidate_repo).name,
           "mode": "native" if native else "posture",
           "summary": report.get("_summary", {}),
           "records": {k: {"conforms": v.get("conforms"), "violations": v.get("violations", []),
                           **({"note": v["note"]} if v.get("note") else {})}
                       for k, v in report.items() if k != "_summary"}}
    f = _file(product)
    runs = json.loads(f.read_text()) if f.exists() else []
    runs.insert(0, run)
    f.write_text(json.dumps(runs[:_KEEP], indent=2))
    return run


def load_runs(product: str) -> list[dict]:
    f = _file(product)
    return json.loads(f.read_text()) if f.exists() else []


def item_result(run: dict, key: str) -> dict | None:
    """How a run did on one catalog item: {result: pass|fail|not-comparable, detail} or
    None when the run says nothing about it."""
    from rubrick.subtractions import BUILTINS
    recs = run.get("records", {})
    head, _, rest = key.partition(":")

    def of(rec, matcher=None):
        if rec is None:
            return None
        if rec.get("conforms") is None:
            return {"result": "not-comparable", "detail": rec.get("note", "")}
        hits = [v for v in rec.get("violations", []) if matcher is None or matcher(v)]
        if hits:
            return {"result": "fail", "detail": hits[0]}
        return {"result": "pass", "detail": ""}

    if head == "absence":
        tmpl = BUILTINS.get(rest, {}).get("violation", "")
        probe = tmpl.split("{v}")[0][:40] if tmpl else ""
        return of(recs.get("subtractions"),
                  lambda v: (probe and probe in v) or f" {rest} " in v or f"adds {rest}" in v) \
            or ({"result": "pass", "detail": ""} if "subtractions" in recs else None)
    if head in ("component", "surface"):
        return of(recs.get(key))
    if head == "rule":
        return of(recs.get(f"behavior:{rest}"))
    if key == "composition":
        return of(recs.get("composition"))
    if head in ("typography", "color", "density", "ambient", "elevation"):
        rec = recs.get(head)
        if rec is None:
            return None
        if rec.get("conforms") is None:
            return {"result": "not-comparable", "detail": rec.get("note", "")}
        # a move fails when the facet's violation names it as missing; metric and
        # application failures belong to the facet, not to one move
        miss = [v for v in rec.get("violations", []) if f"'{rest}'" in v and
                ("missing" in v or "NONE of" in v)]
        return {"result": "fail", "detail": miss[0]} if miss else {"result": "pass", "detail": ""}
    return None
