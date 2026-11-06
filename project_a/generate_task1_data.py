"""Task 1 test-suite generator. Expected values come from the INDEPENDENT oracle (tests/oracle.py), never from
impl (a)/(c). Run: python -m project_a.generate_task1_data"""
import json, random
from pathlib import Path
from project_a.tests.oracle import oracle

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _case(cases, category, inp, fy, official=False):
    old, new = oracle(inp, fy)
    inp = dict(inp, fy=fy) if fy != "2024-25" else dict(inp)
    cases.append({"id": f"TC_{len(cases) + 1:03d}", "category": category, "fy": fy,
                  "official_check_candidate": official, "input": inp, "expected_old": old, "expected_new": new,
                  "expected_recommended": "tie" if old == new else ("new" if new < old else "old")})


def generate_test_cases():
    cases = []
    rnd = random.Random(42)
    # 1. reference salaries across brackets (both FYs). These are the official-calculator check candidates.
    sal = [300_000, 400_000, 500_000, 550_000, 600_000, 700_000, 750_000, 775_000, 800_000, 900_000, 1_000_000,
           1_200_000, 1_500_000, 1_800_000, 2_000_000, 2_500_000, 3_000_000, 4_000_000, 5_000_000, 5_085_000,
           5_500_000, 6_000_000, 7_500_000, 10_000_000, 10_500_000, 15_000_000, 20_000_000, 20_500_000,
           30_000_000, 50_000_000, 50_850_000, 60_000_000, 80_000_000, 100_000_000, 120_000_000]
    for s in sal:
        _case(cases, "reference", dict(gross_salary=s), "2024-25", official=True)
    # 2. boundary sweeps FY2024-25: gross = threshold + std deduction (new 75k / old 50k) +- offsets
    cliffs = [250_000 + 50_000, 300_000 + 75_000, 500_000 + 50_000, 700_000 + 75_000, 727_778 + 75_000,
              1_000_000 + 75_000, 1_200_000 + 75_000, 1_500_000 + 75_000, 5_000_000 + 75_000, 5_000_000 + 50_000,
              10_000_000 + 75_000, 20_000_000 + 75_000, 50_000_000 + 75_000]
    for c in cliffs:
        for off in (-1000, -10, -1, 0, 1, 5, 10, 1000):
            _case(cases, "boundary_sweep", dict(gross_salary=c + off), "2024-25")
    # 3. deductions, HRA, ages, caps (random but seeded) FY2024-25
    for _ in range(70):
        g = rnd.choice([800_000, 1_200_000, 1_500_000, 2_000_000, 3_000_000]); basic = int(g * rnd.uniform(0.3, 0.6))
        _case(cases, "deductions_and_age", dict(
            gross_salary=g, basic_da=basic, hra_received=int(basic * rnd.uniform(0.3, 0.5)),
            rent_paid=int(basic * rnd.uniform(0.1, 0.6)), metro_city=rnd.random() < .5,
            sec_80c=rnd.choice([0, 50_000, 150_000, 200_000]), nps_80ccd1b=rnd.choice([0, 25_000, 50_000, 75_000]),
            home_loan_interest=rnd.choice([0, 100_000, 200_000, 300_000]), age=rnd.choice([28, 59, 60, 65, 79, 80, 85]),
            health_self=rnd.choice([0, 25_000, 30_000, 50_000]), health_parents=rnd.choice([0, 25_000, 50_000, 60_000]),
            parents_senior=rnd.random() < .5), "2024-25")
    # 4. odd rupees (288A/288B) + exact-rupee mode
    for _ in range(40):
        _case(cases, "rounding", dict(gross_salary=rnd.randint(600_000, 2_500_000) + rnd.choice([1, 3, 5, 7, 9, 13]),
                                      sec_80c=rnd.choice([100_000, 150_000]), home_loan_interest=rnd.choice([0, 150_000, 200_000]),
                                      apply_288_rounding=rnd.random() < .7), "2024-25")
    # 5. FY2025-26 (Finance Act 2025): new thresholds 4/8/12/16/20/24L, 87A to 12L (+75k std), marginal relief zone
    t = [400_000, 800_000, 1_200_000, 1_600_000, 2_000_000, 2_400_000]
    for th in t:
        for off in (-10, -1, 0, 1, 10, 1000):
            _case(cases, "fy2526_boundary", dict(gross_salary=th + 75_000 + off), "2025-26", official=(off == 0))
    for g in range(1_275_000, 1_340_001, 5_000):          # marginal-relief zone just above Rs 12L taxable
        _case(cases, "fy2526_marginal_relief", dict(gross_salary=g), "2025-26")
    for g in (5_000_000, 5_075_000, 5_085_000, 10_075_000, 20_075_000, 50_075_000, 60_000_000):
        _case(cases, "fy2526_surcharge", dict(gross_salary=g), "2025-26", official=True)
    for T in (5_000_000, 10_000_000, 20_000_000, 50_000_000):     # surcharge cliffs + marginal-relief zone, both regimes
        for off in (-1000, 0, 10, 5_000, 20_000, 60_000, 150_000, 400_000):
            _case(cases, "fy2526_surcharge", dict(gross_salary=T + 75_000 + off), "2025-26")
    for _ in range(30):
        g = rnd.choice([1_000_000, 1_500_000, 2_500_000, 4_000_000]); basic = int(g * rnd.uniform(0.3, 0.6))
        _case(cases, "fy2526_deductions", dict(
            gross_salary=g, basic_da=basic, hra_received=int(basic * .4), rent_paid=int(basic * rnd.uniform(.2, .6)),
            metro_city=rnd.random() < .5, sec_80c=rnd.choice([0, 150_000]), nps_80ccd1b=rnd.choice([0, 50_000]),
            home_loan_interest=rnd.choice([0, 200_000]), age=rnd.choice([30, 62, 82]),
            health_self=rnd.choice([0, 25_000, 50_000]), health_parents=rnd.choice([0, 25_000, 50_000]),
            parents_senior=rnd.random() < .5), "2025-26")
    (DATA_DIR / "test_cases_200.json").write_text(json.dumps(cases, indent=1))
    n_off = sum(c["official_check_candidate"] for c in cases)
    print(f"Generated {len(cases)} cases ({n_off} official-calculator check candidates) -> test_cases_200.json")
    # official-calculator worksheet: the user fills the two numbers from incometax.gov.in's calculator
    ws = [{"id": c["id"], "fy": c["fy"], "input": c["input"], "official_old": None, "official_new": None}
          for c in cases if c["official_check_candidate"]]
    (DATA_DIR / "official_calculator_checks.json").write_text(json.dumps(ws, indent=1))
    return cases


if __name__ == "__main__":
    generate_test_cases()
