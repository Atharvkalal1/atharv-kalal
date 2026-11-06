# Project B results: NYC 311 data-quality layer

**Data caveat (read first):** this sandbox could not reach NYC Open Data. All numbers below come from a **SYNTHETIC** 12,000-row stand-in (`make_synthetic_sample.py`), so they show the machinery works, not how it performs on real 311 data. Run `python -m project_b.fetch_nyc311 --max-rows 200000` and then `python run_all.py`; every script switches to real data automatically and the JSON records `data_source`. **LLM family: NOT MEASURED** (needs `GEMINI_API_KEY`); only a labelled cost projection is given. The "real issues found" (Task 1) must be re-profiled on real data; the synthetic profile only reflects noise seeded by the generator.

## 1. Setup
Reference = first 2,000 rows (statistics/contracts learned only from this). Test batches = 1,000 rows, 5% injection, 3 seeds; false alarms on 4 clean batches disjoint from the reference. Injector: one type per call, exact ground truth, no marker strings; a/c are tail-of-batch drift, g is a single-agency spike. Detectors never import the injector (tested).

## 2. Per problem (row recall / row precision; batch alert in 3/3 seeds for all; false-alarm rate on clean rows)
| Type | Rules | Statistical | LLM |
|---|---|---|---|
| a renamed/dropped column | 1.00 / 1.00 / 0 | 1.00 / 1.00 / 0 | NOT MEASURED |
| b type change | 1.00 / 1.00 / 0 | 1.00 / 1.00 / 0 | " |
| c date format switch | 1.00 / 1.00 / 0 | 1.00 / 1.00 / 0 | " |
| d lat/lon swapped | 1.00 / 1.00 / 0 | 1.00 / 1.00 / 0 | " |
| e exact duplicates | 1.00 / 1.00 / 0 | 1.00 / 1.00 / 0 | " |
| f near-duplicates | 0.40 / 0.50 / 0 | 0.52 / 0.53 / 0 | " |
| g null spike (one agency) | batch alert + agency; no row list | 1.00 / 0.99 / 0 | " |
| h closed < created | 1.00 / 0.94 / 0.004 | 1.00 / 0.96 / 0.004 | " |
| i ZIP vs borough | 0.99 / 1.00 / 0 | 0.72 / 1.00 / 0 | " |
| j complaint vs descriptor | 1.00 / 1.00 / 0 | 1.00 / 1.00 / 0 | " |
| k resolution vs status | 0.94 / 1.00 / 0 | 0.73 / 1.00 / 0 | " |
| l PII in free text | 1.00 / 1.00 / 0 | 1.00 / 1.00 / 0 | " |
The h false alarms are natural noise seeded in the data (0.4% closed<created rows); precision <1 there is real data issues, not detector error. f is weak for both: near-duplicates are hard when legitimate repeat reports exist. Names (not phones/emails) are invisible to regex; the synthetic PII uses phones/emails/SSN in most variants, so l is optimistic.
Throughput on this sandbox CPU: rules ~53k rows/s, statistics ~7.7k rows/s. Cost per million rows: rules and statistics $0 marginal (compute only). LLM: **projection** $23 (reference rates) to $62 (list rates) per million rows reviewed row-by-row (~107 prompt tokens/row, 25 rows/call) with ~24s of API time per 25 rows unmeasured. Explanation clarity (auto-score 0-1: names field, shows value, says what was expected): rules 0.33-1.0, mean ~0.8; see `results/benchmark_b.json`.

## 3. Hybrid (all 12 types mixed at 1% each, 3,060 rows)
Tier 1 rules on every row, Tier 2 statistics per batch, Tier 3 LLM only on disagreement/semantic rows plus a 1% audit sample: **1.73% of rows routed** (0.9-1.1% on clean batches). Tiers 1+2 alone: overall row recall **0.958**, 0.77% of clean rows flagged; weakest: e 21/30 and f 18/30 (mixed-batch duplicates of already-corrupted rows), a 24/30. Tier 3 was **not executed**; projected LLM cost for routed rows ~$27 per million *routed* rows, i.e. well under $1 per million rows ingested at 1.7% routing. Throughput of the whole hybrid here: ~6k rows/s (single process).

## 4. Scale design: 50M rows/day, 120 customers (max 2 pages)
50M/day = 580 rows/s average, perhaps 3-5k/s at peak. Single-process measured throughput (6k/s hybrid) fits peak on one core only for one tenant; with 120 schemas use ~8-16 workers.
What changes: (1) **Schemas are data**: per-tenant contract (columns, types, formats, ranges, allow-lists) stored in a registry and versioned; rules are generated from it, not Python. A new tenant needs a reference batch to learn its statistics (cold-start: rules-only for the first N batches). (2) **Statistics are the cost centre** (7.7k rows/s vs 53k): MinHash/LSH dedup moves to a keyed stream store with a time window; per-agency null tests become incremental counters instead of batch scans. (3) **LLM stays off the hot path**: routed ~1.7% = ~850k rows/day; at the projected $23-62 per million = ~$20-55/day if every routed row is reviewed, and cheaper if reviews are cached by (text-pattern, status) and sampled. This is a projection; measure with a key first. (4) **Alert fatigue** becomes the limiting factor at 120 tenants: dedupe alerts per (tenant, type, field), page only on batch-level alerts, send row-level ones as a digest; track false-alarm rate per tenant (real data will be noisier than here). (5) Drift: re-learn references weekly, and alert (not auto-adopt) when a reference shift is itself anomalous.
