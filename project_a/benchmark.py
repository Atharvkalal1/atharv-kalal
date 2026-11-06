"""Task 4: measured benchmark for the three implementations. NOTHING here is hard-coded.

  python -m project_a.benchmark                 # (a) and (c) always; (b) only if GEMINI_API_KEY is set
  LLM_N=60 GEMINI_MIN_INTERVAL_S=7 python -m project_a.benchmark   # sample size / rate-limit throttle for (b)

Impl (b) is measured live or reported as NOT MEASURED. It is never estimated or simulated.
"""
from __future__ import annotations
import hashlib, json, os, random, statistics, time
from pathlib import Path
from project_a import gemini_client as G
from project_a.common import TaxInput
from project_a.impl_a_rules import engine as A
from project_a.impl_c_compiled import runtime as C

HERE = Path(__file__).parent
CASES = json.loads((HERE / "data" / "test_cases_200.json").read_text())
REPEATS = 10


def _inp(c):
    return TaxInput(**c["input"])


def _ok(r, c):
    return r["old"]["total_tax"] == c["expected_old"], r["new"]["total_tax"] == c["expected_new"]


def _digest(r):  # full result incl. trace, so 'deterministic' means identical numbers AND identical audit trail
    return hashlib.sha256(json.dumps({k: r[k] for k in ("old", "new")}, sort_keys=True, default=str).encode()).hexdigest()


def measure_local(name, fn):
    lat, ok_old, ok_new, ok_both, trace, by_cat = [], 0, 0, 0, 0, {}
    for c in CASES:
        t0 = time.perf_counter(); r = fn(_inp(c)); lat.append((time.perf_counter() - t0) * 1000)
        o, n = _ok(r, c); ok_old += o; ok_new += n; ok_both += o and n
        trace += r["old"]["fully_traceable"] and r["new"]["fully_traceable"]
        d = by_cat.setdefault(c["category"], [0, 0]); d[0] += o and n; d[1] += 1
    # determinism: every case, REPEATS times, compare full-result digests
    unstable = 0
    for c in CASES:
        digs = {_digest(fn(_inp(c))) for _ in range(REPEATS)}
        unstable += len(digs) > 1
    lat.sort(); n = len(CASES)
    return dict(impl=name, cases=n, rupee_exact_both_regimes=ok_both, rupee_exact_old=ok_old, rupee_exact_new=ok_new,
                accuracy_pct=round(100 * ok_both / n, 2), traceable=trace, traceable_pct=round(100 * trace / n, 2),
                nondeterministic_cases=unstable, repeats=REPEATS,
                latency_ms_p50=round(statistics.median(lat), 3), latency_ms_p95=round(lat[int(.95 * n) - 1], 3),
                cost_per_1k_usd=0.0, by_category={k: f"{a}/{b}" for k, (a, b) in by_cat.items()})


def measure_llm():
    if not G.has_key():
        return dict(impl="(b) LLM at query time", status="NOT MEASURED: set GEMINI_API_KEY (free tier is enough) and rerun",
                    note="No numbers are reported for (b) without a live run. Prompt/validators are unit-tested with a faked client.")
    from project_a.impl_b_llm import calculator as B
    n = int(os.environ.get("LLM_N", 60)); rnd = random.Random(1)
    sample = rnd.sample(CASES, min(n, len(CASES)))
    ok = oko = okn = tr = 0; lat, cost_ref, cost_list, errs = [], [], [], 0
    for c in sample:
        try:
            r, meta = B.compute_with_meta(_inp(c), bypass_cache=True)
        except Exception as e:  # network/parse failure counts as a failed request, loudly
            errs += 1; print("LLM error:", repr(e)[:120]); continue
        o, nw = _ok(r, c); oko += o; okn += nw; ok += o and nw
        tr += r["old"].get("fully_traceable", False) and r["new"].get("fully_traceable", False)
        lat.append(meta["latency_s"] * 1000)
        cost_ref.append(meta["est_cost_per_1k_req_usd"]["commercial_reference"]); cost_list.append(meta["est_cost_per_1k_req_usd"]["commercial_list_2_5_flash"])
    # determinism: 10 live repeats on the first DET_N sampled cases (temperature 0, seed 0)
    det_n, unstable = int(os.environ.get("DET_N", 5)), 0
    for c in sample[:det_n]:
        digs = set()
        for _ in range(REPEATS):
            try:
                r, _m = B.compute_with_meta(_inp(c), bypass_cache=True); digs.add(_digest(r))
            except Exception:
                digs.add("error")
        unstable += len(digs) > 1
    k = len(sample) - errs; lat.sort()
    return dict(impl="(b) LLM at query time", model=G.DEFAULT_MODEL, status="measured live", sampled=len(sample), request_errors=errs,
                rupee_exact_both_regimes=ok, accuracy_pct=round(100 * ok / max(1, k), 2), traceable=tr,
                traceable_pct=round(100 * tr / max(1, k), 2), determinism_cases_tested=det_n, nondeterministic_cases=unstable,
                latency_ms_p50=round(statistics.median(lat), 1) if lat else None, latency_ms_p95=round(lat[max(0, int(.95 * len(lat)) - 1)], 1) if lat else None,
                cost_per_1k_usd_free_tier=0.0, cost_per_1k_usd_reference_rates=round(statistics.mean(cost_ref), 4) if cost_ref else None,
                cost_per_1k_usd_list_rates=round(statistics.mean(cost_list), 4) if cost_list else None)


def run_benchmarks(write=True):
    res = {"generated_with": {"cases": len(CASES), "llm_key_present": G.has_key()},
           "a_hand_coded": measure_local("(a) hand-coded rules", A.compute),
           "c_llm_compiled": measure_local("(c) LLM-compiled rules (reviewed DSL)", C.compute),
           "b_llm_query_time": measure_llm()}
    from project_a.parser import evaluate_parser
    res["parser"] = evaluate_parser(verbose=False)
    if write:
        (HERE / "results").mkdir(exist_ok=True); (HERE / "results" / "benchmark.json").write_text(json.dumps(res, indent=1))
    print("\n=== PROJECT A BENCHMARK ===")
    for k in ("a_hand_coded", "c_llm_compiled", "b_llm_query_time"):
        r = res[k]
        if "accuracy_pct" in r:
            print(f"{r['impl']}: exact {r['accuracy_pct']}% | traceable {r['traceable_pct']}% | nondeterministic cases {r['nondeterministic_cases']}"
                  f" | p50 {r['latency_ms_p50']} ms p95 {r['latency_ms_p95']} ms")
        else:
            print(f"{r['impl']}: {r['status']}")
    return res


if __name__ == "__main__":
    run_benchmarks()
