"""Implementation (b): LLM at query time. The model reads the rule text and does the arithmetic.

Nothing here computes tax in live mode. We (1) build the prompt, (2) parse + normalise the answer,
(3) audit it with verify_traceability (clause validity, deductions, reconciliation, R-288B).
A consistent-but-wrong answer is NOT detectable here; that is what the Task 4/5 measurements are for.

Offline: with no GEMINI_API_KEY (or offline=True) a deterministic STUB runs instead. It is tagged
meta["mode"] == "offline_stub" and just delegates to implementation (a) -- it is NOT an LLM result and
must never be used in the accuracy/latency/cost tables. Set GEMINI_STRICT=1 to forbid the fallback.
"""
from __future__ import annotations
import json, os, warnings
from pathlib import Path
from project_a.common import TaxInput, fy_slug, attach_traceability, safe_recommend
from project_a import gemini_client as G

_RULES = Path(__file__).parent.parent / "rules_text"

SYSTEM = ("You are a precise Indian income-tax calculator. Use ONLY the rules provided. "
          "Do exact integer rupee arithmetic and show every step. Output JSON only.")

SCHEMA = """Return JSON: {"old": R, "new": R} where R = {
 "raw_taxable_income": int, "taxable_income": int, "tax_on_slabs": int, "rebate_87a": int,
 "raw_surcharge": int, "surcharge_marginal_relief": int, "surcharge": int, "cess": int,
 "raw_total_tax": int, "total_tax": int,
 "trace": [{"step": str, "label": str, "amount": int, "clause": "<R-... id from the rules>"}]}
Definitions: raw_taxable_income is before R-288A; taxable_income is after R-288A (equal when apply_288_rounding is false);
rebate_87a = tax_on_slabs minus tax after rebate (incl. marginal relief); surcharge = raw_surcharge - surcharge_marginal_relief;
raw_total_tax = tax_on_slabs - rebate_87a + surcharge + cess; total_tax = raw_total_tax after R-288B.
Use hra_salary_base as the 'salary' for the HRA rule. Every trace row must cite a clause ID, and the trace must contain these step ids:
deductions: std (both regimes) and, old regime only, hra_ex, hp, d80c, d80ccd, d80d_self, d80d_par;
then raw_taxable, taxable, slab_tax, rebate, raw_surcharge, surcharge_marginal_relief, surcharge, cess, raw_total,
rounding_288b (only if R-288B changes the total; amount = total_tax - raw_total_tax), total. Amounts are integers (rounding_288b may be negative)."""

_INTS = ("raw_taxable_income", "taxable_income", "tax_on_slabs", "rebate_87a", "raw_surcharge",
         "surcharge_marginal_relief", "surcharge", "cess", "raw_total_tax", "total_tax")


def build_prompt(inp: TaxInput) -> str:
    rules = (_RULES / f"fy{fy_slug(inp.fy)}.md").read_text()
    return (f"# RULES\n{rules}\n\n# TAXPAYER (annual rupees)\n{json.dumps(inp.to_dict(), indent=1)}\n\n"
            f"# TASK\nCompute tax under BOTH regimes.\n{SCHEMA}")


def _intify(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def _normalize(r, reg: str, inp: TaxInput) -> dict:
    r = dict(r) if isinstance(r, dict) else {}
    r["regime"], r["gross_salary"], r["rounding_288_applied"] = reg, inp.gross_salary, inp.apply_288_rounding
    for k in _INTS:
        r[k] = _intify(r.get(k))
    r["trace"] = [dict(t, amount=_intify(t.get("amount"))) for t in (r.get("trace") or []) if isinstance(t, dict)]
    return r


def use_offline(offline: bool | None) -> bool:
    if offline is True:
        return True
    if G.has_key():
        return False
    if os.environ.get("GEMINI_STRICT"):
        raise RuntimeError("GEMINI_API_KEY not set and GEMINI_STRICT=1")
    warnings.warn("GEMINI_API_KEY not set: impl (b) is running the OFFLINE STUB (not an LLM).", stacklevel=3)
    return True


def _stub(inp: TaxInput):
    from project_a.impl_a_rules import engine as A
    res = A.compute(inp)
    for reg in ("old", "new"):
        res[reg]["warnings"] = ["offline_stub: deterministic answer from implementation (a), NOT an LLM result"]
    return res, {"mode": "offline_stub", "latency_s": 0.0, "prompt_tokens": 0, "output_tokens": 0,
                 "cache_hit": False, "est_cost_per_1k_req_usd": G.estimate_cost(0, 0)}


def compute_with_meta(inp: TaxInput, offline: bool | None = None, use_cache: bool = True, bypass_cache: bool = False):
    inp.validate()
    if use_offline(offline):
        return _stub(inp)
    out, meta = G.generate_json(build_prompt(inp), system=SYSTEM, use_cache=use_cache, bypass_cache=bypass_cache)
    res = {}
    for reg in ("old", "new"):
        r = _normalize(out.get(reg), reg, inp)
        r["warnings"] = []
        res[reg] = attach_traceability(r, inp.fy)
    res["recommendation"] = safe_recommend(res["old"], res["new"])
    return res, meta


def compute(inp: TaxInput, **kw) -> dict:
    return compute_with_meta(inp, **kw)[0]
