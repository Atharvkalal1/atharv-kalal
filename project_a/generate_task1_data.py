"""Task 1 Test Suite Generator: generates 220+ test cases and 50 plain-language scenarios."""
import json, random, math
from pathlib import Path
from project_a.common import TaxInput
from project_a.impl_a_rules import engine as A

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def generate_test_cases():
    cases = []
    cid = 1
    
    # 1. Official reference baseline cases (35 cases) across standard salary brackets
    salaries = [
        300_000, 400_000, 500_000, 550_000, 600_000, 700_000, 750_000, 775_000, 800_000,
        900_000, 1_000_000, 1_200_000, 1_500_000, 1_800_000, 2_000_000, 2_500_000,
        3_000_000, 4_000_000, 5_000_000, 5_085_000, 5_500_000, 6_000_000, 7_500_000,
        10_000_000, 10_500_000, 15_000_000, 20_000_000, 20_500_000, 30_000_000,
        50_000_000, 50_850_000, 60_000_000, 80_000_000, 100_000_000, 120_000_000
    ]
    for s in salaries:
        inp = dict(gross_salary=s)
        t_inp = TaxInput(**inp)
        r = A.compute(t_inp)
        cases.append({
            "id": f"TC_{cid:03d}",
            "category": "official_reference",
            "verify_official_calculator": True,
            "input": inp,
            "expected_old": r["old"]["total_tax"],
            "expected_new": r["new"]["total_tax"],
            "expected_recommended": r["recommendation"]["recommended"]
        })
        cid += 1

    # 2. Boundary sweeps around cliffs: 2.5L, 3L, 5L, 7L, 7.27L, 10L, 12L, 15L, 50L, 1Cr, 2Cr, 5Cr (65 cases)
    cliffs = [
        # old/new slab boundaries + standard deduction
        250_000 + 50_000, 300_000 + 75_000, 500_000 + 50_000, 700_000 + 75_000,
        727_778 + 75_000, 1_000_000 + 75_000, 1_200_000 + 75_000, 1_500_000 + 75_000,
        5_000_000 + 75_000, 10_000_000 + 75_000, 20_000_000 + 75_000, 50_000_000 + 75_000
    ]
    for cliff in cliffs:
        for offset in [-1000, -10, 0, 10, 1000]:
            s = cliff + offset
            if s <= 0: continue
            inp = dict(gross_salary=s)
            t_inp = TaxInput(**inp)
            r = A.compute(t_inp)
            cases.append({
                "id": f"TC_{cid:03d}",
                "category": "boundary_sweep",
                "verify_official_calculator": False,
                "input": inp,
                "expected_old": r["old"]["total_tax"],
                "expected_new": r["new"]["total_tax"],
                "expected_recommended": r["recommendation"]["recommended"]
            })
            cid += 1

    # 3. Deduction cap boundaries and age variations (65 cases)
    rnd = random.Random(42)
    for _ in range(65):
        g = rnd.choice([800_000, 1_200_000, 1_500_000, 2_000_000, 3_000_000])
        basic = int(g * rnd.uniform(0.3, 0.6))
        hra_rec = int(basic * rnd.uniform(0.3, 0.5))
        rent = int(basic * rnd.uniform(0.1, 0.6))
        metro = rnd.random() < 0.5
        c80 = rnd.choice([0, 50_000, 150_000, 200_000])
        nps = rnd.choice([0, 25_000, 50_000, 75_000])
        hl = rnd.choice([0, 100_000, 200_000, 300_000])
        age = rnd.choice([28, 60, 65, 80, 85])
        h_self = rnd.choice([0, 25_000, 30_000, 50_000])
        h_par = rnd.choice([0, 25_000, 50_000, 60_000])
        par_sen = rnd.random() < 0.5
        
        inp = dict(
            gross_salary=g, basic_da=basic, hra_received=hra_rec, rent_paid=rent,
            metro_city=metro, sec_80c=c80, nps_80ccd1b=nps, home_loan_interest=hl,
            age=age, health_self=h_self, health_parents=h_par, parents_senior=par_sen
        )
        t_inp = TaxInput(**inp)
        r = A.compute(t_inp)
        cases.append({
            "id": f"TC_{cid:03d}",
            "category": "deductions_and_age",
            "verify_official_calculator": False,
            "input": inp,
            "expected_old": r["old"]["total_tax"],
            "expected_new": r["new"]["total_tax"],
            "expected_recommended": r["recommendation"]["recommended"]
        })
        cid += 1

    # 4. Crossover & odd-rupee (288A/288B) cases (60 cases)
    for _ in range(60):
        g = rnd.randint(600_000, 2_500_000) + rnd.choice([1, 3, 7, 9, 13, 27])
        c80 = rnd.choice([100_000, 150_000])
        hl = rnd.choice([0, 150_000, 200_000])
        inp = dict(gross_salary=g, sec_80c=c80, home_loan_interest=hl, apply_288_rounding=True)
        t_inp = TaxInput(**inp)
        r = A.compute(t_inp)
        cases.append({
            "id": f"TC_{cid:03d}",
            "category": "crossover_and_rounding",
            "verify_official_calculator": False,
            "input": inp,
            "expected_old": r["old"]["total_tax"],
            "expected_new": r["new"]["total_tax"],
            "expected_recommended": r["recommendation"]["recommended"]
        })
        cid += 1

    out_file = DATA_DIR / "test_cases_200.json"
    out_file.write_text(json.dumps(cases, indent=2))
    print(f"Generated {len(cases)} structured test cases at {out_file.name}")
    return cases

def generate_plain_language_cases():
    prompts = [
        # 15 English complete inputs
        {"id": "PL_01", "style": "english", "text": "I earn 12 LPA gross as software engineer in Mumbai, basic 6L, pay rent 25k per month, and invest 1.5L in 80C.", "expected_action": "compute"},
        {"id": "PL_02", "style": "english", "text": "My CTC is 18,00,000 per annum, basic is 9,00,000, HRA received 3,60,000, rent paid 30,000 monthly in Bangalore (non-metro), 80C 150000, NPS 50000.", "expected_action": "compute"},
        {"id": "PL_03", "style": "english", "text": "Salary 850000 with no rent. Put 1.5L in PPF and pay 25000 health insurance for self.", "expected_action": "compute"},
        {"id": "PL_04", "style": "english", "text": "Age 32, gross salary 25 LPA, basic 12 LPA, home loan interest 200000, 80C 150000, health insurance 25000 for self and 50000 for senior citizen parents.", "expected_action": "compute"},
        {"id": "PL_05", "style": "english", "text": "Gross 7.5 LPA, no deductions claimed. Tell me which regime is better.", "expected_action": "compute"},
        {"id": "PL_06", "style": "english", "text": "Senior citizen age 64 working as consultant, annual salary 14,00,000, 80C 1.5 lakh, health insurance 50,000.", "expected_action": "compute"},
        {"id": "PL_07", "style": "english", "text": "Annual package 10 Lakhs, basic 5 Lakhs, HRA 2 Lakhs, paying 18000 rent monthly in Delhi, 80C 1.2 Lakhs.", "expected_action": "compute"},
        {"id": "PL_08", "style": "english", "text": "Gross salary 55 Lakhs, basic 25 Lakhs, no rent, maximum 80C and NPS 50000. Check surcharge impact.", "expected_action": "compute"},
        {"id": "PL_09", "style": "english", "text": "I have 6.5 lakh gross salary, live in own house, 80C investment of 70000.", "expected_action": "compute"},
        {"id": "PL_10", "style": "english", "text": "Earning 15 LPA in Chennai, basic 7.5L, HRA 3L, rent 22000 per month, 80C 1.5L, health self 20000.", "expected_action": "compute"},
        {"id": "PL_11", "style": "english", "text": "Gross 1.05 Crore, basic 50 Lakhs, claiming 80C 1.5L and home loan 2L. Check 15% surcharge marginal relief.", "expected_action": "compute"},
        {"id": "PL_12", "style": "english", "text": "Salary 9.5 LPA, basic 4.75L, HRA 2L, paying 15k rent monthly in Kolkata. 80C 1.5L.", "expected_action": "compute"},
        {"id": "PL_13", "style": "english", "text": "Super senior citizen age 82, pension/salary income 12,00,000, health insurance 50000.", "expected_action": "compute"},
        {"id": "PL_14", "style": "english", "text": "Gross salary 22 LPA, basic 11 LPA, paying 35000 rent in Gurgaon (non-metro), 80C 150000, 80CCD 50000.", "expected_action": "compute"},
        {"id": "PL_15", "style": "english", "text": "Gross 4,50,000 per year with no investments.", "expected_action": "compute"},

        # 12 Hinglish complete inputs
        {"id": "PL_16", "style": "hinglish", "text": "Meri annual salary 14 lakh hai, basic 7 lakh, Pune me 22000 per month rent deta hu aur 80C me 1.5L invest kiya hai.", "expected_action": "compute"},
        {"id": "PL_17", "style": "hinglish", "text": "Package 18 LPA hai, Delhi me rehta hu aur 30k rent pay karta hu, HRA 3.6L milta hai, basic 9L hai. PPF me 1.5L daala hai.", "expected_action": "compute"},
        {"id": "PL_18", "style": "hinglish", "text": "Mera gross package 8 lakh hai, koi rent nahi deta, 80C full 1.5 lakh kiya hai.", "expected_action": "compute"},
        {"id": "PL_19", "style": "hinglish", "text": "Salary 22 lakh hai Mumbai me, basic 11 lakh, HRA 4.4L, rent 40k monthly, home loan interest 2 lakh hai.", "expected_action": "compute"},
        {"id": "PL_20", "style": "hinglish", "text": "CTC 12 LPA, basic 6 LPA, HRA 2.4 LPA, Kolkata me 18000 rent deta hu, NPS me 50k invest kiya.", "expected_action": "compute"},
        {"id": "PL_21", "style": "hinglish", "text": "Meri salary 6.5 lakh hai, koi deduction nahi hai, tax kitna lagega dono regime me?", "expected_action": "compute"},
        {"id": "PL_22", "style": "hinglish", "text": "Age 35 hai, salary 16 lakh, basic 8L, Bangalore me 25k mahina rent, 80C 1.5L aur parents senior citizen hain unka 40k health insurance.", "expected_action": "compute"},
        {"id": "PL_23", "style": "hinglish", "text": "Mera package 30 lakh hai, basic 15L, home loan 2 lakh interest hai aur 80C me 1.5L.", "expected_action": "compute"},
        {"id": "PL_24", "style": "hinglish", "text": "Salary 10.5 lakh hai, basic 5 lakh, 15k rent monthly Hyderabad me deta hu, 80C me 1 lakh.", "expected_action": "compute"},
        {"id": "PL_25", "style": "hinglish", "text": "Gross 5.5 lakh per year hai, koi bachat ya rent nahi hai, konsa regime better hai?", "expected_action": "compute"},
        {"id": "PL_26", "style": "hinglish", "text": "Salary 15 lakh, basic 7.5L, Chennai metro me 25000 rent, 80C 150000, 80CCD1B 50000, medical self 25000.", "expected_action": "compute"},
        {"id": "PL_27", "style": "hinglish", "text": "Age 62 senior citizen, salary 11 lakh, basic 5.5L, rent 20k Noida me, 80C 1.5L, health insurance 50k.", "expected_action": "compute"},

        # 13 Incomplete / Ambiguous inputs (Must clarify)
        {"id": "PL_28", "style": "incomplete", "text": "I earn 12 Lakhs per annum. Which regime is better?", "expected_action": "clarify"},
        {"id": "PL_29", "style": "incomplete", "text": "I am claiming HRA on my 15 LPA salary.", "expected_action": "clarify"},
        {"id": "PL_30", "style": "incomplete", "text": "My CTC is 18 LPA and I pay rent in Bangalore.", "expected_action": "clarify"},
        {"id": "PL_31", "style": "incomplete", "text": "I have salary 9 Lakhs and paid 40,000 for insurance.", "expected_action": "clarify"},
        {"id": "PL_32", "style": "incomplete", "text": "Meri salary 14 lakh hai aur maine bachat ki hai, tax batao.", "expected_action": "clarify"},
        {"id": "PL_33", "style": "incomplete", "text": "Paying rent of 25,000 monthly, what tax will I save?", "expected_action": "clarify"},
        {"id": "PL_34", "style": "incomplete", "text": "Gross 20 LPA, basic 10 LPA, please compare both tax regimes.", "expected_action": "clarify"},
        {"id": "PL_35", "style": "incomplete", "text": "I bought a house and paying EMI, calculate my tax on 16 LPA.", "expected_action": "clarify"},
        {"id": "PL_36", "style": "incomplete", "text": "Package 8 lakh, HRA 2 lakh milta hai, kitna tax bachega?", "expected_action": "clarify"},
        {"id": "PL_37", "style": "incomplete", "text": "I am a retired senior citizen with some pension.", "expected_action": "clarify"},
        {"id": "PL_38", "style": "incomplete", "text": "Salary 11 LPA, invested in mutual funds.", "expected_action": "clarify"},
        {"id": "PL_39", "style": "incomplete", "text": "Rent receipt 30k per month hai Mumbai me, salary 15 LPA, tax kitna banega?", "expected_action": "clarify"},
        {"id": "PL_40", "style": "incomplete", "text": "Tax on 50 Lakhs salary under old vs new regime.", "expected_action": "clarify"},

        # 10 Contradictory / Invalid inputs (Must clarify)
        {"id": "PL_41", "style": "contradictory", "text": "My basic salary is 15 Lakhs and my total gross CTC is 10 Lakhs.", "expected_action": "clarify"},
        {"id": "PL_42", "style": "contradictory", "text": "I am 24 years old and claiming senior citizen rebate for myself on 12 LPA salary.", "expected_action": "clarify"},
        {"id": "PL_43", "style": "contradictory", "text": "My gross salary is -500,000 per year.", "expected_action": "clarify"},
        {"id": "PL_44", "style": "contradictory", "text": "Gross salary is 8 LPA, basic 4 LPA, and I pay 10 Lakhs rent per year.", "expected_action": "clarify"},
        {"id": "PL_45", "style": "contradictory", "text": "Meri salary 12 lakh hai aur basic salary 18 lakh hai.", "expected_action": "clarify"},
        {"id": "PL_46", "style": "contradictory", "text": "Age 15 years old school student earning 20 LPA salary.", "expected_action": "clarify"},
        {"id": "PL_47", "style": "contradictory", "text": "Claiming 5,00,000 under section 80C and claiming 0 gross salary.", "expected_action": "clarify"},
        {"id": "PL_48", "style": "contradictory", "text": "Paying -20000 rent per month on 15 LPA salary.", "expected_action": "clarify"},
        {"id": "PL_49", "style": "contradictory", "text": "I live in my own house with no rent paid but want full HRA exemption of 3 Lakhs on 12 LPA.", "expected_action": "clarify"},
        {"id": "PL_50", "style": "contradictory", "text": "Age 28, gross 10L, basic 5L, claiming 80D senior citizen self deduction of 50000 for myself.", "expected_action": "clarify"}
    ]
    out_file = DATA_DIR / "plain_language_50.json"
    out_file.write_text(json.dumps(prompts, indent=2))
    print(f"Generated {len(prompts)} plain-language scenarios at {out_file.name}")
    return prompts

if __name__ == "__main__":
    generate_test_cases()
    generate_plain_language_cases()
