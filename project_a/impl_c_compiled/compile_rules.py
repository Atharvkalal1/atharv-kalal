"""One-off compile step: LLM turns rule text into a DSL spec. A HUMAN then reviews and promotes it.

    python -m project_a.impl_c_compiled.compile_rules --fy 2024-25

Writes compiled/fy<slug>.candidate.json, validates it, and diffs it against the reviewed spec
(if any) on a grid of inputs. It never overwrites the reviewed spec.
"""
from __future__ import annotations
import argparse, json, random
from pathlib import Path
from project_a.common import TaxInput, fy_slug
from project_a import gemini_client as G
from project_a.gemini_client import generate_json
from project_a.impl_c_compiled import dsl, runtime

ROOT = Path(__file__).parent
DSL_DOC = dsl.__doc__

EXAMPLE = {"id": "std", "op": "expr", "expr": "min(50000, gross_salary)", "clause": "R-STD-OLD", "label": "Standard deduction"}

PROMPT = """Convert the tax rules below into a JSON rule spec for the DSL described here.

# DSL
{dsl}
Variables available in expressions: gross_salary, basic_da, hra_received, rent_paid, metro_city (bool), age,
sec_80c, nps_80ccd1b, health_self, health_parents, parents_senior (bool), home_loan_interest, plus ids of earlier steps.
Also available: hra_salary_base (the Rule 2A 'salary'), apply_288_rounding (bool).
Required outputs per regime (output name -> step id): gross_salary, raw_taxable_income, taxable_income, tax_on_slabs, rebate_87a,
raw_surcharge, surcharge_marginal_relief, surcharge, cess, raw_total_tax, total_tax.
Required step ids: raw_taxable (before R-288A), taxable (after R-288A, honouring apply_288_rounding), slab_tax, rebate (out="tax_after_rebate"),
raw_surcharge (op surcharge), surcharge_marginal_relief, surcharge (= raw - relief), cess, raw_total, rounding_288b (trace "nonzero"), total (R-288B);
deduction step ids: std, and for old: hra_ex, hp, d80c, d80ccd, d80d_self, d80d_par. Every step has "clause" (an R-... ID from the rules) and "label".
Do NOT invent numbers. Every constant must come from the rules. Example step: {example}
Output: {{"fy": "{fy}", "regimes": {{"new": {{"steps": [...], "outputs": {{...}}}}, "old": {{...}}}}}}

# RULES
{rules}
"""

SAMPLE = TaxInput(gross_salary=1_500_000, basic_da=600_000, hra_received=240_000, rent_paid=300_000,
                  metro_city=True, age=35, sec_80c=150_000, home_loan_interest=100_000).to_dict()


def grid(n=500, seed=1):
    rnd = random.Random(seed)
    for _ in range(n):
        g = rnd.choice([300_000, 700_000, 775_000, 1_200_000, 5_085_000, 12_000_000, 25_000_000, 60_000_000]) + rnd.randint(0, 50_000)
        yield TaxInput(gross_salary=g, basic_da=g // 2, hra_received=g // 5, rent_paid=rnd.randint(0, g // 2),
                       metro_city=rnd.random() < .5, age=rnd.choice([30, 60, 85]), sec_80c=rnd.randint(0, 200_000),
                       nps_80ccd1b=rnd.randint(0, 60_000), health_self=rnd.randint(0, 60_000),
                       health_parents=rnd.randint(0, 60_000), parents_senior=rnd.random() < .5,
                       home_loan_interest=rnd.randint(0, 250_000))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fy", default="2024-25")
    ap.add_argument("--offline", action="store_true", help="no LLM: copy the reviewed spec as a tagged stub candidate")
    ap.add_argument("--bypass-cache", action="store_true"); a = ap.parse_args()
    rules = (ROOT.parent / "rules_text" / f"fy{fy_slug(a.fy)}.md").read_text()
    if a.offline or not G.has_key():
        print("WARNING: OFFLINE STUB - no LLM was called. The candidate is a copy of the reviewed spec; the diff below is meaningless.")
        spec = dict(runtime.load_spec(a.fy), generated_by="offline_stub")
        meta = {"mode": "offline_stub"}
    else:
        spec, meta = generate_json(PROMPT.format(dsl=DSL_DOC, example=json.dumps(EXAMPLE), fy=a.fy, rules=rules),
                                   system="You compile legal rules into a strict JSON DSL. Output JSON only.",
                                   bypass_cache=a.bypass_cache)
    cand = ROOT / "compiled" / f"fy{fy_slug(a.fy)}.candidate.json"
    cand.write_text(json.dumps(spec, indent=1))
    print("compile meta:", meta, "->", cand)
    problems = dsl.validate_spec(spec, SAMPLE)
    print("VALIDATION:", "OK" if not problems else problems)
    if problems:
        return
    try:
        ref = runtime.load_spec(a.fy)
    except ValueError:
        print("No reviewed spec to diff against; review the candidate by hand and test it on the 200-case suite.")
        return
    bad = 0
    for inp in grid():
        x, y = runtime.compute(inp, ref), runtime.compute(inp, spec)
        for r in ("old", "new"):
            if x[r]["total_tax"] != y[r]["total_tax"]:
                bad += 1
                if bad <= 5:
                    print("DIFF", r, inp, x[r]["total_tax"], y[r]["total_tax"])
    print(f"diff vs reviewed spec on 500 inputs: {bad} mismatching regime results")
    print("If 0 and you have read every step: copy the candidate over the reviewed file and commit.")


if __name__ == "__main__":
    main()
