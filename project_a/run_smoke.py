"""Quick demo: python -m project_a.run_smoke [--llm] [--offline]"""
import sys
from project_a.common import TaxInput
from project_a.impl_a_rules import engine as A
from project_a.impl_c_compiled import runtime as C

CASES = {
    "salary 12L": TaxInput(gross_salary=1_200_000),
    "old regime w/ deductions": TaxInput(gross_salary=1_200_000, sec_80c=150_000, nps_80ccd1b=50_000,
                                         health_self=25_000, health_parents=25_000, home_loan_interest=200_000),
    "odd rupees (288A/288B)": TaxInput(gross_salary=1_234_567),
}
impls = [("A rules", A.compute), ("C compiled", C.compute)]
if "--llm" in sys.argv or "--offline" in sys.argv:
    from project_a.impl_b_llm import calculator as B
    impls.append(("B llm" if "--offline" not in sys.argv else "B stub", lambda i: B.compute(i, offline="--offline" in sys.argv or None)))
for name, inp in CASES.items():
    print(f"\n== {name}")
    for label, fn in impls:
        r = fn(inp)
        print(f"  {label:11s} old={r['old']['total_tax']:>9,} new={r['new']['total_tax']:>9,} -> {r['recommendation']['recommended']}"
              f"  traceable={r['old']['fully_traceable'] and r['new']['fully_traceable']}")
    rec = A.compute(inp)["recommendation"]
    print("  ", rec["reason"], "| clauses:", ", ".join(rec["clause_citations"]))
