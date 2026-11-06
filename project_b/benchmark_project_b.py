"""Task 4/5: per-problem x per-detector measurement + hybrid end-to-end. Every number is computed here.
    python -m project_b.benchmark_project_b            (LLM family runs only if GEMINI_API_KEY is set; else NOT MEASURED)
"""
from __future__ import annotations
import copy, json, os, random, statistics, time
from pathlib import Path
from project_a import gemini_client as G
from project_b.common import load, Reference
from project_b.injector import inject, TYPES
from project_b.detectors import rules, statistical, llm_review
from project_b.hybrid_pipeline import HybridPipeline

OUT = Path(__file__).parent / "results"; SEEDS = (1, 2, 3); N = 1000; RATE = 0.05
CLARITY_WORDS = ("contract", "reference", "expected", "never seen", "belongs to", "dominant", "swapped", "history", "reads like", "vs", "before", "not iso", "identical", "within 10")


def clarity(findings):
    if not findings: return None
    sc = [(f.get("field") is not None and str(f["field"]).split("_")[0] in f["msg"]) + any(ch.isdigit() or ch in "'\"" for ch in f["msg"]) + any(w in f["msg"] for w in CLARITY_WORDS) for f in findings]
    return round(statistics.mean(sc) / 3, 2)


def score(findings, ptype, truth, n_rows):
    typed = [f for f in findings if f["type"] == ptype]
    flagged = {f["row"] for f in typed if f["row"] is not None}
    if truth["level"] == "batch" and ptype == "g":
        typed_ok = [f for f in typed if f.get("agency") == truth["agency"]]; batch_hit = bool(typed_ok)
    else:
        batch_hit = bool(typed)
    tr = truth["rows"]; hit = len(flagged & tr)
    return dict(batch_detected=batch_hit, row_recall=hit / len(tr) if tr else None, row_precision=hit / len(flagged) if flagged else None,
                clarity=clarity(typed))


def mean(xs):
    xs = [x for x in xs if x is not None]; return round(statistics.mean(xs), 3) if xs else None


def mixed_batch(rows, rate=0.01, seed=0):
    """All 12 types in one batch with row-level ground truth (hidden tag list, stripped before detection)."""
    b = copy.deepcopy(rows)
    for r in b: r["__t"] = []
    for k, ptype in enumerate("efabcdghijkl"):
        b, tr = inject(b, ptype, rate, seed + k)
        for i in tr["rows"]: b[i]["__t"] = ([] if ptype in "ef" else b[i].get("__t", [])) + [ptype]
    tags = [r.pop("__t") for r in b]
    return b, tags


def run(write=True):
    rows, src = load(); ref_rows = rows[:2000]; ref = Reference(ref_rows); contract = rules.build_contract(ref_rows); pool = rows[2000:]
    fams = {"rules": lambda b: rules.detect(b, contract), "stats": lambda b: statistical.detect(b, ref)}
    live = G.has_key(); res = {"data_source": src, "rows_total": len(rows), "reference_rows": len(ref_rows), "batch_rows": N, "rate": RATE, "seeds": list(SEEDS), "llm_live": live}
    # --- false alarms on clean batches (disjoint from reference)
    cleans = [pool[i * N:(i + 1) * N] for i in range(4)]
    res["false_alarms"] = {}
    for fam, fn in fams.items():
        per = {t: [] for t in TYPES}; batch_alert = {t: 0 for t in TYPES}
        for cb in cleans:
            fs = fn(cb)
            for t in TYPES:
                ft = [f for f in fs if f["type"] == t]; per[t].append(len({f["row"] for f in ft if f["row"] is not None}) / N); batch_alert[t] += bool(ft)
        res["false_alarms"][fam] = {t: {"row_rate": round(statistics.mean(per[t]), 4), "clean_batches_alerted": f"{batch_alert[t]}/{len(cleans)}"} for t in TYPES}
    # --- per problem x family
    res["problems"] = {}; base = pool[4 * N:]
    for t in TYPES:
        res["problems"][t] = {"name": TYPES[t]}
        for fam, fn in fams.items():
            sc = []
            for s in SEEDS:
                b, tr = inject(base[s * N:(s + 1) * N], t, RATE, s); sc.append(score(fn(b), t, tr, len(b)))
            res["problems"][t][fam] = {"batch_detected": f"{sum(x['batch_detected'] for x in sc)}/{len(sc)}", "row_recall": mean([x["row_recall"] for x in sc]),
                                       "row_precision": mean([x["row_precision"] for x in sc]), "clarity": mean([x["clarity"] for x in sc])}
    # --- throughput (full family pass over 5,000 clean rows)
    big = pool[:5000]; res["throughput_rows_per_sec"] = {}
    for fam, fn in fams.items():
        t0 = time.perf_counter(); fn(big); res["throughput_rows_per_sec"][fam] = int(len(big) / (time.perf_counter() - t0))
    # --- LLM family
    sample_text = base[:200]
    res["llm_cost_projection"] = llm_review.project_cost_per_million_rows(sample_text)
    if live:
        W = int(os.environ.get("LLM_WINDOW", 200)); usage = dict(calls=0, prompt_tokens=0, output_tokens=0, latency_s=0.0); cl = llm_review
        for t in TYPES:
            b, tr = inject(base[:W], t, RATE, 1); fs, u = llm_review.review(b)
            for k in usage: usage[k] += u[k]
            res["problems"][t]["llm"] = dict(score(fs, t, tr, len(b)), window_rows=len(b))
        fs, u = llm_review.review(base[W:2 * W]); 
        for k in usage: usage[k] += u[k]
        res["false_alarms"]["llm"] = {"any_type_rows_flagged_pct_of_clean": round(100 * len({f["row"] for f in fs if f["row"] is not None}) / W, 2)}
        rows_reviewed = W * (len(TYPES) + 1)
        res["llm_measured"] = dict(usage, rows_reviewed=rows_reviewed, rows_per_sec=round(rows_reviewed / usage["latency_s"], 2),
                                   usd_per_million_rows_reference=round(llm_review.cost_usd(usage["prompt_tokens"], usage["output_tokens"])["reference"] / rows_reviewed * 1e6, 2),
                                   usd_per_million_rows_list=round(llm_review.cost_usd(usage["prompt_tokens"], usage["output_tokens"])["list"] / rows_reviewed * 1e6, 2))
    else:
        for t in TYPES: res["problems"][t]["llm"] = "NOT MEASURED (set GEMINI_API_KEY)"
    # --- hybrid end to end on a mixed batch (all 12 problems at 1% each) vs clean batches
    mb, tags = mixed_batch(base[:3000], 0.01, 5); hp = HybridPipeline(ref, contract, seed=3)
    t0 = time.perf_counter(); fnds, info = hp.process(mb); wall = time.perf_counter() - t0
    caught = {t: [0, 0] for t in TYPES}
    flagged_by = {}
    for f in fnds:
        if f["row"] is not None: flagged_by.setdefault(f["row"], set()).add(f["type"])
    for i, tg in enumerate(tags):
        for t in tg:
            caught[t][1] += 1; caught[t][0] += t in flagged_by.get(i, set())
    clean_rows_flagged = sum(1 for i, tg in enumerate(tags) if not tg and i in flagged_by)
    bad_rows = sum(1 for tg in tags if tg)
    ccl = [hp.process(cb)[1] for cb in cleans[:2]]
    res["hybrid"] = dict(info, rows=len(mb), rows_with_a_problem=bad_rows, wall_seconds=round(wall, 3), rows_per_sec=int(len(mb) / wall),
                         recall_by_type={t: f"{a}/{b}" for t, (a, b) in caught.items()},
                         overall_row_recall=round(sum(a for a, _ in caught.values()) / max(1, sum(b for _, b in caught.values())), 3),
                         clean_rows_flagged_pct=round(100 * clean_rows_flagged / max(1, len(mb) - bad_rows), 2),
                         clean_batches_routed_to_llm_pct=[c["routed_pct"] for c in ccl],
                         note="Tier 3 (LLM) executed" if info["llm_executed"] else "Tier 3 NOT executed (no key): recall below is tiers 1+2 only; LLM rows routed are counted and costed as a projection")
    if write: OUT.mkdir(exist_ok=True); (OUT / "benchmark_b.json").write_text(json.dumps(res, indent=1))
    p = res["problems"]
    print(f"=== PROJECT B | data: {src} | LLM live: {live} ===")
    print("type | rules recall/prec/FA | stats recall/prec/FA")
    for t in TYPES:
        a, b = p[t]["rules"], p[t]["stats"]
        print(f" {t} {TYPES[t][:34]:34s} | {a['row_recall']}/{a['row_precision']}/{res['false_alarms']['rules'][t]['row_rate']} (batch {a['batch_detected']}) | {b['row_recall']}/{b['row_precision']}/{res['false_alarms']['stats'][t]['row_rate']} (batch {b['batch_detected']})")
    print("throughput", res["throughput_rows_per_sec"], "| hybrid", {k: res["hybrid"][k] for k in ("overall_row_recall", "clean_rows_flagged_pct", "routed_pct", "rows_per_sec")})
    return res


if __name__ == "__main__":
    run()
