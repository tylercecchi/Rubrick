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


def _library_signatures_ok() -> bool:
    """Library-aware detection: framer/GSAP-declared choreography must read as the same
    dispositions as its CSS twin, and a plain build must stay clean (four-way discipline)."""
    from rubrick.detect_treatments import detect_timings, detect_treatments
    from rubrick.facet_signatures import detect_facet_moves
    framer = ('<AnimatePresence><motion.div variants={v} initial="hidden" animate="visible" '
              'exit={{ opacity: 0 }} transition={{ duration: 0.45, type: "spring", '
              'stiffness: 300 }} /></AnimatePresence>')
    ambient = ('<motion.div animate={{ scale: [1, 1.06, 1] }} '
               'transition={{ repeat: Infinity, duration: 2.4 }} />')
    plain = 'const [open, setOpen] = useState(false); <div onClick={() => setOpen(!open)} />'
    t = detect_treatments(framer)
    return ({"multi-phase", "motion-ack", "spring-physics"} <= t
            and detect_timings(framer)["exit_ms"] == 450
            and "breathing-pulse" in detect_facet_moves("ambient", ambient)
            and not detect_treatments(plain)
            and not detect_facet_moves("ambient", plain))


def _capability_channel_ok() -> bool:
    """Capability channel: an imported identity library maps to its class; declared-but-
    unimported and generic-default libraries never count; the native gate demands the
    product's actual runtime while posture never gates on it (no posture check exists)."""
    import json as _json
    import pathlib as _pl
    import tempfile
    from rubrick.capabilities import check_native_capabilities, detect_capabilities
    repo = _pl.Path(tempfile.mkdtemp())
    (repo / "src/components").mkdir(parents=True)
    (repo / "package.json").write_text(_json.dumps(
        {"dependencies": {"framer-motion": "^11", "lodash": "^4", "recharts": "^2"}}))
    (repo / "src/components/Hero.tsx").write_text(
        'import { motion } from "framer-motion";\nimport _ from "lodash";\n<motion.div />')
    caps = detect_capabilities(str(repo), "src/components")
    generic_caps = detect_capabilities(str(_FIX / "rubrick-generic"), _COMPS)
    gate = check_native_capabilities(caps, [])
    return ([c["class"] for c in caps] == ["physics-motion-runtime"]
            and generic_caps == []
            and len(gate) == 1 and "physics-motion-runtime" in gate[0])


def _absence_admission_ok() -> bool:
    """The SUBTRACTIVE gate's inverted admission: a presence detector for an omission
    must NOT match the product that omits it and MUST match every generic exemplar."""
    from rubrick.detectors import admit_absence
    from rubrick.facet_signatures import raw_source
    rest = raw_source(*PRODUCTS["Restrained"], _COMPS)  # no icons anywhere
    ex = ['import { Check } from "lucide-react"; <Check size={16} />',
          '<FontAwesomeIcon icon={faCheck} />']
    nm = ['<img src="/logo.png" alt="Acme" width={24} />']  # an image, not an icon set
    good = {"all": [r"lucide-react|react-icons|@heroicons|FontAwesomeIcon|<svg"], "none": []}
    narrow = {"all": [r"lucide-react"], "none": []}       # misses an honest spelling
    loose = {"all": [r"<div"], "none": []}                # fires on the product itself
    # the status-badge gap: a SHAPE-only spec matches pill exemplars but also the avatar
    b_ex = ['<span className="rounded-full bg-green-100 px-2 text-xs">Active</span>',
            '<span className="rounded-full bg-blue-50 px-2 py-0.5">New</span>']
    b_nm = ['<img className="rounded-full w-8 h-8" src={user.avatar} />']
    shape = {"all": [r"rounded-full|border-radius:\s*9999px"], "none": []}
    return (admit_absence(good, rest, ex, nm) is None
            and "generic exemplar" in (admit_absence(narrow, rest, ex, nm) or "")
            and "calibration product" in (admit_absence(loose, rest, ex, nm) or "")
            and "no generic exemplar" in (admit_absence(good, rest, [], nm) or "")
            and "near-miss probe" in (admit_absence(good, rest, ex, []) or "")
            and "fires on near-miss" in (admit_absence(shape, rest, b_ex, b_nm) or "")
            and _element_scope_ok())


def _element_scope_ok() -> bool:
    """scope='element': a badge spec (fill + tight padding + small text) fires only when
    the traits share ONE element — three unrelated elements must not jointly fire it,
    which for an absence detector would wrongly FAIL an honest build."""
    from rubrick.detectors import run_spec
    badge = {"all": [r"background\s*:|\bbg-\w+-\d", r"padding\s*:\s*['\"]?[0-4]px|\bpx-[12]\b",
                     r"font-?size\s*:\s*1[0-3]|\btext-xs\b"], "none": [], "scope": "element",
             "flags": "i"}
    scattered = ('<div style={{ background: "#111", padding: 16 }}>'
                 '<i style={{ padding: "2px" }} /><p style={{ fontSize: 12 }}>x</p></div>')
    chip = '<span style={{ background: "#e6f4ea", padding: "2px 6px", fontSize: 12 }}>Ok</span>'
    css_split = ".tag { background: #eef; padding: 2px 8px; }\n.note { font-size: 12px }"
    css_one = ".tag { background: #eef; padding: 2px 8px; font-size: 12px }"
    whole = dict(badge, scope="source")
    return (not run_spec(badge, scattered) and run_spec(whole, scattered)
            and run_spec(badge, chip)
            and run_spec(badge, '<span onClick={() => go()} className="bg-red-100 px-2 text-xs">!</span>')
            and not run_spec(badge, css_split) and run_spec(badge, css_one))


def _twin(files: dict) -> tuple:
    """A hand-written stand-in for a generated generic twin (eval only — the real twin is
    a model generation; here we need a FIXED baseline to test the capture rule)."""
    import pathlib as _pl
    import tempfile
    root = _pl.Path(tempfile.mkdtemp(prefix="rubrick-twin-"))
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return (str(root), "src/app/globals.css", _COMPS)


def _learned_absence_gate_ok() -> bool:
    """ONE capture rule for every absence (built-in or learned): captured when the product
    zeroes it AND the generic twin has it; uncertain when the twin lacks it too. A captured
    learned absence gates add-back LLM-free and survives the manifest round-trip; a revoked
    built-in leaves the registry. Temp learned store; the real one is untouched."""
    import pathlib as _pl
    import tempfile
    from rubrick import detectors, learned
    from rubrick.product_system import ProductSystem
    from rubrick.subtractions import check_subtractions, classify, registry
    spec = {"all": [r"\btoast\b|Toaster|enqueueSnackbar"], "none": []}
    rrepo, rg = PRODUCTS["Restrained"]
    twin_has = _twin({"src/app/globals.css": ".card { box-shadow: 0 4px 24px rgba(0,0,0,.2) }",
                      "src/components/Save.tsx": 'import { toast } from "sonner"; toast("Saved")'})
    twin_lacks = _twin({"src/app/globals.css": "body { margin: 0 }",
                        "src/components/P.tsx": "export const P = () => <p>hi</p>"})
    orig = learned._F
    learned._F = _pl.Path(tempfile.mkdtemp()) / "learned.json"
    detectors._memo["mtime"] = "stale"
    try:
        learned.record_promoted_absence("toast-notifications", "inline status instead of toasts")
        detectors.record_detector("absence", "toast-notifications", spec, "active", "eval")
        r = classify(rrepo, rg, _COMPS, twin_has, designed=True)
        cap = {x["omits"] for x in r["captured"]}
        unc = {x["omits"] for x in r["uncertain"]}
        captured = {"toast-notifications", "elevation-shadow"} <= cap and "flat-color" in unc
        r2 = classify(rrepo, rg, _COMPS, twin_lacks, designed=True)
        no_delta = not r2["captured"] and "toast-notifications" in {x["omits"] for x in r2["uncertain"]}
        not_designed = classify(rrepo, rg, _COMPS, twin_has, designed=False)["captured"] == []
        toast = next(x for x in r["captured"] if x["omits"] == "toast-notifications")
        cand = _twin({"src/components/Save.tsx": 'import { toast } from "sonner";\ntoast("Saved")'})
        fires = bool(check_subtractions([toast], *cand))
        clean = not check_subtractions(r["captured"], rrepo, rg, _COMPS)
        m = ProductSystem(dispositions={}, subtractions=[toast]).emit_manifest()
        roundtrip = m["subtractions"][0]["detector"] == spec and "omission_is_identity" in m["_guide"]
        detectors.record_detector("absence", "flat-color", None, "revoked", "eval")
        revoked = "flat-color" not in registry() and "single-hue" in registry()
        return captured and no_delta and not_designed and fires and clean and roundtrip and revoked
    finally:
        learned._F = orig
        detectors._memo["mtime"] = "stale"


def _measure_absence_ok() -> bool:
    """Amount-based omissions: a MEASURE detector is admitted by reading (calibration
    zeroed, generic exemplars not), and pre-unification manifests (built-ins stored by
    name only) still gate."""
    from rubrick.detectors import admit_absence
    from rubrick.subtractions import check_subtractions
    rrepo, rg = PRODUCTS["Restrained"]
    cal = (rrepo, rg, _COMPS)
    ex = [".btn { transition: background 0.2s ease }", '<div className="transition-all duration-200" />']
    good = {"measure": "has_transition", "zeroed": "false", "added": "true"}
    one_face = {"measure": "font_families", "zeroed": "== 1", "added": ">= 2"}
    bad_measure = {"measure": "vibes", "zeroed": "false", "added": "true"}
    legacy = [{"omits": "flat-color", "note": "FLAT-COLOR — solid fills only, no gradients"}]
    grad = _twin({"src/app/globals.css": ".hero { background: linear-gradient(#f00, #00f) }"})
    return (admit_absence(good, "", ex, [], cal) is None
            and "does not meet 'added'" in (admit_absence(one_face, "", ex, [], cal) or "")
            and "unknown measure" in (admit_absence(bad_measure, "", ex, [], cal) or "")
            and "calibration repo" in (admit_absence(good, "", ex, [], None) or "")
            and bool(check_subtractions(legacy, *grad))
            and not check_subtractions(legacy, rrepo, rg, _COMPS))

def _survey_triage_ok() -> bool:
    """The survey's DETERMINISTIC half: an ungrounded host is dropped (inapplicable), an
    unsystematic or known/discarded one never surfaces, confidence follows substitute vs
    counter-evidence, findings rank high -> low, and the jobs scrub strips the product's
    component names without eating its domain nouns."""
    from rubrick.absences import AbsenceSighting, AbsenceSurvey, scrub, triage
    src = "export function TaskRow() {}\nexport function UndoRow() {}\n.row { color: red }"
    def s(name, host, instead="", against="", systematic=True):
        return AbsenceSighting(name=name, category="feedback", twin_evidence=f"<{name} />",
                               host=host, evidence="absent", instead=instead,
                               against=against, systematic=systematic)
    survey = AbsenceSurvey(deliberate=[
        s("hover-lift", "TaskRow", against="--row-hover defined, never used"),
        s("confirm-dialog", "TaskRow delete action", instead="undo"),
        s("user-avatar", "ProfileHeader"),                       # host doesn't exist
        s("tooltip", "TaskRow", systematic=False),
        s("elevation-shadow", "TaskRow"),                        # known (registry)
        s("toast", "UndoRow", instead="inline text", against="half-wired"),
    ])
    keep, dropped = triage(survey, src, {"elevation-shadow"}, set())
    order = [(k["name"], k["confidence"]) for k in keep]
    return (order == [("confirm-dialog", "high"), ("toast", "medium"), ("hover-lift", "low")]
            and any("user-avatar" in d and "inapplicable" in d for d in dropped)
            and any("tooltip" in d for d in dropped)
            and keep[0]["exemplars"] == ["<confirm-dialog />"]
            and scrub("restore a task via the UndoRow banner", {"UndoRow", "Undo", "Row"})
                == "restore a task via the banner"
            and scrub("add a task", {"UndoRow", "Undo", "Row"}) == "add a task")


def _baseline_logic_ok() -> bool:
    """The twin-baseline logic, deterministically: majority vote across twins (captured vs
    uncertain), the purpose-level gesture check (a gesture most twins use for the same
    purpose demotes a gesture-only component to review; one they don't use stays; feel
    still counts), designer job overrides, library drag idioms, and host grounding."""
    from rubrick.absences import apply_job_overrides, gesture_defaults, host_grounded, still_identity
    from rubrick.components import detect_gesture
    from rubrick.subtractions import classify
    rrepo, rg = PRODUCTS["Restrained"]
    shadow = _twin({"src/app/globals.css": ".c { box-shadow: 0 4px 24px rgba(0,0,0,.2) }"})
    flat = _twin({"src/app/globals.css": ".c { border: 1px solid #ddd }"})
    def fate(twins, name="elevation-shadow"):
        r = classify(rrepo, rg, _COMPS, twins, designed=True)
        return ("captured" if name in {x["omits"] for x in r["captured"]} else
                "uncertain" if name in {x["omits"] for x in r["uncertain"]} else None)
    vote = (fate([shadow, shadow, flat]) == "captured" and fate([shadow, flat, flat]) == "uncertain"
            and classify(rrepo, rg, _COMPS, [shadow, shadow, flat], designed=True)["representative"] == 0)
    native = '<div draggable onDragStart={s} />'
    pangea = 'import { DragDropContext, Draggable } from "@hello-pangea/dnd";'
    dndkit = 'const { attributes } = useSortable({ id });'
    plain = 'const [draft, setDraft] = useState(""); <button onClick={add}>Add</button>'
    drag_sig = {"role": "board", "gesture": "drag", "patterns": set(),
                "material_roles": set(), "treatments": set()}
    feel_sig = {**drag_sig, "treatments": {"spring-physics", "multi-phase", "motion-ack"}}
    d3 = gesture_defaults(drag_sig, [[plain, native], [pangea], [dndkit]])   # 3/3 drag
    d1 = gesture_defaults(drag_sig, [[plain], [plain], [native]])             # 1/3
    gesture = (d3["gesture"] and not still_identity(drag_sig, d3)            # -> review
               and not d1["gesture"]                                         # -> kept
               and still_identity(feel_sig, d3)                              # feel still counts
               and detect_gesture(pangea) == "drag" and detect_gesture(dndkit) == "drag"
               and detect_gesture(plain) == "click")
    jobs = apply_job_overrides([("restore a removed task", "recover from a mistaken removal"),
                                ("add a task", "add a task"), ("replay history", "see history")],
                               {"restore a removed task": "STRIKE", "replay history": "audit changes"})
    hosts = (host_grounded(".row list item", ".row { padding: 0 }")
             and not host_grounded("ProfileHeader avatar", ".row { padding: 0 }")
             and not host_grounded("row", ".arrow { x: 1 }"))
    from rubrick.absences import _JobsDelta, apply_jobs_delta
    prev = {"product_kind": "a kanban board", "jobs": ["add a task", "move a task"], "content": []}
    same = apply_jobs_delta(prev, [_JobsDelta()]) == prev                    # no change -> verbatim
    one = apply_jobs_delta(prev, [_JobsDelta(remove_jobs=["Add a task"], add_jobs=["archive a task"])])
    split = apply_jobs_delta(prev, [_JobsDelta(remove_jobs=["add a task"]), _JobsDelta()])
    sticky = (same and one["jobs"] == ["move a task", "archive a task"]
              and split["jobs"] == prev["jobs"])  # a removal needs every chunk to agree
    return vote and gesture and jobs == ["add a task", "audit changes"] and hosts and sticky


def _measure_spellings_ok() -> bool:
    """Every omission measure reads the SAME styling the same way however it's written —
    literal CSS, design tokens (var(--x)), inline React styles, Tailwind utilities — and a
    plain build reads as having none of it. (A literal-only reader made a token-based
    product read as "no rounding": a false refusal at capture, a missed add-back at check.)"""
    from rubrick.subtractions import BUILTINS, MEASURES, added, zeroed
    forms = {
        "literal": _twin({"src/app/globals.css": ".a{border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.2);"
                          "background:linear-gradient(#3b82f6,#22c55e);font-family:'Inter';font-weight:600;"
                          "animation:p 2s infinite}\n.b{font-family:'Fraunces';font-weight:700;color:#3b82f6}",
                          "src/components/A.tsx": "export const A = () => <div className='a' />"}),
        "tokens": _twin({"src/app/globals.css": ":root{--r:12px;--sh:0 8px 24px rgba(0,0,0,.2);"
                         "--g:linear-gradient(#3b82f6,#22c55e);--f1:'Inter';--f2:'Fraunces';--w1:600;--w2:700;"
                         "--blue:#3b82f6}\n.a{border-radius:var(--r);box-shadow:var(--sh);background:var(--g);"
                         "font-family:var(--f1);font-weight:var(--w1);animation:p 2s infinite}\n"
                         ".b{font-family:var(--f2);font-weight:var(--w2);color:var(--blue)}",
                         "src/components/A.tsx": "export const A = () => <div className='a' />"}),
        "inline": _twin({"src/components/A.tsx": 'export const A = () => <div style={{ borderRadius: 12, '
                         'boxShadow: "0 8px 24px rgba(0,0,0,.2)", background: "linear-gradient(#3b82f6, #22c55e)", '
                         'fontFamily: "Inter", fontWeight: 600, animation: "p 2s infinite" }}><h1 style={{ '
                         'fontFamily: "Fraunces", fontWeight: 700, color: "#3b82f6" }} /></div>'}),
        "tailwind": _twin({"src/components/A.tsx": 'import { Inter, Fraunces } from "next/font/google";\n'
                           'export const A = () => <div className="rounded-xl shadow-lg bg-gradient-to-r '
                           'from-blue-500 to-green-500 font-semibold animate-pulse"><h1 className="font-bold '
                           'text-blue-600" /></div>'}),
    }
    plain = _twin({"src/app/globals.css": ".a{padding:8px;color:#333}",
                   "src/components/A.tsx": "export const A = () => <div className='a'>hi</div>"})
    for name, ent in BUILTINS.items():
        det = ent["detector"]
        if name in ("single-hue", "single-face"):
            continue  # "exactly one" omissions: covered by the counts below
        if not all(added(det, MEASURES[det["measure"]](*f)) for f in forms.values()):
            return False
        if not zeroed(det, MEASURES[det["measure"]](*plain)):
            return False
    counts = {k: (MEASURES["hue_families"](*f), MEASURES["font_families"](*f), MEASURES["font_weights"](*f))
              for k, f in forms.items()}
    return (len(set(counts.values())) == 1 and counts["literal"] == (2, 2, 2)
            and MEASURES["font_families"](*plain) is None)


def _principles_ok() -> bool:
    """Principles: a business motive the product never states is flagged (and isn't when
    its own jobs name it); interactions sharing most moves share ONE principle (Beacon's
    browse vs toggle); a designer's rewording is scoped to its product, legacy unscoped
    wording still applies. Temp learned store; the real one is untouched."""
    import pathlib as _pl
    import tempfile
    from rubrick import learned
    from rubrick.orchestrate import motive_flag, similar_moves
    flags = (motive_flag("keep them nominally in control while raising the cost of exit")
             and motive_flag("slow and soften to preserve retention")
             and not motive_flag("selecting a signal is a deliberate, ceremonial act")
             and not motive_flag("protect retention of patient records", ["ensure retention of records"]))
    browse = {"demote-not-remove", "interaction-lock", "manufactured-latency", "motion-ack", "multi-phase"}
    toggle = browse - {"motion-ack"}
    group = similar_moves(browse, toggle) and not similar_moves(browse, {"spring-physics", "reactive-continuous"})
    orig = learned._F
    learned._F = _pl.Path(tempfile.mkdtemp()) / "learned.json"
    try:
        learned.record_rationale("ceremony", "Beacon wording", product="Beacon")
        learned.record_rationale("legacy-id", "old global wording")
        scoped = (learned.rationale("ceremony", product="Beacon") == "Beacon wording"
                  and learned.rationale("ceremony", product="Ledger") is None
                  and learned.rationale("legacy-id", product="Ledger") == "old global wording")
    finally:
        learned._F = orig
    return bool(flags) and group and scoped


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
    # LIBRARY-AWARE DETECTION + CAPABILITY CHANNEL (the anti-flatness pair): motion-library
    # choreography reads as the same dispositions as CSS, and the identity's runtime
    # capability classes are detected, instructed, and native-gated.
    check("library-declared choreography detects (framer/GSAP); plain stays clean",
          _library_signatures_ok())
    check("capability channel: imported identity libs map to classes; native gate fires",
          _capability_channel_ok())

    # OPEN SUBTRACTIVE CHANNEL: omission is seen/gated as openly as addition — learned
    # presence detectors with inverted admission, captured only as a diff vs the baseline.
    check("absence admission: rejects product-matching, exemplar-missing, near-miss-firing",
          _absence_admission_ok())
    check("one capture rule vs the generic twin: captured / uncertain / revocable / gates",
          _learned_absence_gate_ok())
    check("measure-based absences admit by reading; legacy manifests still gate",
          _measure_absence_ok())
    check("survey triage: inapplicable/unsystematic dropped, confidence-ranked, scrub safe",
          _survey_triage_ok())
    check("twin baseline: majority vote, purpose-level gesture check, job overrides",
          _baseline_logic_ok())
    check("omission measures read literal / token / inline / Tailwind styling identically",
          _measure_spellings_ok())
    check("principles: invented motives flagged, shared behavior merged, rewrites scoped",
          _principles_ok())

    print(f"\n=== {'ALL PASS ✓' if ok else 'FAILURES ✗'} ===")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
