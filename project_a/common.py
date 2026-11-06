"""Shared types and helpers used by all three implementations."""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, asdict
from fractions import Fraction
from pathlib import Path


def round_rupee(x) -> int:
    """Round to the nearest rupee, halves up. Exact (Fraction) arithmetic, no float drift."""
    return math.floor(Fraction(x) + Fraction(1, 2))


def round_to_10(x) -> int:
    """Sections 288A/288B: nearest multiple of Rs 10, a halfway '5' rounds up."""
    return int((round_rupee(x) + 5) // 10 * 10)


def fy_slug(fy: str) -> str:
    return fy.replace("-", "_")


@dataclass
class TaxInput:
    """Structured input. All money values are annual rupees."""
    gross_salary: int                 # total gross salary incl. HRA, before any deduction
    fy: str = "2024-25"
    basic_da: int = 0                 # legacy: annual 'salary' for Rule 2A. Wins over the 3 fields below if > 0
    hra_received: int = 0
    rent_paid: int = 0                # annual rent actually paid
    metro_city: bool = False          # Delhi, Mumbai, Kolkata, Chennai
    age: int = 30                     # age at end of the FY
    sec_80c: int = 0                  # amount invested/paid (cap applied by the engine)
    nps_80ccd1b: int = 0
    health_self: int = 0              # 80D premium: self, spouse, children
    health_parents: int = 0           # 80D premium: parents
    parents_senior: bool = False      # any parent aged 60+
    home_loan_interest: int = 0       # self-occupied house, interest paid in the FY
    basic_salary: int = 0             # Rule 2A: basic
    da_eligible: int = 0              # Rule 2A: DA forming part of retirement benefits
    commission_turnover: int = 0      # Rule 2A: commission as a fixed % of turnover
    apply_288_rounding: bool = True   # False = exact-rupee mode (for verification)

    @property
    def hra_salary_base(self) -> int:
        """'Salary' for HRA under Rule 2A."""
        return self.basic_da if self.basic_da > 0 else (self.basic_salary + self.da_eligible + self.commission_turnover)

    def validate(self) -> "TaxInput":
        for k, v in self.to_dict().items():
            if k in ("fy", "metro_city", "parents_senior", "apply_288_rounding"):
                continue
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(f"{k} must be a non-negative integer, got {v!r}")
        if not 18 <= self.age <= 120:
            raise ValueError("age out of range")
        if self.hra_salary_base > self.gross_salary or self.hra_received > self.gross_salary:
            raise ValueError("HRA salary base / hra_received cannot exceed gross_salary")
        return self

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hra_salary_base"] = self.hra_salary_base
        return d


# ----------------------------------------------------------------------------- traceability
DEDUCTION_STEPS = ("hra_ex", "std", "hp", "d80c", "d80ccd", "d80d_self", "d80d_par")
_FIELD_OF_STEP = {"raw_taxable": "raw_taxable_income", "taxable": "taxable_income", "slab_tax": "tax_on_slabs",
                  "rebate": "rebate_87a", "raw_surcharge": "raw_surcharge",
                  "surcharge_marginal_relief": "surcharge_marginal_relief", "surcharge": "surcharge",
                  "cess": "cess", "raw_total": "raw_total_tax", "total": "total_tax"}
_REQUIRED = ("gross_salary", "raw_taxable_income", "taxable_income", "tax_on_slabs", "rebate_87a", "raw_surcharge",
             "surcharge_marginal_relief", "surcharge", "cess", "raw_total_tax", "total_tax")


def load_valid_clauses(fy: str = "2024-25") -> set[str]:
    """Clause IDs defined in rules_text/fy<slug>.md (lines that start with 'R-...')."""
    text = (Path(__file__).parent / "rules_text" / f"fy{fy_slug(fy)}.md").read_text()
    return set(re.findall(r"^(R-[A-Z0-9]+(?:-[A-Z0-9]+)*)", text, re.M))


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def verify_traceability(regime_result: dict, valid_clauses: set[str]) -> dict:
    """Audit one regime result. Checks (a) clause validity, (b) deductions == gross - raw taxable,
    (c) components reconcile with total_tax (incl. R-288B), plus trace rows == headline fields."""
    r, errs = regime_result, []
    trace = r.get("trace") or []
    if not trace:
        errs.append("empty trace")
    for t in trace:
        clause = str(t.get("clause", "")).strip()
        parts = [c.strip() for c in clause.split("/")] if clause else []
        if not parts:
            errs.append(f"step '{t.get('step')}' has no clause")
        for c in parts:
            if c not in valid_clauses:
                errs.append(f"step '{t.get('step')}' cites unknown clause '{c}'")
        if not _is_int(t.get("amount")):
            errs.append(f"step '{t.get('step')}' amount is not an integer")
    bad = [k for k in _REQUIRED if not _is_int(r.get(k))]
    if bad:
        errs.append("missing/non-integer fields: " + ", ".join(bad))
        return {"fully_traceable": False, "trace_errors": errs}
    steps = {}
    for t in trace:
        if t.get("step") in steps and t.get("step") in _FIELD_OF_STEP:
            errs.append(f"duplicate trace step '{t['step']}'")
        steps[t.get("step")] = t.get("amount")
    applied = r.get("rounding_288_applied", True)
    # trace rows must equal the headline numbers (every rupee in the answer is in the trace)
    for step, field in _FIELD_OF_STEP.items():
        if step == "surcharge_marginal_relief" and r[field] == 0 and step not in steps:
            continue
        if step not in steps:
            errs.append(f"trace has no '{step}' step")
        elif steps[step] != r[field]:
            errs.append(f"trace step '{step}' = {steps[step]} but {field} = {r[field]}")
    # (b) deductions
    ded = sum(a for s, a in steps.items() if s in DEDUCTION_STEPS and _is_int(a))
    gap = r["gross_salary"] - r["raw_taxable_income"]
    if r["raw_taxable_income"] > 0 and ded != gap:
        errs.append(f"deductions {ded} != gross_salary - raw_taxable_income ({gap})")
    if r["raw_taxable_income"] == 0 and ded < r["gross_salary"]:
        errs.append(f"taxable income is 0 but deductions {ded} < gross_salary {r['gross_salary']}")
    # 288A / 288B
    exp_ti = round_to_10(r["raw_taxable_income"]) if applied else r["raw_taxable_income"]
    if r["taxable_income"] != exp_ti:
        errs.append(f"taxable_income {r['taxable_income']} != expected {exp_ti} (R-288A applied={applied})")
    # (c) reconcile
    recon = r["tax_on_slabs"] - r["rebate_87a"] + r["surcharge"] + r["cess"]
    if recon != r["raw_total_tax"]:
        errs.append(f"slab - rebate + surcharge + cess = {recon} != raw_total_tax {r['raw_total_tax']}")
    exp_tt = round_to_10(r["raw_total_tax"]) if applied else r["raw_total_tax"]
    if r["total_tax"] != exp_tt:
        errs.append(f"total_tax {r['total_tax']} != expected {exp_tt} (R-288B applied={applied})")
    if r["total_tax"] != r["raw_total_tax"] and "rounding_288b" not in steps:
        errs.append("R-288B rounding changed the total but no 'rounding_288b' trace step")
    if "rounding_288b" in steps and steps["rounding_288b"] != r["total_tax"] - r["raw_total_tax"]:
        errs.append("rounding_288b step does not equal total_tax - raw_total_tax")
    if r["raw_surcharge"] - r["surcharge_marginal_relief"] != r["surcharge"]:
        errs.append("raw_surcharge - surcharge_marginal_relief != surcharge")
    return {"fully_traceable": not errs, "trace_errors": errs}


def attach_traceability(regime_result: dict, fy: str = "2024-25") -> dict:
    regime_result.update(verify_traceability(regime_result, load_valid_clauses(fy)))
    return regime_result


# ----------------------------------------------------------------------------- recommendation
_NOT_DRIVERS = {"taxable", "raw_taxable", "total", "raw_total"}
_DEDUCTIONS_OLD = ("hra_ex", "hp", "d80c", "d80ccd", "d80d_self", "d80d_par")


def _clauses(*results: dict) -> list[str]:
    out = set()
    for res in results:
        for t in res.get("trace", []):
            if t.get("step") in _NOT_DRIVERS or not t.get("amount"):
                continue
            out.update(c.strip() for c in str(t.get("clause", "")).split("/") if c.strip().startswith("R-"))
    return sorted(out)


def recommend(old: dict, new: dict) -> dict:
    """Cheaper regime ('tie' if equal), the saving, a reason, and the R-... clauses driving the numbers."""
    o, n = old["total_tax"], new["total_tax"]
    if n == o:
        choice, saving = "tie", 0
        reason = f"Both regimes give Rs {n:,}. The new regime is the default if you do not opt out."
    else:
        choice, saving = ("new", o - n) if n < o else ("old", n - o)
        reason = f"New regime tax Rs {n:,}; old regime tax Rs {o:,}. {choice.capitalize()} regime is cheaper by Rs {saving:,}."
    drivers = {t["step"]: t["amount"] for t in old.get("trace", [])
               if t.get("step") in _DEDUCTIONS_OLD and t.get("amount")}
    if drivers:
        reason += " Old-regime deductions counted: " + ", ".join(f"{k}=Rs {v:,}" for k, v in drivers.items()) + "."
    return {"recommended": choice, "saving": saving, "reason": reason, "clause_citations": _clauses(old, new)}


def safe_recommend(old: dict, new: dict) -> dict:
    try:
        return recommend(old, new)
    except (KeyError, TypeError):
        return {"recommended": None, "saving": 0, "reason": "result malformed; no recommendation",
                "clause_citations": []}
