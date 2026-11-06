# Project A - Task 2: three implementations of the income-tax calculator (FY 2024-25)

All three expose `compute(TaxInput) -> {"old": {...}, "new": {...}}` with `taxable_income, tax_on_slabs, rebate_87a, surcharge, cess, total_tax, trace[]`.
Each trace row carries a clause ID (`R-...`) defined in `rules_text/fy2024_25.md`.

| | Where the logic lives | LLM at runtime? |
|---|---|---|
| (a) `impl_a_rules/` | Python engine + numbers in `rules_fy2024_25.json` | No |
| (b) `impl_b_llm/` | Gemini reads `rules_text/` per request and does the arithmetic | Yes |
| (c) `impl_c_compiled/` | Rule DSL (`compiled/fy2024_25.json`) run by a safe interpreter (`dsl.py`) | No (LLM only at compile time) |

## Run
    export GEMINI_API_KEY=...        # live mode for (b) and the compile step; without it an OFFLINE STUB runs
    python -m project_a.run_smoke [--llm | --offline]
    pytest project_a -q              # LLM tests auto-enable if GEMINI_API_KEY is set (RUN_LLM_200=1 for the 200-case LLM run)
    python -m project_a.impl_c_compiled.compile_rules --fy 2024-25 [--offline]

## What every implementation returns
`compute(inp) -> {"old": R, "new": R, "recommendation": {recommended: old|new|tie, saving, reason, clause_citations}}`
R = `gross_salary, raw_taxable_income (before s.288A), taxable_income, tax_on_slabs, rebate_87a, raw_surcharge,
surcharge_marginal_relief, surcharge, cess, raw_total_tax (before s.288B), total_tax, trace[], fully_traceable, trace_errors[]`.
`TaxInput.apply_288_rounding=False` gives exact-rupee mode. Rule 2A salary: `basic_da` if > 0 else `basic_salary + da_eligible + commission_turnover`.

## Auditor (`common.verify_traceability`)
Every trace row cites a clause defined in `rules_text/fy2024_25.md`; trace rows equal the headline numbers; deductions sum to
`gross - raw_taxable_income`; `slab - rebate + surcharge + cess == raw_total_tax`; s.288A/288B applied correctly. Run on every regime output of (a), (b), (c).

## Gemini client
Disk cache `.gemini_cache.json` (`use_cache`, `bypass_cache` for the 10x determinism run), `GEMINI_MIN_INTERVAL_S` throttle, backoff on 429/500/503,
`meta["est_cost_per_1k_req_usd"]` = free tier $0 + commercial reference ($0.15/$0.60 per 1M, as specified) + current list price ($0.30/$2.50). Verify rates before quoting them.
A cache hit reports `cache_hit: true`; never mix cached numbers into latency tables.

## 200-case suite
If `project_a/data/test_cases_200.json` exists, the tests run it automatically: `[{"id", "input": {TaxInput kwargs}, "expected_old", "expected_new"}]`.

## Honest status
- (a) and (c) tested: hand-worked cases, 3000 random inputs (agreement + full traceability), auditor tamper tests. (b) is tested only against a faked Gemini; it has NOT been run live (no key/network in the build sandbox).
- Offline stub (`meta.mode == "offline_stub"`) delegates to (a). It is NOT an LLM result; never use it in Task 4 tables.
- `compiled/fy2024_25.json` is the *reviewed* spec, hand-authored in the DSL the LLM is asked to emit; `compile_rules.py` only writes a candidate.
- Constants come from my knowledge of the Finance Act 2024; verify against the official sources and the ITD calculator (which applies s.288A/288B).
