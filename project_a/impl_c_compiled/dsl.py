"""Tiny rule DSL + interpreter for implementation (c). No LLM at runtime.

A spec is {"fy", "regimes": {"new"|"old": {"steps": [...], "outputs": {...}}}}.
Steps run in order and write into an environment of exact Fractions. Ops:
  expr      {"id","expr"}                          safe arithmetic (+ - * /, min, max, round_rupee, round_to_10, comparisons, a if c else b)
  slabs     {"id","tables":[{"when":expr|null,"table":[[upper|null, pct],..]}]}   first matching table wins
  rebate    {"id","out","income","tax","limit","max","marginal_relief"}           id=rebate amount, out=tax after rebate
  surcharge {"id","income","tax","slabs":<slabs step id>,"thresholds":[[T,pct],..],"max_rate"}
            id = RAW surcharge; the marginal relief is stored in variable "<id>__relief" (net = raw - relief,
            expressed by two ordinary expr steps so each rupee of relief has its own trace row + clause)
  cess      {"id","base","pct"}
Every step carries "clause" (rule-text ID) and "label" so each rupee is traceable.
Optional "trace": false (hide) or "nonzero" (show only when the value is not 0, e.g. the s.288B rounding step).
Inputs in the environment = TaxInput.to_dict(): incl. hra_salary_base and apply_288_rounding (bool).
"""
from __future__ import annotations
import ast
from fractions import Fraction
from project_a.common import round_rupee, round_to_10

_OK = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Call, ast.Compare,
       ast.BoolOp, ast.IfExp, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd,
       ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq, ast.And, ast.Or)
_FUNCS = {"min": min, "max": max, "round_rupee": round_rupee, "round_to_10": round_to_10}


def _ev(n, env):
    if not isinstance(n, _OK):
        raise ValueError(f"disallowed syntax: {type(n).__name__}")
    if isinstance(n, ast.Expression):
        return _ev(n.body, env)
    if isinstance(n, ast.Constant):
        v = n.value
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return Fraction(str(v))
        raise ValueError("bad constant")
    if isinstance(n, ast.Name):
        if n.id not in env:
            raise KeyError(f"unknown variable '{n.id}'")
        return env[n.id]
    if isinstance(n, ast.UnaryOp):
        v = _ev(n.operand, env)
        return -v if isinstance(n.op, ast.USub) else v
    if isinstance(n, ast.BinOp):
        a, b = _ev(n.left, env), _ev(n.right, env)
        return {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b,
                ast.Div: lambda: Fraction(a) / Fraction(b)}[type(n.op)]()
    if isinstance(n, ast.Compare):
        left = _ev(n.left, env)
        for op, c in zip(n.ops, n.comparators):
            right = _ev(c, env)
            ok = {ast.Gt: left > right, ast.GtE: left >= right, ast.Lt: left < right,
                  ast.LtE: left <= right, ast.Eq: left == right, ast.NotEq: left != right}[type(op)]
            if not ok:
                return False
            left = right
        return True
    if isinstance(n, ast.BoolOp):
        vals = [bool(_ev(v, env)) for v in n.values]
        return all(vals) if isinstance(n.op, ast.And) else any(vals)
    if isinstance(n, ast.IfExp):
        return _ev(n.body, env) if _ev(n.test, env) else _ev(n.orelse, env)
    if isinstance(n, ast.Call):
        if not isinstance(n.func, ast.Name) or n.func.id not in _FUNCS or n.keywords:
            raise ValueError("disallowed call")
        return _FUNCS[n.func.id](*[_ev(a, env) for a in n.args])
    raise ValueError("unsupported")


def evaluate(expr: str, env: dict):
    return _ev(ast.parse(expr, mode="eval"), env)


def _slab_tax(income, table) -> Fraction:
    tax, lower = Fraction(0), Fraction(0)
    for upper, pct in table:
        top = income if upper is None else min(income, Fraction(upper))
        if top > lower:
            tax += (top - lower) * pct / 100
        if upper is None or income <= upper:
            break
        lower = Fraction(upper)
    return tax


def run_regime(spec_regime: dict, inputs: dict) -> dict:
    env = {k: (v if isinstance(v, bool) else Fraction(v)) for k, v in inputs.items() if k != "fy"}
    tables, trace = {}, []
    for s in spec_regime["steps"]:
        op, sid = s["op"], s["id"]
        if op == "expr":
            env[sid] = evaluate(s["expr"], env)
        elif op == "slabs":
            table = next((t["table"] for t in s["tables"] if t.get("when") is None or evaluate(t["when"], env)), None)
            if table is None:
                raise ValueError(f"no slab table matched in step {sid}")
            tables[sid] = table
            env[sid] = round_rupee(_slab_tax(env[s.get("on", "taxable")], table))
        elif op == "rebate":
            inc, tax = env[s["income"]], env[s["tax"]]
            if inc <= s["limit"]:
                after = max(Fraction(0), tax - s["max"])
            elif s["marginal_relief"] and tax > inc - s["limit"]:
                after = inc - s["limit"]
            else:
                after = tax
            env[s["out"]] = after
            env[sid] = tax - after
        elif op == "surcharge":
            inc, tax, table = env[s["income"]], env[s["tax"]], tables[s["slabs"]]
            rate, before, T = 0, 0, None
            for thr, pct in s["thresholds"]:
                if inc > thr:
                    before, rate, T = rate, min(pct, s["max_rate"]), thr
            if rate == 0:
                env[sid], env[sid + "__relief"] = Fraction(0), Fraction(0)
            else:
                at_T = round_rupee(_slab_tax(Fraction(T), table))
                cap = Fraction(at_T) * (100 + before) / 100 + (inc - T) - tax
                full = tax * rate / 100
                raw = round_rupee(full)
                net = round_rupee(max(Fraction(0), min(full, cap)))
                env[sid], env[sid + "__relief"] = Fraction(raw), Fraction(raw - net)
        elif op == "cess":
            env[sid] = round_rupee(evaluate(s["base"], env) * Fraction(s["pct"]) / 100)
        else:
            raise ValueError(f"unknown op {op}")
        tr = s.get("trace", True)
        if tr is True or (tr == "nonzero" and env[sid] != 0):
            v = env[sid]
            trace.append(dict(step=sid, label=s["label"], amount=round_rupee(v), clause=s["clause"]))
    out = {k: round_rupee(env[v]) for k, v in spec_regime["outputs"].items()}
    return dict(out, trace=trace)


REQUIRED_OUTPUTS = ("gross_salary", "raw_taxable_income", "taxable_income", "tax_on_slabs", "rebate_87a", "raw_surcharge",
                    "surcharge_marginal_relief", "surcharge", "cess", "raw_total_tax", "total_tax")


def validate_spec(spec: dict, sample_inputs: dict) -> list[str]:
    """Static + dry-run checks a human reviewer should see before promoting a compiled spec."""
    problems = []
    for reg in ("new", "old"):
        r = spec.get("regimes", {}).get(reg)
        if not r:
            problems.append(f"missing regime {reg}")
            continue
        for s in r["steps"]:
            for k in ("id", "op", "clause", "label"):
                if k not in s:
                    problems.append(f"{reg}: step missing '{k}': {s}")
        try:
            res = run_regime(r, sample_inputs)
            for k in REQUIRED_OUTPUTS:
                if k not in res:
                    problems.append(f"{reg}: output '{k}' missing")
        except Exception as e:  # noqa: BLE001
            problems.append(f"{reg}: dry run failed: {e!r}")
    return problems
