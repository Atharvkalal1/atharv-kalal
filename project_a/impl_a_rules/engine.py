"""Implementation (a): hand-coded rules. Numbers live in rules_<fy>.json, logic lives here."""
from __future__ import annotations
import json
from fractions import Fraction
from pathlib import Path

from project_a.common import (TaxInput, round_rupee, round_to_10, fy_slug, attach_traceability, recommend)

_DIR = Path(__file__).parent


def load_rules(fy: str) -> dict:
    p = _DIR / f"rules_fy{fy_slug(fy)}.json"
    if not p.exists():
        raise ValueError(f"No rules file for FY {fy}: {p.name}")
    return json.loads(p.read_text())


def slab_tax(income: int, slabs) -> Fraction:
    tax, lower = Fraction(0), 0
    for upper, rate in slabs:
        top = income if upper is None else min(income, upper)
        if top > lower:
            tax += Fraction(top - lower) * rate / 100
        if upper is None or income <= upper:
            break
        lower = upper
    return tax


def surcharge(income: int, tax: int, slabs, thresholds, max_rate: int) -> tuple[int, int]:
    """Returns (raw_surcharge, marginal_relief); net surcharge = raw - relief."""
    rate, before, T = 0, 0, None
    for thr, r in thresholds:
        if income > thr:
            before, rate, T = rate, min(r, max_rate), thr
    if rate == 0:
        return 0, 0
    full = Fraction(tax) * rate / 100
    tax_at_T = round_rupee(slab_tax(T, slabs))
    cap = Fraction(tax_at_T) * (100 + before) / 100 + (income - T) - tax   # marginal relief limit
    raw = round_rupee(full)
    net = round_rupee(max(Fraction(0), min(full, cap)))
    return raw, raw - net


def _finish(gross, raw_taxable, apply288, slabs, rebate_cfg, max_rate, R, trace, slab_clause, rebate_clause):
    taxable = round_to_10(raw_taxable) if apply288 else raw_taxable
    trace.append(dict(step="taxable", label="Taxable income after s.288A rounding", amount=taxable, clause="R-288A"))
    t = round_rupee(slab_tax(taxable, slabs))
    trace.append(dict(step="slab_tax", label="Tax on slabs", amount=t, clause=slab_clause))
    lim, mx = rebate_cfg["limit"], rebate_cfg["max"]
    if taxable <= lim:
        after = max(0, t - mx)
    elif rebate_cfg["marginal_relief"] and t > taxable - lim:
        after = taxable - lim
    else:
        after = t
    trace.append(dict(step="rebate", label="s.87A rebate (incl. marginal relief)", amount=t - after, clause=rebate_clause))
    raw_sur, relief = surcharge(taxable, after, slabs, R["surcharge_thresholds"], max_rate)
    sur = raw_sur - relief
    trace.append(dict(step="raw_surcharge", label="Surcharge before marginal relief", amount=raw_sur, clause="R-SURCHARGE"))
    trace.append(dict(step="surcharge_marginal_relief", label="Surcharge marginal relief", amount=relief, clause="R-MARGINAL-RELIEF"))
    trace.append(dict(step="surcharge", label="Net surcharge", amount=sur, clause="R-SURCHARGE"))
    cess = round_rupee(Fraction(after + sur) * R["cess_pct"] / 100)
    trace.append(dict(step="cess", label="Health & education cess", amount=cess, clause="R-CESS"))
    raw_total = after + sur + cess
    trace.append(dict(step="raw_total", label="Total tax before s.288B rounding", amount=raw_total, clause="R-TOTAL"))
    total = round_to_10(raw_total) if apply288 else raw_total
    if total != raw_total:
        trace.append(dict(step="rounding_288b", label="s.288B rounding to nearest Rs 10", amount=total - raw_total, clause="R-288B"))
    trace.append(dict(step="total", label="Total tax", amount=total, clause="R-TOTAL/R-288B"))
    return dict(gross_salary=gross, rounding_288_applied=apply288, raw_taxable_income=raw_taxable,
                taxable_income=taxable, tax_on_slabs=t, rebate_87a=t - after, raw_surcharge=raw_sur,
                surcharge_marginal_relief=relief, surcharge=sur, cess=cess, raw_total_tax=raw_total,
                total_tax=total, trace=trace)


def calc_new(inp: TaxInput, R: dict) -> dict:
    c = R["new"]
    std = min(c["standard_deduction"], inp.gross_salary)
    raw = max(0, inp.gross_salary - std)
    trace = [dict(step="std", label="Standard deduction", amount=std, clause="R-STD-NEW"),
             dict(step="raw_taxable", label="Taxable income before s.288A", amount=raw, clause="R-NEW-BASE")]
    out = _finish(inp.gross_salary, raw, inp.apply_288_rounding, c["slabs"], c["rebate"], c["surcharge_max_rate"],
                  R, trace, "R-NEW-SLABS", "R-REBATE-NEW")
    return dict(regime="new", **out)


def calc_old(inp: TaxInput, R: dict) -> dict:
    c = R["old"]; caps = c["caps"]; h = c["hra"]
    base = inp.hra_salary_base
    if inp.hra_received and inp.rent_paid:
        pct = h["metro_pct"] if inp.metro_city else h["non_metro_pct"]
        hra_ex = round_rupee(min(Fraction(inp.hra_received),
                                 max(Fraction(0), inp.rent_paid - Fraction(base) * h["rent_excess_pct"] / 100),
                                 Fraction(base) * pct / 100))
    else:
        hra_ex = 0
    sal = inp.gross_salary - hra_ex
    std = min(c["standard_deduction"], sal)
    hp = min(inp.home_loan_interest, caps["24b"])
    d80c = min(inp.sec_80c, caps["80c"])
    d80ccd = min(inp.nps_80ccd1b, caps["80ccd1b"])
    d_self = min(inp.health_self, caps["80d_self_senior"] if inp.age >= R["senior_age"] else caps["80d_self"])
    d_par = min(inp.health_parents, caps["80d_parents_senior"] if inp.parents_senior else caps["80d_parents"])
    raw = max(0, sal - std - hp - d80c - d80ccd - d_self - d_par)
    trace = [dict(step="hra_ex", label="HRA exemption", amount=hra_ex, clause="R-HRA"),
             dict(step="std", label="Standard deduction", amount=std, clause="R-STD-OLD"),
             dict(step="hp", label="Home-loan interest (self-occupied)", amount=hp, clause="R-24B"),
             dict(step="d80c", label="80C", amount=d80c, clause="R-80C"),
             dict(step="d80ccd", label="80CCD(1B)", amount=d80ccd, clause="R-80CCD1B"),
             dict(step="d80d_self", label="80D self/family", amount=d_self, clause="R-80D-SELF"),
             dict(step="d80d_par", label="80D parents", amount=d_par, clause="R-80D-PARENTS"),
             dict(step="raw_taxable", label="Taxable income before s.288A", amount=raw, clause="R-OLD-TAXABLE")]
    band = "super_senior" if inp.age >= R["super_senior_age"] else "senior" if inp.age >= R["senior_age"] else "regular"
    out = _finish(inp.gross_salary, raw, inp.apply_288_rounding, c["slab_sets"][band], c["rebate"],
                  c["surcharge_max_rate"], R, trace, "R-OLD-SLABS", "R-REBATE-OLD")
    return dict(regime="old", **out)


def compute(inp: TaxInput) -> dict:
    inp.validate()
    R = load_rules(inp.fy)
    old = attach_traceability(calc_old(inp, R), inp.fy)
    new = attach_traceability(calc_new(inp, R), inp.fy)
    return {"old": old, "new": new, "recommendation": recommend(old, new)}
