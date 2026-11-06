"""Task 5: the law changes (FY2025-26). Measured, not narrated.

  python -m project_a.task5_law_change

What is measured here (all offline, deterministic):
  1. size of the change per implementation (diff of the artefact that has to change)
  2. SILENT-FAILURE experiment: realistic partial updates ("slabs changed, rebate forgotten", ...) applied to (a) and (c);
     we count wrong answers that raise no error and still pass the traceability auditor, and how many the golden suite catches
  3. the first-attempt compiled spec (kept in the repo as *.first_attempt_buggy.json) replayed against the oracle
What needs a human or a key (reported as such, never invented): wall-clock minutes spent, and impl (b) behaviour (needs GEMINI_API_KEY).
"""
from __future__ import annotations
import copy, difflib, json, os, time
from pathlib import Path
from project_a.common import TaxInput
from project_a.impl_a_rules import engine as A
from project_a.impl_c_compiled import runtime as C
from project_a import gemini_client as G

HERE = Path(__file__).parent
CASES = [c for c in json.loads((HERE / "data" / "test_cases_200.json").read_text())]
NEW_CASES = [c for c in CASES if c["fy"] == "2025-26"]


def _lines(p):
    return json.dumps(json.loads(Path(p).read_text()), indent=1, sort_keys=True).splitlines() if str(p).endswith(".json") else Path(p).read_text().splitlines()


def diff_size(a, b):
    d = [l for l in difflib.unified_diff(_lines(a), _lines(b), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    return dict(lines_added=sum(l[0] == "+" for l in d), lines_removed=sum(l[0] == "-" for l in d))


def _score(fn, cases):
    wrong = silent = 0
    for c in cases:
        r = fn(TaxInput(**c["input"]))
        bad = (r["old"]["total_tax"], r["new"]["total_tax"]) != (c["expected_old"], c["expected_new"])
        wrong += bad
        silent += bad and r["old"]["fully_traceable"] and r["new"]["fully_traceable"]   # wrong, no exception, auditor happy
    return wrong, silent


def mutations():
    base = json.loads((HERE / "impl_a_rules" / "rules_fy2025_26.json").read_text())
    old = json.loads((HERE / "impl_a_rules" / "rules_fy2024_25.json").read_text())
    m = {}
    x = copy.deepcopy(base); x["new"]["rebate"] = old["new"]["rebate"]; m["slabs updated, 87A rebate forgotten"] = x
    x = copy.deepcopy(base); x["new"]["slabs"] = old["new"]["slabs"]; m["87A rebate updated, slabs forgotten"] = x
    x = copy.deepcopy(base); x["new"]["rebate"]["max"] = 25000; m["rebate limit updated, rebate cap (60,000) forgotten"] = x
    x = copy.deepcopy(base); x["new"]["slabs"][5] = [2400000, 30]; x["new"]["slabs"][4] = [2000000, 20]; m["25% slab (20-24L) typo'd away"] = x
    m["whole FY2024-25 file copied, nothing changed"] = old
    return m


def run_experiment(write=True):
    t0 = time.perf_counter()
    out = {"change_size": {}, "silent_failure_experiment": {}, "first_attempt_compiled_spec": {}, "impl_b": {}}
    out["change_size"] = {
        "a_hand_coded (rules_fy*.json)": diff_size(HERE / "impl_a_rules" / "rules_fy2024_25.json", HERE / "impl_a_rules" / "rules_fy2025_26.json"),
        "c_compiled (compiled/fy*.json)": diff_size(HERE / "impl_c_compiled" / "compiled" / "fy2024_25.json", HERE / "impl_c_compiled" / "compiled" / "fy2025_26.json"),
        "b_llm (rules_text/fy*.md = the prompt)": diff_size(HERE / "rules_text" / "fy2024_25.md", HERE / "rules_text" / "fy2025_26.md"),
        "note": "Same legal facts, three artefacts. (a) and (c) edit numbers/DSL; (b) edits prose that the model must re-interpret each call.",
    }
    # --- silent failure experiment on (a) and (c)
    orig_load = A.load_rules
    spec_c = json.loads((HERE / "impl_c_compiled" / "compiled" / "fy2025_26.json").read_text())
    for name, rules in mutations().items():
        row = {}
        A.load_rules = lambda fy, _r=rules: _r if fy == "2025-26" else orig_load(fy)
        try:
            w, s = _score(A.compute, NEW_CASES); row["a_wrong"], row["a_silent"] = w, s
        finally:
            A.load_rules = orig_load
        # equivalent mutation for (c): patch the same numbers into the DSL spec
        sp = copy.deepcopy(spec_c)
        for st in sp["regimes"]["new"]["steps"]:
            if st["id"] == "slab_tax":
                st["tables"][0]["table"] = [[u, r] for u, r in rules["new"]["slabs"]]
            if st["id"] == "rebate":
                st["limit"], st["max"] = rules["new"]["rebate"]["limit"], rules["new"]["rebate"]["max"]
        w, s = _score(lambda i, _s=sp: C.compute(i, spec=_s), NEW_CASES); row["c_wrong"], row["c_silent"] = w, s
        row["cases"] = len(NEW_CASES)
        out["silent_failure_experiment"][name] = row
    try:
        A.compute(TaxInput(gross_salary=1_000_000, fy="2030-31")); out["unknown_fy_raises"] = False
    except ValueError:
        out["unknown_fy_raises"] = True
    # --- first-attempt compiled spec (kept for reproducibility)
    p = HERE / "impl_c_compiled" / "compiled" / "fy2025_26.first_attempt_buggy.json"
    if p.exists():
        sp = json.loads(p.read_text())
        try:
            w, s = _score(lambda i: C.compute(i, spec=sp), NEW_CASES)
            out["first_attempt_compiled_spec"] = {"cases": len(NEW_CASES), "wrong": w, "wrong_but_fully_traceable": s,
                                                  "comment": "wrong answers that no runtime check flags"}
        except Exception as e:
            out["first_attempt_compiled_spec"] = {"error": repr(e)[:200]}
    # --- impl (b): live only
    if G.has_key():
        from project_a.impl_b_llm import calculator as B
        n = int(os.environ.get("LLM_N", 30)); sample = NEW_CASES[:n]; wrong = silent = errs = 0
        for c in sample:
            try:
                r = B.compute(TaxInput(**c["input"]), bypass_cache=True)
            except Exception:
                errs += 1; continue
            bad = (r["old"]["total_tax"], r["new"]["total_tax"]) != (c["expected_old"], c["expected_new"])
            wrong += bad; silent += bad and r["old"].get("fully_traceable") and r["new"].get("fully_traceable")
        out["impl_b"] = {"status": "measured live (updated prompt text)", "cases": len(sample), "request_errors": errs, "wrong": wrong, "wrong_but_fully_traceable": silent}
    else:
        out["impl_b"] = {"status": "NOT MEASURED: needs GEMINI_API_KEY"}
    out["human_minutes_to_update"] = {"a": None, "b": None, "c": None, "note": "Fill from your own stopwatch; this script cannot measure human time."}
    out["machine_seconds"] = round(time.perf_counter() - t0, 2)
    if write:
        (HERE / "results").mkdir(exist_ok=True); (HERE / "results" / "task5.json").write_text(json.dumps(out, indent=1))
    print("=== TASK 5: FY2025-26 LAW CHANGE ===")
    print("change size:", json.dumps(out["change_size"], indent=1))
    print("silent-failure experiment (wrong answers over", len(NEW_CASES), "FY2025-26 cases; 'silent' = wrong AND no error AND auditor passes):")
    for k, v in out["silent_failure_experiment"].items():
        print(f"  {k:55s} (a) wrong {v['a_wrong']:3d} silent {v['a_silent']:3d} | (c) wrong {v['c_wrong']:3d} silent {v['c_silent']:3d}")
    print("first-attempt compiled spec:", out["first_attempt_compiled_spec"]); print("impl (b):", out["impl_b"])
    return out


if __name__ == "__main__":
    run_experiment()
