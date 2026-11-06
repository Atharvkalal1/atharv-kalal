"""Independent reference calculator (test oracle).

Deliberately written differently from impl (a) and (c): cumulative-base-tax tables instead of slab loops,
surcharge handled by a descending threshold scan, plain Fractions, no shared helper code from engine.py,
dsl.py or common.round_*. It exists so that 'expected' values in the test suite are NOT produced by the code under test.

Shared ASSUMPTIONS (cannot be cross-checked by code, must be checked against the official calculator):
 s.288A/288B rounding to nearest Rs 10 (half up); slab tax, surcharge and cess each rounded to the rupee (half up).
"""
from fractions import Fraction as F
from math import floor

CFG = {
 "2024-25": {
   "new": dict(std=75000, slabs=[(0, 0), (300000, 5), (700000, 10), (1000000, 15), (1200000, 20), (1500000, 30)],
               rebate_limit=700000, rebate_max=25000, max_sur=25),
   "old": dict(std=50000, rebate_limit=500000, rebate_max=12500, max_sur=37,
               slabs={"reg": [(0, 0), (250000, 5), (500000, 20), (1000000, 30)],
                      "sen": [(0, 0), (300000, 5), (500000, 20), (1000000, 30)],
                      "sup": [(0, 0), (500000, 20), (1000000, 30)]}),
 },
}
# FY2025-26: only the new regime changes (Finance Act 2025)
CFG["2025-26"] = {
   "new": dict(std=75000, slabs=[(0, 0), (400000, 5), (800000, 10), (1200000, 15), (1600000, 20), (2000000, 25), (2400000, 30)],
               rebate_limit=1200000, rebate_max=60000, max_sur=25),
   "old": CFG["2024-25"]["old"],
}
SUR = [(5_000_000, 10), (10_000_000, 15), (20_000_000, 25), (50_000_000, 37)]


def rnd(x):  # nearest rupee, half up
    return floor(F(x) + F(1, 2))


def rnd10(x):  # nearest 10, half up
    return floor(F(x) / 10 + F(1, 2)) * 10


def cum_tax(inc, slabs):
    """Tax = sum over slabs; slabs = [(lower_bound, rate%)...] ascending."""
    tot = F(0)
    for i, (lo, r) in enumerate(slabs):
        hi = slabs[i + 1][0] if i + 1 < len(slabs) else None
        if inc <= lo:
            break
        top = inc if hi is None else min(inc, hi)
        tot += F(top - lo) * r / 100
    return tot


def surcharge(ti, tax_after_rebate, slabs, max_sur):
    rate_at = lambda inc: min(max([0] + [r for t, r in SUR if inc > t]), max_sur)
    rate = rate_at(ti)
    if rate == 0:
        return 0
    full = F(tax_after_rebate) * rate / 100
    # marginal relief: scan thresholds below ti, the one that applies is the highest crossed
    T = max(t for t, _ in SUR if ti > t)
    prev = rate_at(T)  # rate that applied AT the threshold (income == T gets the previous slab's rate)
    tax_T = rnd(cum_tax(T, slabs))
    limit = F(tax_T) * (100 + prev) / 100 + (ti - T) - tax_after_rebate
    return rnd(max(F(0), min(full, limit)))


def _finish(raw_ti, slabs, c, apply288):
    ti = rnd10(raw_ti) if apply288 else raw_ti
    tax = rnd(cum_tax(ti, slabs))
    if ti <= c["rebate_limit"]:
        after = max(0, tax - c["rebate_max"])
    elif c.get("relief") and tax > ti - c["rebate_limit"]:
        after = ti - c["rebate_limit"]
    else:
        after = tax
    s = surcharge(ti, after, slabs, c["max_sur"])
    cess = rnd(F(after + s) * 4 / 100)
    tot = after + s + cess
    return rnd10(tot) if apply288 else tot


def oracle(i: dict, fy: str = "2024-25"):
    """i: TaxInput kwargs (dict). Returns (old_total, new_total)."""
    cfg = CFG[fy]
    g, age = i["gross_salary"], i.get("age", 30)
    ap = i.get("apply_288_rounding", True)
    # new
    n = cfg["new"]; n = dict(n, relief=True)
    new = _finish(max(0, g - min(n["std"], g)), n["slabs"], n, ap)
    # old
    o = cfg["old"]; o = dict(o, relief=False)
    base = i.get("basic_da", 0) or (i.get("basic_salary", 0) + i.get("da_eligible", 0) + i.get("commission_turnover", 0))
    hra_r, rent = i.get("hra_received", 0), i.get("rent_paid", 0)
    pct = 50 if i.get("metro_city") else 40
    hra = rnd(min(F(hra_r), max(F(0), rent - F(base) / 10), F(base) * pct / 100)) if hra_r and rent else 0
    sal = g - hra
    ded = min(o["std"], sal)
    ded += min(i.get("home_loan_interest", 0), 200000)
    ded += min(i.get("sec_80c", 0), 150000) + min(i.get("nps_80ccd1b", 0), 50000)
    ded += min(i.get("health_self", 0), 50000 if age >= 60 else 25000)
    ded += min(i.get("health_parents", 0), 50000 if i.get("parents_senior") else 25000)
    band = "sup" if age >= 80 else "sen" if age >= 60 else "reg"
    old = _finish(max(0, sal - ded), o["slabs"][band], o, ap)
    return old, new
