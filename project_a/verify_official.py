"""Compare the engines with the Income Tax Department calculator. YOU fill data/official_calculator_checks.json
(official_old / official_new for each row, from incometax.gov.in's calculator, same FY, resident individual, salary only)
then run:  python -m project_a.verify_official"""
import json
from pathlib import Path
from project_a.common import TaxInput
from project_a.impl_a_rules import engine as A

p = Path(__file__).parent / "data" / "official_calculator_checks.json"


def main():
    ws = json.loads(p.read_text()); done = [w for w in ws if w["official_old"] is not None and w["official_new"] is not None]
    bad = []
    for w in done:
        r = A.compute(TaxInput(**w["input"], **({} if "fy" in w["input"] else {"fy": w["fy"]})))
        if (r["old"]["total_tax"], r["new"]["total_tax"]) != (w["official_old"], w["official_new"]):
            bad.append((w["id"], (r["old"]["total_tax"], r["new"]["total_tax"]), (w["official_old"], w["official_new"])))
    print(f"official calculator checks filled: {len(done)}/{len(ws)}; mismatches: {len(bad)}")
    for b in bad: print("  MISMATCH", b)
    if len(done) < 30: print("  (assignment requires >= 30 cases checked against the official calculator)")
    return len(done), bad


if __name__ == "__main__":
    main()
