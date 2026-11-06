# Project A results: income-tax engine (rules vs LLM vs compiled)

Every number below is produced by `python run_all.py` into `project_a/results/*.json`.
**Not measured offline:** implementation (b) (needs `GEMINI_API_KEY`), human stopwatch minutes, and the official-calculator cross-check (needs you). These cells are marked, never estimated.

## 1. Test suite (Task 1)
368 structured cases (FY2024-25: 35 reference, 104 boundary, 70 deductions/age, 40 rounding; FY2025-26: 119 incl. every slab edge, the 12L marginal-relief zone and all surcharge cliffs). **Expected values come from an independent oracle** (`tests/oracle.py`, different structure from (a)/(c)), not from the code under test, plus 5 hand-derived anchors (e.g. FY25-26 gross 13,00,000 -> new-regime tax 26,000). 48 cases are flagged as official-calculator candidates in `data/official_calculator_checks.json`; fill the two columns from the ITD calculator and run `python -m project_a.verify_official` (**0/48 filled so far; the 30-case requirement is not yet met**).
Plain-language: 50 dev + 30 held-out descriptions (English, Hinglish, incomplete, contradictory), hand-labelled with expected action and expected fields.

## 2. Comparison (Task 4)
| | (a) hand-coded | (b) LLM at query time | (c) LLM-compiled, reviewed DSL |
|---|---|---|---|
| Rupee-exact (both regimes, 368 cases) | 100% | **NOT MEASURED** | 100% |
| 10 repeats, identical full result incl. trace | 368/368 | **NOT MEASURED** | 368/368 |
| Latency p50 / p95 | ~0.3 / ~0.4 ms | **NOT MEASURED** | ~0.8 / ~0.9 ms |
| Cost / 1,000 requests | $0 | **NOT MEASURED** (token counts are recorded when run live) | $0 at run time |
| Every rupee traces to a clause (auditor) | 100% | **NOT MEASURED** | 100% |
Run `GEMINI_API_KEY=... GEMINI_MIN_INTERVAL_S=7 python -m project_a.benchmark` to fill column (b). Caveat: (a) and (c) agreeing with the oracle shows implementation consistency, not legal correctness; the shared assumptions (s.288A/B rounding points) must be confirmed against the official calculator.

## 3. Plain-language parser (Task 3)
Architecture: extract (rules, or Gemini) -> deterministic gate. The LLM can only extract; the gate decides compute vs ask. Never-guess rules: rent without period, rent without HRA, HRA without city/basic, "home loan" without interest, unspecified insurance/ELSS, silence about deductions all produce a question. Only default: age<60, reported in `assumptions`.
| Set | Action accuracy | Computed when it should have asked | Fields exact (compute cases) |
|---|---|---|---|
| dev 50 | 50/50 | 0 | 17/17 |
| held-out 30 | 30/30 | 0 | 15/15 |
**Read with care:** the rules were tuned on the dev set and the "held-out" set was written by the same author after the parser, so it is optimistic. Ten dev labels were *changed* from compute to clarify because the original labels encoded guessing (documented in `label_note`). Before the interview, write 20 fresh unseen cases; LLM-extractor accuracy is not measured.

## 4. Task 5: FY2025-26 change log
Size of the change (diff lines added/removed): (a) rules JSON +12/-8; (c) compiled DSL +12/-8; (b) rule prose +5/-5 (but re-interpreted by the model each call).
**Silent-failure experiment** (119 FY2025-26 cases; "silent" = wrong, no exception, auditor still passes):
| Partial update | (a) wrong/silent | (c) wrong/silent |
|---|---|---|
| slabs updated, 87A rebate forgotten | 34/34 | 34/34 |
| rebate limit updated, 60,000 cap forgotten | 13/13 | 13/13 |
| 87A updated, slabs forgotten | 84/84 | 84/84 |
| 25% slab mistyped | 63/63 | 63/63 |
| FY24-25 file copied unchanged | 113/113 | 113/113 |
**Finding:** rules and compiled rules do *not* have "0 silent failures": a wrong parameter is silent to the runtime auditor in both. The control is the oracle-backed golden suite, which catches all of them. Missing FY files fail loudly (`ValueError`).
**Defects found in the first submission by this audit (fixed):** the first-attempt compiled FY25-26 spec mapped raw surcharge/relief/surcharge to one step (17/119 suite cases wrong; the auditor did flag it); the FY25-26 rule text had no clause IDs so *every* FY25-26 answer from (a) and (c) failed traceability; a stale test asserted FY25-26 raises. The suite initially had too few surcharge cases to see the bug (1/87 wrong), which is why 32 surcharge-cliff cases were added.
(b): **NOT MEASURED**. Human minutes to update: **fill in from your stopwatch** (`results/task5.json`).

## 5. Final design for 100,000 users (max 2 pages)
| Component | Type | Why (measured) |
|---|---|---|
| Free-text -> facts | **Hybrid**: LLM extracts, rules gate | Rules alone read dev/held-out text but are brittle to unseen phrasing (unmeasured); the gate guarantees 0 computes-when-should-ask on both sets even if extraction is wrong, and an LLM extractor is unit-tested to be stopped by the gate |
| Tax arithmetic | **Rule** (compiled DSL or JSON; both 100% vs oracle, <1 ms, $0) | Statute needs rupee-exactness, determinism, clause trace. (b) is not used until measured; even then it can't beat 100%/$0 |
| Rule authoring each Budget | **LLM drafts, human reviews, tests gate** | Spec diff is ~20 lines; LLM drafting is useful, but the first compiled attempt was wrong, so review + oracle are mandatory |
| Audit trail / explanation | **Rule** | Auditor checks every trace row and reconciliation |
Keeping it correct through the next Budget: (1) add `rules_fyXX.json` + compiled spec + rule text with clause IDs; (2) regenerate cases from the oracle, extend the oracle independently (second reader of the Finance Act); (3) CI blocks release unless oracle suite, 30+ official-calculator checks and mutation experiment pass; (4) unknown FY raises; (5) route-to-human on parser doubt.
