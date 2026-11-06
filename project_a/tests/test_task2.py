import copy, io, json, os, random, urllib.error
from pathlib import Path
try:
    import pytest
except ImportError:
    import types
    pytest = types.ModuleType('pytest')
    pytest.mark = types.SimpleNamespace(
        parametrize=lambda *a, **k: (lambda f: f),
        skipif=lambda *a, **k: (lambda f: f)
    )
    class RaisesContext:
        def __init__(self, exc): self.exc = exc
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, tb): return exc_type is not None and issubclass(exc_type, self.exc)
    pytest.raises = lambda exc: RaisesContext(exc)
    pytest.warns = lambda exc: RaisesContext(exc)
    pytest.approx = lambda x: x
from project_a import gemini_client as G
from project_a.common import TaxInput, round_to_10, load_valid_clauses, verify_traceability
from project_a.impl_a_rules import engine as A
from project_a.impl_b_llm import calculator as B
from project_a.impl_c_compiled import runtime as C

# (input, expected old total, expected new total) -- worked by hand from rules_text/fy2024_25.md.
# Default mode = s.288A/288B rounding to Rs 10. exact=True cases use apply_288_rounding=False.
CASES = [
    (dict(gross_salary=1_200_000), None, 71_500),
    (dict(gross_salary=775_000), None, 0),                                   # exactly 7L taxable -> 87A
    (dict(gross_salary=785_000), None, 10_400),                              # 87A marginal relief
    (dict(gross_salary=800_000), None, 23_400),                              # relief not needed
    (dict(gross_salary=1_200_000, sec_80c=150_000, nps_80ccd1b=50_000, health_self=25_000,
          health_parents=25_000, home_loan_interest=200_000), 54_600, None),
    (dict(gross_salary=1_000_000, basic_da=600_000, hra_received=240_000, rent_paid=300_000, metro_city=True), 56_680, None),
    (dict(gross_salary=550_000), 0, None),                                   # old 87A at exactly 5L
    (dict(gross_salary=5_085_000), None, 1_248_000),                         # surcharge marginal relief
    # 288A: 1,159,567 -> 1,159,570; slabs 73,935.5 -> 73,936; cess 2,957; raw 76,893; 288B -> 76,890
    (dict(gross_salary=1_234_567), None, 76_890),
    # exact-rupee mode: slabs 73,935.05 -> 73,935; cess 2,957; total 76,892
    (dict(gross_salary=1_234_567, apply_288_rounding=False), None, 76_892),
    # Rule 2A: salary base 400k+100k+100k = 600k -> HRA exemption 210,000 -> old taxable 740,000 -> 48,000+12,500, cess -> 62,920
    (dict(gross_salary=1_000_000, basic_salary=400_000, da_eligible=100_000, commission_turnover=100_000,
          hra_received=240_000, rent_paid=270_000, metro_city=True), 62_920, None),
    # without commission, base 500k -> exemption 220,000 -> taxable 730,000 -> 58,500 + cess = 60,840
    (dict(gross_salary=1_000_000, basic_salary=400_000, da_eligible=100_000,
          hra_received=240_000, rent_paid=270_000, metro_city=True), 60_840, None),
    # basic_da > 0 wins over the three fields
    (dict(gross_salary=1_000_000, basic_da=600_000, basic_salary=1, hra_received=240_000, rent_paid=270_000,
          metro_city=True), 62_920, None),
]
IMPLS = [("rules", A.compute), ("compiled", C.compute)]
if os.environ.get("GEMINI_API_KEY"):
    IMPLS.append(("llm", B.compute))


@pytest.mark.parametrize("name,fn", IMPLS)
@pytest.mark.parametrize("inp,old,new", CASES)
def test_hand_checked(name, fn, inp, old, new):
    r = fn(TaxInput(**inp))
    if old is not None:
        assert r["old"]["total_tax"] == old
    if new is not None:
        assert r["new"]["total_tax"] == new


def test_round_to_10_halves_round_up():
    assert [round_to_10(x) for x in (0, 4, 5, 14, 15, 25, 76_893, 76_895)] == [0, 0, 10, 10, 20, 30, 76_890, 76_900]


def test_hra_salary_base_property():
    assert TaxInput(gross_salary=9, basic_da=5, basic_salary=1).hra_salary_base == 5
    assert TaxInput(gross_salary=9, basic_salary=1, da_eligible=2, commission_turnover=3).hra_salary_base == 6
    assert TaxInput(gross_salary=9).to_dict()["hra_salary_base"] == 0


def _rand_input(rnd):
    g = rnd.choice([200_000, 600_000, 775_000, 1_300_000, 5_085_000, 10_100_000, 20_200_000, 52_000_000]) + rnd.randint(0, 80_000)
    base = rnd.randint(0, g)
    kw = dict(basic_da=base) if rnd.random() < .5 else dict(basic_salary=base // 2, da_eligible=base // 4, commission_turnover=base // 4)
    return TaxInput(gross_salary=g, hra_received=rnd.randint(0, g), rent_paid=rnd.randint(0, g),
                    metro_city=rnd.random() < .5, age=rnd.choice([25, 60, 79, 80, 90]), sec_80c=rnd.randint(0, 300_000),
                    nps_80ccd1b=rnd.randint(0, 100_000), health_self=rnd.randint(0, 80_000),
                    health_parents=rnd.randint(0, 80_000), parents_senior=rnd.random() < .5,
                    home_loan_interest=rnd.randint(0, 400_000), apply_288_rounding=rnd.random() < .5, **kw)


def test_rules_and_compiled_agree_and_are_fully_traceable_on_3000_random_inputs():
    rnd = random.Random(7)
    relief_seen = 0
    for _ in range(3000):
        inp = _rand_input(rnd)
        a, c = A.compute(inp), C.compute(inp)
        for reg in ("old", "new"):
            for k in ("total_tax", "raw_total_tax", "taxable_income", "raw_taxable_income", "raw_surcharge",
                      "surcharge_marginal_relief", "surcharge", "cess", "rebate_87a"):
                assert a[reg][k] == c[reg][k], (inp, reg, k)
            assert a[reg]["fully_traceable"] is True, (inp, reg, a[reg]["trace_errors"])
            assert c[reg]["fully_traceable"] is True, (inp, reg, c[reg]["trace_errors"])
            assert a[reg]["trace_errors"] == [] == c[reg]["trace_errors"]
            if inp.apply_288_rounding:
                assert a[reg]["total_tax"] % 10 == 0 and a[reg]["taxable_income"] % 10 == 0
            relief_seen += a[reg]["surcharge_marginal_relief"] > 0
        assert a["recommendation"] == c["recommendation"]
    assert relief_seen > 0      # the marginal-relief path was actually exercised


def test_unified_schema():
    for fn in (A.compute, C.compute, lambda i: B.compute(i, offline=True)):
        r = fn(TaxInput(gross_salary=1_200_000, sec_80c=150_000))
        assert set(r) == {"old", "new", "recommendation"}
        assert r["recommendation"]["recommended"] in ("old", "new", "tie")
        assert isinstance(r["recommendation"]["saving"], int) and isinstance(r["recommendation"]["reason"], str)
        assert r["recommendation"]["clause_citations"] and all(c.startswith("R-") for c in r["recommendation"]["clause_citations"])


def test_tie_and_marginal_relief_breakdown():
    r = A.compute(TaxInput(gross_salary=100_000))
    assert r["recommendation"]["recommended"] == "tie" and r["recommendation"]["saving"] == 0
    n = A.compute(TaxInput(gross_salary=5_085_000))["new"]
    assert (n["raw_surcharge"], n["surcharge_marginal_relief"], n["surcharge"]) == (119_300, 112_300, 7_000)
    steps = {t["step"]: t for t in n["trace"]}
    assert steps["surcharge_marginal_relief"]["clause"] == "R-MARGINAL-RELIEF" and steps["raw_surcharge"]["clause"] == "R-SURCHARGE"


def test_288b_trace_step_only_when_rounding_adjusts():
    n = A.compute(TaxInput(gross_salary=1_234_567))["new"]
    s = [t for t in n["trace"] if t["step"] == "rounding_288b"]
    assert len(s) == 1 and s[0]["clause"] == "R-288B" and s[0]["amount"] == -3 and n["raw_total_tax"] == 76_893
    assert not [t for t in A.compute(TaxInput(gross_salary=1_200_000))["new"]["trace"] if t["step"] == "rounding_288b"]


def test_auditor_catches_tampering():
    valid = load_valid_clauses()
    good = A.compute(TaxInput(gross_salary=1_234_567, sec_80c=100_000))["old"]
    assert verify_traceability(good, valid)["fully_traceable"]
    bad = copy.deepcopy(good); bad["trace"][0]["clause"] = "R-MADE-UP"
    assert not verify_traceability(bad, valid)["fully_traceable"]
    bad = copy.deepcopy(good); bad["total_tax"] += 10
    assert not verify_traceability(bad, valid)["fully_traceable"]
    bad = copy.deepcopy(good); bad["raw_taxable_income"] += 7; bad["taxable_income"] = round_to_10(bad["raw_taxable_income"])
    assert not verify_traceability(bad, valid)["fully_traceable"]       # deductions no longer sum to gross - taxable
    bad = copy.deepcopy(good); bad["cess"] += 1
    assert not verify_traceability(bad, valid)["fully_traceable"]


def test_unknown_fy_fails_loudly_not_silently():
    with pytest.raises(ValueError):
        A.compute(TaxInput(gross_salary=1_000_000, fy="2025-26"))
    with pytest.raises(ValueError):
        C.compute(TaxInput(gross_salary=1_000_000, fy="2025-26"))


# ------------------------------------------------------------------ impl (b) with a faked Gemini
def test_offline_stub_is_tagged(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_STRICT", raising=False)
    with pytest.warns(UserWarning):
        res, meta = B.compute_with_meta(TaxInput(gross_salary=1_200_000))
    assert meta["mode"] == "offline_stub" and "offline_stub" in res["new"]["warnings"][0]
    monkeypatch.setenv("GEMINI_STRICT", "1")
    with pytest.raises(RuntimeError):
        B.compute_with_meta(TaxInput(gross_salary=1_200_000))


def test_live_path_audited(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    inp = TaxInput(gross_salary=1_234_567, sec_80c=100_000)
    truth = A.compute(inp)
    answer = {"old": {k: v for k, v in truth["old"].items() if k not in ("fully_traceable", "trace_errors")},
              "new": {k: v for k, v in truth["new"].items() if k not in ("fully_traceable", "trace_errors")}}
    monkeypatch.setattr(G, "generate_json", lambda *a, **k: (copy.deepcopy(answer), {"mode": "live_gemini"}))
    res, meta = B.compute_with_meta(inp)
    assert meta["mode"] == "live_gemini" and res["old"]["fully_traceable"] and res["new"]["fully_traceable"]
    assert res["recommendation"]["recommended"] == truth["recommendation"]["recommended"]
    answer["new"]["trace"][2]["clause"] = "R-INVENTED"          # a hallucinated citation must be flagged
    answer["old"]["cess"] += 5                                  # and a silent arithmetic slip too
    res, _ = B.compute_with_meta(inp)
    assert not res["new"]["fully_traceable"] and not res["old"]["fully_traceable"]


# ------------------------------------------------------------------ gemini client: cache, throttle, backoff, cost
class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _ok():
    body = {"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}],
            "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 1500, "thoughtsTokenCount": 500}}
    return _Resp(json.dumps(body).encode())


def test_gemini_cache_backoff_cost_throttle(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "k"); monkeypatch.setenv("GEMINI_CACHE_PATH", str(tmp_path / "c.json"))
    monkeypatch.setenv("GEMINI_MIN_INTERVAL_S", "5")
    clock, slept, calls = [100.0], [], []
    monkeypatch.setattr(G, "_now", lambda: clock[0])
    monkeypatch.setattr(G, "_sleep", lambda s: (slept.append(s), clock.__setitem__(0, clock[0] + s)))
    G._last_call[0] = 0.0
    script = [urllib.error.HTTPError("u", 429, "rate", {}, None), _ok(), _ok()]

    def fake_urlopen(req, timeout=0):
        calls.append(1)
        x = script.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(G.urllib.request, "urlopen", fake_urlopen)
    parsed, meta = G.generate_json("p", "s")
    assert parsed == {"a": 1} and len(calls) == 2 and slept[0] >= 2          # one 429 -> backoff -> success
    assert meta["mode"] == "live_gemini" and meta["prompt_tokens"] == 1000 and meta["output_tokens"] == 2000
    cost = meta["est_cost_per_1k_req_usd"]
    assert cost["free_tier"] == 0.0 and cost["commercial_reference"] == pytest.approx(1.35)   # (1000*.15+2000*.60)/1e6*1000
    assert cost["commercial_list_2_5_flash"] == pytest.approx(5.3)
    p2, m2 = G.generate_json("p", "s")                                       # cache hit, no network
    assert len(calls) == 2 and m2["cache_hit"] is True and m2["mode"] == "live_gemini_cached"
    G.generate_json("p", "s", bypass_cache=True)                             # forced live call
    assert len(calls) == 3
    assert max(slept) >= 4 or any(s >= 4 for s in slept)                    # RPM throttle spaced the calls


# ------------------------------------------------------------------ optional 200-case suite
_DATA = Path(__file__).parent.parent / "data" / "test_cases_200.json"


@pytest.mark.skipif(not _DATA.exists(), reason="project_a/data/test_cases_200.json not present yet (Task 1)")
@pytest.mark.parametrize("name,fn", IMPLS[:2] + ([IMPLS[2]] if len(IMPLS) > 2 and os.environ.get("RUN_LLM_200") else []))
def test_200_case_suite_full_agreement(name, fn):
    """File format: [{"id": str, "input": {TaxInput kwargs}, "expected_old": int, "expected_new": int}, ...]"""
    cases = json.loads(_DATA.read_text())
    assert len(cases) >= 200
    wrong = []
    for c in cases:
        r = fn(TaxInput(**c["input"]))
        if (r["old"]["total_tax"], r["new"]["total_tax"]) != (c["expected_old"], c["expected_new"]):
            wrong.append(c.get("id"))
    assert not wrong, f"{len(wrong)}/{len(cases)} disagree: {wrong[:10]}"
