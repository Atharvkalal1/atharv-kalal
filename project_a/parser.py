"""Task 3: plain-language -> TaxInput, with clarifying questions instead of guesses.

Architecture (extract -> gate):
  1. EXTRACT facts from text. Two interchangeable extractors producing the same `facts` dict:
       - extract_rules(text): deterministic clause-level regex extractor (offline, free, reproducible)
       - extract_llm(text):   Gemini JSON extractor (needs GEMINI_API_KEY); used for text the rules cannot read
  2. GATE (always rules, never an LLM): validates, detects contradictions / missing / ambiguous facts and either
     returns status "ok" (+ explicit `assumptions`) or "needs_clarification" with questions.
The LLM may only *extract*; it never decides whether it is safe to compute. Nothing is silently defaulted
(the only default is age<60 when age is absent, and it is reported in `assumptions`).
"""
from __future__ import annotations
import json, os, re
from pathlib import Path
from project_a.common import TaxInput

METRO = {"delhi", "new delhi", "mumbai", "kolkata", "chennai"}
NON_METRO = {"bangalore", "bengaluru", "pune", "hyderabad", "ahmedabad", "gurgaon", "gurugram", "noida", "jaipur",
             "lucknow", "chandigarh", "indore", "kochi", "surat", "nagpur", "thane", "bhopal", "patna", "ghaziabad"}
_UNIT = {"crore": 1e7, "cr": 1e7, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "lpa": 1e5, "l": 1e5,
         "k": 1e3, "thousand": 1e3, "hazaar": 1e3}
AMT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(crore|cr|lakhs?|lacs?|lpa|l|k|thousand|hazaar)?\b")
PARENT = r"parents?|mummy|papa|mother|father|maa|baap"
NEG_NO_RENT = [r"\b(?:with\s+|and\s+)?no\s+rent\b", r"\bkoi\s+rent\s+nahi\b", r"\brent\s+(?:nahi|nahin)\b",
               r"\bwithout\s+rent\b", r"\bya\s+rent\s+nahi\b"]
NEG_NO_DED = [r"\bno\s+(?:other\s+)?(?:deductions?|investments?|savings?|exemptions?)\b", r"\bno\s+(?:80c|80d|nps)\b", r"\bzero\s+deductions?\b",
              r"\bkoi\s+(?:deduction|bachat|investment)(?:\s+ya\s+rent)?\s+(?:nahi|nahin)\b",
              r"\b(?:deductions?|bachat)\s+(?:nahi|nahin)\b", r"\bnothing\s+to\s+claim\b"]
NEG_NO_HRA = [r"\bno\s+hra\b", r"\bhra\s+(?:nahi|nahin)(?:\s+milta)?\b", r"\bwithout\s+hra\b"]
OWN = r"\bown\s+(?:my\s+)?(?:house|flat|home)\b|\bapn[ae]\s+ghar\b|\bapna\s+ghar\b"
MONTHLY = r"per\s*month|monthly|\bpm\b|p\.m\.|mahin[ae]|a\s+month|/\s*month|\bmonth\b"
ANNUAL = r"per\s*annum|annual(?:ly)?|yearly|per\s*year|\bp\.?a\.?\b|saal|\bannum\b|a\s+year"


def _money(m):
    from decimal import Decimal  # exact: 2.3 lakh must be 230000, not 229999.99999999997
    return Decimal(m.group(1)) * int(_UNIT.get((m.group(2) or "").lower(), 1))


def _blank_facts() -> dict:
    return dict(gross=None, basic=None, hra=None, rent_amount=None, rent_period=None, city=None, age=None,
                c80=None, nps=None, hl=None, hs=None, hp=None, parents_senior=None,
                flags=dict(no_rent=False, no_ded=False, no_hra=False, own_house=False, negative=False, insurance_unspecified=False,
                           mf_unspecified=False, emi_no_interest=False, hl_no_interest=False, missing_amount=[],
                           senior_claim_self=False, hra_exemption_claim=False, rent_mentioned=False))


def extract_rules(text: str) -> dict:
    f, fl = _blank_facts(), None
    fl = f["flags"]
    t = re.sub(r"(?<=\d),(?=\d)", "", text.lower().replace("₹", " ").replace("rs.", " ").replace("rs ", " "))
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    if re.search(r"(?<![\w])-\s*\d", t):
        fl["negative"] = True
    for pat in NEG_NO_RENT:
        if re.search(pat, t): fl["no_rent"] = True
    for pat in NEG_NO_DED:
        if re.search(pat, t): fl["no_ded"] = True
    for pat in NEG_NO_HRA:
        if re.search(pat, t): fl["no_hra"] = True
    if re.search(OWN, t): fl["own_house"] = True
    for pat in NEG_NO_RENT + NEG_NO_DED + NEG_NO_HRA:
        t = re.sub(pat, " ", t)
    # city
    for c in sorted(METRO | NON_METRO, key=len, reverse=True):
        if re.search(rf"\b{c}\b", t):
            f["city"] = "metro" if c in METRO else "non_metro"; break
    if re.search(r"non[\s-]?metro", t): f["city"] = "non_metro"
    elif f["city"] is None and re.search(r"\bmetro\b", t): f["city"] = "metro"
    # age
    m = (re.search(r"\bage[d]?\s*(?:is|:|=)?\s*(\d{1,3})\b", t) or re.search(r"\b(\d{1,3})\s*(?:years?|yrs?|saal|sal|yo)\b(?:\s*old)?", t)
         or re.search(r"\b(?:i am|i'm|im)\s+(\d{2})\b", t) or re.search(r"\bumar\s*(\d{1,3})\b", t))
    if m: f["age"] = int(m.group(1))
    if re.search(rf"(?:{PARENT}).{{0,40}}senior|senior.{{0,40}}(?:{PARENT})", t): f["parents_senior"] = True
    if re.search(r"hra\s+exemption|exemption\s+(?:of\s+)?(?:\d.{0,12})?hra", t): fl["hra_exemption_claim"] = True
    # clauses
    clauses = [c.strip() for c in re.split(r"[;,?!]|\.(?=\s|$)|\band\b|\baur\b|\bbut\b|\bwhile\b", t) if c.strip()]
    last = None
    for c in clauses:
        nums = [m for m in AMT.finditer(c) if not re.match(r"\s*%", c[m.end():])]
        amt = int(_money(nums[0])) if nums else None
        has = lambda *w: any(re.search(rf"\b{x}", c) for x in w)
        field = None
        if has(PARENT) and (has("health", "medical", "insurance", "mediclaim", "80d") or last in ("hs", "hp")) and amt is not None:
            field = "hp"
        elif has("basic"): field = "basic"
        elif has("hra", "house rent allowance"): field = "hra"
        elif has("rent", "kiraya", "kiraye"): field = "rent"
        elif has("80c", "ppf", "elss", "epf", "provident", "pf"): field = "c80"
        elif has("nps", "80ccd"): field = "nps"
        elif has("home loan", "housing loan", "loan interest", "homeloan"):
            field = "hl"
            if not has("interest", "byaj", "vyaj") and amt is not None: fl["hl_no_interest"] = True; amt = None; field = None
        elif has("emi"):
            fl["emi_no_interest"] = True; field = None
        elif has("health", "medical", "mediclaim", "80d"): field = "hs"
        elif has("insurance", "premium"):
            if amt is not None: fl["insurance_unspecified"] = True
        elif has("mutual fund", "mutual funds"):
            fl["mf_unspecified"] = True
        elif has("gross", "ctc", "package", "salary", "earn", "income", "pension", "lpa", "annual", "make", "paid me", "get"): field = "gross"
        if re.search(r"senior\s+citizen|senior\s+slab|senior\s+rebate", c) and not has(PARENT) and field != "hs":
            fl["senior_claim_self"] = True
        if field is None:
            continue
        if amt is None:
            if field == "c80" and has("max", "maximum", "full"): amt = 150000
            elif field in ("c80", "nps", "hl", "hs", "hp"): fl["missing_amount"].append(field); last = field; continue
            elif field == "rent": fl["rent_mentioned"] = True; last = field; continue
            else: continue
        if field == "c80" and has("max", "maximum", "full") and nums and _money(nums[0]) == 1.5e5: pass
        if field == "hs" and (has("senior") and not has(PARENT)): fl["senior_claim_self"] = fl["senior_claim_self"] or has("claim")
        if field == "gross" and re.search(MONTHLY, c) and not re.search(ANNUAL, c):
            amt *= 12          # explicitly stated as monthly -> annualise (stated, not guessed)
        if field == "rent":
            fl["rent_mentioned"] = True
            f["rent_amount"] = amt
            f["rent_period"] = "monthly" if re.search(MONTHLY, c) else "annual" if re.search(ANNUAL, c) else None
        else:
            if f.get(field) is None: f[field] = amt
        last = field
    if fl["rent_mentioned"] and f["rent_amount"] is None and not fl["no_rent"]: fl["missing_amount"].append("rent")
    # 'senior citizen' / 'retired' hints on the taxpayer
    f["_senior_hint"] = bool(re.search(r"senior\s+citizen|retired|pensioner", t)) and not re.search(rf"(?:{PARENT}).{{0,40}}senior|senior.{{0,40}}(?:{PARENT})", t)
    return f


FACT_SCHEMA = ("Return JSON with keys: gross, basic, hra, rent_amount (number as stated), rent_period ('monthly'|'annual'|null), "
               "city ('metro' for Delhi/Mumbai/Kolkata/Chennai, 'non_metro' otherwise, null if no city), age, c80, nps, hl (home-loan INTEREST only), "
               "hs, hp, parents_senior (bool|null), flags {no_rent, no_ded, no_hra, own_house, negative, insurance_unspecified, mf_unspecified, "
               "emi_no_interest, hl_no_interest, missing_amount (list of field names mentioned without an amount), senior_claim_self, hra_exemption_claim, rent_mentioned}. "
               "All money in annual rupees EXCEPT rent_amount. Use null for anything not stated. NEVER guess or infer a number that is not in the text.")


def extract_llm(text: str) -> dict:
    from project_a import gemini_client as G
    out, _ = G.generate_json(f"Extract tax facts from this message (English/Hinglish).\n{FACT_SCHEMA}\n\nMESSAGE: {text}",
                             system="You extract facts only. You never compute tax and never guess missing values.")
    f = _blank_facts(); fl = f["flags"]
    for k in f:
        if k != "flags" and k in out: f[k] = out[k]
    fl.update({k: v for k, v in (out.get("flags") or {}).items() if k in fl})
    f["_senior_hint"] = False
    return f


def _ask(reasons, questions):
    return {"status": "needs_clarification", "input": None, "reasons": reasons, "clarifying_questions": questions}


def gate(f: dict) -> dict:
    """Deterministic decision on extracted facts. Order = severity."""
    fl, R, Q = f["flags"], [], []
    def need(r, q): R.append(r); Q.append(q)
    n = lambda k: f[k] or 0
    if fl["negative"]: need("Negative amount or age.", "Some values look negative. Please re-enter salary, rent and deductions as positive numbers.")
    if f["gross"] is None: need("Gross salary not given.", "What is your total annual gross salary (CTC)?")
    elif f["gross"] < 10_000: need(f"Gross salary {f['gross']} looks too small.", "Is your gross salary monthly or annual, and what is the annual amount?")
    if f["age"] is not None and f["age"] < 18: need(f"Age {f['age']} is below 18.", "Please confirm your age (salaried individuals are 18+).")
    if f["gross"]:
        g = f["gross"]
        if n("basic") > g: need(f"Basic {n('basic'):,} exceeds gross {g:,}.", "Basic cannot exceed gross salary. Which of the two numbers is wrong?")
        if n("hra") > g: need("HRA exceeds gross.", "HRA received cannot exceed gross salary. Please re-check it.")
        for k, lab in (("c80", "80C"), ("nps", "NPS"), ("hl", "home-loan interest"), ("hs", "health insurance"), ("hp", "parents' health insurance")):
            if n(k) > g: need(f"{lab} {n(k):,} exceeds gross.", f"The {lab} amount exceeds your salary. Please re-check it.")
    if fl["senior_claim_self"] and (f["age"] is None or f["age"] < 60) and not f["parents_senior"] is True:
        need("Senior-citizen benefit claimed for self but age is " + ("unknown." if f["age"] is None else f"{f['age']}."),
             "Senior-citizen benefits need age 60+. What is your age, and is the claim for you or your parents?")
    elif fl["senior_claim_self"] and f["age"] is not None and f["age"] < 60:
        need("Senior-citizen claim for self with age < 60.", "You mentioned a senior-citizen benefit but your age is under 60. Is it for your parents?")
    if fl["hra_exemption_claim"] and (fl["own_house"] or fl["no_rent"]):
        need("HRA exemption claimed but no rent is paid.", "HRA exemption needs rent actually paid. Do you pay rent to anyone?")
    if fl["insurance_unspecified"]: need("Insurance type unclear.", "Is the insurance premium health (80D) or life (80C)? If health, for self or parents?")
    if fl["mf_unspecified"]: need("Mutual funds: ELSS unknown.", "Are the mutual funds ELSS (tax-saving, 80C)? How much was invested?")
    if fl["emi_no_interest"] or fl["hl_no_interest"]: need("Home loan interest not given.", "What is the interest portion paid on the home loan this year (24b)?")
    for k in dict.fromkeys(fl["missing_amount"]): need(f"'{k}' mentioned without an amount.", f"How much did you pay/invest for {k}?")
    rent = None
    if f["rent_amount"] is not None and not fl["no_rent"]:
        if f["rent_period"] is None: need("Rent period unclear.", "Is the rent amount monthly or annual?")
        else: rent = f["rent_amount"] * (12 if f["rent_period"] == "monthly" else 1)
        if rent and f["gross"] and rent > f["gross"]: need("Annual rent exceeds salary.", "Annual rent is above your salary. Is that amount monthly or annual?")
    if rent:
        if f["hra"] is None and not fl["no_hra"]: need("HRA received unknown.", "How much HRA does your employer pay annually (0 if none)?")
        if (f["hra"] or 0) > 0:
            if f["basic"] is None: need("Basic salary unknown (needed for HRA).", "What is your annual basic salary (+DA)?")
            if f["city"] is None: need("City unknown (metro or not).", "Which city do you live in? (Delhi/Mumbai/Kolkata/Chennai count as metro.)")
    elif (f["hra"] or 0) > 0 and not (fl["own_house"] or fl["no_rent"]) and f["rent_amount"] is None:
        need("HRA given but rent unknown.", "How much rent do you pay (monthly or annual)?")
    if n("hp") > 0 and f["parents_senior"] is None: need("Parents' age unknown.", "Are your parents aged 60 or above? (changes the 80D limit)")
    if f["age"] is None and f.get("_senior_hint"): need("Senior-citizen status unclear.", "What is your age?")
    silent = not any([f["c80"], f["nps"], f["hl"], f["hs"], f["hp"], rent, f["hra"], fl["no_ded"], fl["no_rent"], fl["no_hra"], fl["own_house"]])
    if silent and f["gross"] and not R:
        need("Nothing said about deductions, rent or investments.",
             "To choose between regimes: do you pay rent/HRA, invest in 80C/NPS, pay health insurance or home-loan interest? (Say 'none' if not.)")
    if R: return _ask(R, Q)
    assumptions = [] if f["age"] is not None else ["age assumed below 60 (not stated)"]
    if not (f["c80"] or f["nps"] or f["hl"] or f["hs"] or f["hp"] or rent): assumptions.append("no old-regime deductions (stated)")
    inp = TaxInput(gross_salary=f["gross"], basic_da=n("basic"), hra_received=n("hra"), rent_paid=rent or 0,
                   metro_city=f["city"] == "metro", age=f["age"] if f["age"] is not None else 30, sec_80c=n("c80"),
                   nps_80ccd1b=n("nps"), health_self=n("hs"), health_parents=n("hp"), parents_senior=bool(f["parents_senior"]),
                   home_loan_interest=n("hl"))
    return {"status": "ok", "input": inp, "extracted": inp.to_dict(), "assumptions": assumptions,
            "clarifying_questions": [], "age_stated": f["age"] is not None}


def parse_plain_language(text: str, use_llm: bool = False) -> dict:
    f = extract_llm(text) if use_llm else extract_rules(text)
    r = gate(f); r["mode"] = "llm_extract+rule_gate" if use_llm else "rules_extract+rule_gate"; r["facts"] = f
    return r


# ----------------------------------------------------------------------------- evaluation
FIELDS = ("gross_salary", "basic_da", "hra_received", "rent_paid", "metro_city", "sec_80c", "nps_80ccd1b",
          "health_self", "health_parents", "parents_senior", "home_loan_interest")
DEFAULTS = {k: 0 for k in FIELDS} | {"metro_city": False, "parents_senior": False}


def evaluate_parser(files=("plain_language_50.json", "plain_language_holdout_30.json"), use_llm=False, verbose=True) -> dict:
    out = {}
    for fn in files:
        p = Path(__file__).parent / "data" / fn
        if not p.exists(): continue
        cases = json.loads(p.read_text())
        a = dict(n=len(cases), action_ok=0, false_compute=0, false_clarify=0, compute_n=0, fields_exact=0, age_ok=0)
        for c in cases:
            r = parse_plain_language(c["text"], use_llm=use_llm)
            act = "compute" if r["status"] == "ok" else "clarify"
            if act == c["expected_action"]: a["action_ok"] += 1
            elif act == "compute": a["false_compute"] += 1
            else: a["false_clarify"] += 1
            if verbose and act != c["expected_action"]:
                print(f"  [{fn[:14]}] {c['id']} expected {c['expected_action']}, got {act}: {c['text'][:90]}")
            if c["expected_action"] == "compute":
                a["compute_n"] += 1
                if r["status"] == "ok":
                    exp = DEFAULTS | c["expected_fields"]; got = r["extracted"]
                    a["fields_exact"] += all(got[k] == exp[k] for k in FIELDS)
                    if "age" in c["expected_fields"]: a["age_ok"] += got["age"] == c["expected_fields"]["age"]
        out[fn] = a
        if verbose:
            print(f"Parser {fn}: action acc {a['action_ok']}/{a['n']}, false-compute {a['false_compute']} (guessing), "
                  f"false-clarify {a['false_clarify']}, field-exact {a['fields_exact']}/{a['compute_n']}")
    return out


if __name__ == "__main__":
    evaluate_parser()
