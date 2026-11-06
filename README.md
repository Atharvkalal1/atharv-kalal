# Fire AI take-home: Rules vs LLMs

Two systems, each built three ways (hand-coded rules, an LLM at query time, and rules compiled by an LLM), then measured and defended.

| Project | Question | Where | Results |
|---|---|---|---|
| **A: Income-tax engine** (India, salaried, FY 2024-25 and FY 2025-26) | Rules, LLM, or both? | `project_a/` | `RESULTS_A.md` |
| **B: Data-quality layer** (NYC 311, 2023) | Rules, statistics, or LLM review? | `project_b/` | `RESULTS_B.md` |

Cross-cutting documents: `DECISION_MATRIX.md` (every component marked rule / statistical / LLM / hybrid, with the measurement behind it) and `AI_USAGE.md`.

Everything is standard-library Python plus `pytest`. **No network and no API key are needed** to run the whole project; the LLM columns are then reported as `NOT MEASURED`. Nothing is simulated or estimated in their place.

---

## 1. Quick start

```bash
git clone <your-private-repo-url> fireai && cd fireai
./run_all.sh            # macOS / Linux / WSL / Git Bash
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_all.py
```

That single command runs the 79 tests, regenerates the JSON behind every number in `RESULTS_A.md` and `RESULTS_B.md` (`project_a/results/`, `project_b/results/`), and exits non-zero if any test fails. The `.md` documents themselves are hand-maintained: nothing rewrites them, so after a rerun (especially with a Gemini key or real data) copy the new figures from the JSON into them. It takes about 35 seconds offline (about 13 s of that is the tests).

## 2. Requirements

| Need | Details |
|---|---|
| Python | 3.10 or newer (developed on 3.12) |
| Packages | `pytest>=7` only (`requirements.txt`) |
| OS | Linux, macOS, Windows. `run_all.sh` needs bash; on plain Windows use the PowerShell steps above |
| Network | Not needed, except for the two optional extras: Gemini calls and downloading real NYC 311 data |
| Gemini key | Optional. The free tier of Google AI Studio is enough |

### Setup in a virtual environment (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_all.py
```

`run_all.sh` does this for you. If `pytest` is already importable it uses your Python as is; otherwise it creates `.venv` and installs into it. That makes it work on "externally managed" Pythons (Ubuntu 24.04, Debian, Homebrew), where a bare `pip install` fails with `error: externally-managed-environment`.

Useful switches: `PYTHON=python3.11 ./run_all.sh` picks an interpreter, and `FORCE_VENV=1 ./run_all.sh` always uses `.venv`.

## 3. Run modes

The same command runs in four modes. Each extra input fills in cells that are otherwise `NOT MEASURED`.

| Mode | What you do | What changes |
|---|---|---|
| **Offline (default)** | Nothing | Project A columns (a) and (c) are fully measured. Column (b), the LLM extractor and the Project B LLM family print `NOT MEASURED`. Project B runs on clearly labelled **SYNTHETIC** data |
| **+ Gemini** | `export GEMINI_API_KEY=...` | Fills Project A (b) (accuracy, 10x determinism, latency, token cost), the Task 5 (b) row, and the Project B LLM family and hybrid tier 3 |
| **+ real NYC 311** | `python -m project_b.fetch_nyc311 --max-rows 200000` | Project B switches from SYNTHETIC to **REAL**; the profile and all detector tables change |
| **+ official calculator** | Fill `project_a/data/official_calculator_checks.json`, then `python -m project_a.verify_official` | Turns "0/48 checked" into a real cross-check against the Income Tax Department calculator |

Output headers tell you which mode you are in: `data: SYNTHETIC (...)` or `REAL (NYC Open Data)`, `LLM live: False/True`, and `NOT MEASURED: ...` for missing cells.

### What a clean offline run prints (trimmed; timings vary by machine)

```
79 passed in 13s
(a) hand-coded rules: exact 100.0% | traceable 100.0% | nondeterministic cases 0 | p50 0.39 ms p95 0.59 ms
(c) LLM-compiled rules (reviewed DSL): exact 100.0% | traceable 100.0% | nondeterministic cases 0 | p50 1.07 ms p95 2.01 ms
(b) LLM at query time: NOT MEASURED: set GEMINI_API_KEY (free tier is enough) and rerun
Parser plain_language_50.json: action acc 50/50, false-compute 0 (guessing), ...
Parser plain_language_holdout_30.json: action acc 30/30, false-compute 0 (guessing), ...
silent-failure experiment ... 'silent' = wrong AND no error AND auditor passes
official calculator checks filled: 0/48; mismatches: 0
=== PROJECT B | data: SYNTHETIC (run fetch_nyc311.py for real data) | LLM live: False ===
done in 34s; JSON in project_a/results and project_b/results
```

Latency and throughput differ per machine. Accuracy, determinism, traceability and the detection tables are deterministic (fixed seeds) and should match exactly.

## 4. Using Gemini (free tier)

1. Create a key in [Google AI Studio](https://aistudio.google.com/) and export it:
   ```bash
   export GEMINI_API_KEY="your-key"           # PowerShell: $env:GEMINI_API_KEY="your-key"
   export GEMINI_MIN_INTERVAL_S=7             # seconds between calls; raise it if you hit 429s
   ./run_all.sh
   ```
2. A full live run makes roughly 250 calls with the defaults: Project A benchmark `LLM_N` (60) + `DET_N` (5) x 10 repeats, Task 5 `LLM_N` (30), Project B about 13 windows x 200 rows / 25 rows per call. At 7 s spacing that is on the order of half an hour. Check your quota in AI Studio first; free-tier limits change.
3. To run only the Project A pieces: `LLM_N=60 GEMINI_MIN_INTERVAL_S=7 python -m project_a.benchmark`.
4. To evaluate the Gemini extractor of the plain-language parser (not part of `run_all.py`):
   ```bash
   python -c "from project_a.parser import evaluate_parser; evaluate_parser(use_llm=True)"
   ```

Behaviour worth knowing:

- **Caching.** `project_a/gemini_client.py` caches responses in `project_a/.gemini_cache.json` (git-ignored). Benchmarks pass `bypass_cache=True`, so latency and determinism numbers are always live. A cache hit is flagged `cache_hit: true`; never mix cached calls into latency tables. Delete the file to start fresh.
- **Retries.** HTTP 429/500/503 are retried with exponential backoff; `GEMINI_MIN_INTERVAL_S` throttles proactively.
- **Costs.** Every live call records its token counts and an estimate for the free tier ($0), a reference rate (default $0.15 / $0.60 per 1M input / output tokens) and the 2.5 Flash list rate (default $0.30 / $2.50). Rates change, so verify them and override with the `GEMINI_*_PER_M` variables.
- **No key, no fake LLM.** Without a key the LLM paths report `NOT MEASURED`. The `offline_stub` mode of `impl_b_llm` (and `compile_rules --offline`) just delegates to implementation (a) and is tagged `"mode": "offline_stub"`; it is for plumbing tests only and never feeds a results table. `GEMINI_STRICT=1` makes a missing key an error instead of a fallback.

### Environment variables

| Variable | Default | Effect |
|---|---|---|
| `GEMINI_API_KEY` | unset | Enables every live LLM path |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model name |
| `GEMINI_MIN_INTERVAL_S` | `0` | Minimum seconds between calls (use about 7 on the free tier) |
| `GEMINI_STRICT` | unset | `1` = never fall back to the offline stub |
| `GEMINI_CACHE_PATH` | `project_a/.gemini_cache.json` | Cache file location |
| `GEMINI_REF_IN_PER_M`, `GEMINI_REF_OUT_PER_M` | `0.15`, `0.60` | Reference price, USD per 1M tokens |
| `GEMINI_LIST_IN_PER_M`, `GEMINI_LIST_OUT_PER_M` | `0.30`, `2.50` | List price, USD per 1M tokens |
| `LLM_N` | `60` (Project A benchmark), `30` (Task 5) | Number of cases sent to impl (b) |
| `DET_N` | `5` | Cases repeated 10x for the (b) determinism check |
| `LLM_BATCH` | `25` | Rows per call in the Project B LLM reviewer |
| `LLM_WINDOW` | `200` | Rows per problem type shown to the Project B LLM reviewer |
| `RUN_LLM_200` | unset | Also run the full 200-case suite through (b) inside pytest |

## 5. Real NYC 311 data (Project B)

By default Project B uses `project_b/data/synthetic_nyc311_2023.jsonl` (12,000 generated rows, labelled SYNTHETIC in every output). To use the real 2023 data:

```bash
python -m project_b.fetch_nyc311 --max-rows 200000            # needs internet
python -m project_b.fetch_nyc311 --max-rows 200000 --token YOUR_SOCRATA_APP_TOKEN   # optional, higher rate limits
./run_all.sh                                                   # regenerates every Project B table
```

- It writes `project_b/data/nyc311_2023.jsonl`, sorted by created date. The loader prefers this file whenever it exists; delete it to return to synthetic data.
- Regenerate the synthetic sample with `python -m project_b.make_synthetic_sample --n 12000`. **Keep it at 10,000 rows or more** (the benchmark needs 2,000 reference + 4,000 clean + 4,000 injection rows; 3,000 and 6,000 were tried and crash with `IndexError`). The default of 12,000 is safe.
- The real file is large; add `project_b/data/nyc311_2023.jsonl` to `.gitignore` rather than committing it (GitHub rejects files over 100 MB).
- **Reference-sample caveat:** `fetch_nyc311` sorts rows by created time, and the benchmark takes the first 2,000 rows as the statistical reference. On real data that is the earliest few hours of January 1st, so seasonal and time-of-day differences can raise statistical false alarms for reasons unrelated to data quality. Consider drawing the reference sample at random across the year before trusting the real-data false-alarm numbers.
- The profile, detection rates and cost tables **will change** with real data. Update `RESULTS_B.md` from the new `project_b/results/*.json`.

## 6. Official-calculator cross-check (Project A, Task 1)

The assignment requires at least 30 cases checked against the Income Tax Department calculator. The repo ships 48 candidates; the two official columns are yours to fill, because they come from the website.

1. Open `project_a/data/official_calculator_checks.json`. Each row looks like:
   ```json
   {"id": "TC_006", "fy": "2024-25", "input": {"gross_salary": 700000}, "official_old": null, "official_new": null}
   ```
2. For each row, enter the same inputs on the official calculator (same FY, resident individual, salary only) and write the total tax payable, including cess, for each regime into `official_old` and `official_new`.
3. Run `python -m project_a.verify_official`. It reports how many rows are filled and lists mismatches. If a figure differs by under Rs 10, check the rounding convention (the engines apply sections 288A and 288B, rounding to the nearest Rs 10; `apply_288_rounding=False` gives exact rupees).

## 7. Running pieces individually

All commands run from the repo root.

### Project A

| Command | What it does |
|---|---|
| `python -m project_a.generate_task1_data` | Regenerates the structured test cases in `project_a/data/test_cases_200.json` (368 cases across FY 2024-25 and FY 2025-26; the filename is historical), with expected values from the independent oracle `project_a/tests/oracle.py` |
| `python -m project_a.benchmark` | Task 4 table: rupee-exact accuracy, 10 repeated runs, latency, cost per 1,000 requests, clause traceability for (a), (c) and, with a key, (b). Writes `results/benchmark.json` |
| `python -m project_a.parser` | Task 3: evaluates the plain-language parser on the 50 dev and 30 held-out descriptions |
| `python -m project_a.task5_law_change` | Task 5: FY 2025-26 change size, the silent-failure experiments, the first (buggy) compiled spec. Writes `results/task5.json` |
| `python -m project_a.verify_official` | Official-calculator comparison (section 6) |
| `python -m project_a.run_smoke [--llm \| --offline]` | Prints three sample taxpayers through every implementation |
| `python -m project_a.impl_c_compiled.compile_rules --fy 2024-25 [--offline]` | Asks Gemini to compile the rule text into a candidate DSL spec, validates it and diffs it against the reviewed spec. It never overwrites the reviewed spec (`compiled/fy2024_25.json`) |
| `pytest project_a -q` | Project A tests (55) |

### Project B

| Command | What it does |
|---|---|
| `python -m project_b.profiler` | Task 1: profiles the raw data (missing coordinates, unspecified boroughs, closed-before-created, ...) with counts and examples. Writes `results/profile.json` |
| `python -m project_b.benchmark_project_b` | Tasks 3 to 5: runs the 12 injected problem types through rules, statistics and (with a key) LLM review, then the hybrid pipeline. Writes `results/benchmark_b.json` |
| `python -m project_b.fetch_nyc311 ...` | Downloads real data (section 5) |
| `python -m project_b.make_synthetic_sample --n 12000` | Regenerates the synthetic sample |
| `pytest project_b -q` | Project B tests (24) |

## 8. Using the code from Python

```python
from project_a.common import TaxInput
from project_a.impl_a_rules import engine as A        # or impl_c_compiled.runtime / impl_b_llm.calculator

r = A.compute(TaxInput(gross_salary=1_800_000, age=32, sec_80c=150_000, health_self=20_000))
r["old"]["total_tax"], r["new"]["total_tax"]           # (297960, 215800)
r["recommendation"]["recommended"]                     # 'new'
r["recommendation"]["reason"]                          # 'New regime tax Rs 215,800; old regime tax Rs 297,960. ...'
r["new"]["fully_traceable"]                            # True: every rupee cites a clause (R-NEW-SLABS, R-288A, ...)
r["new"]["trace"][:2]                                  # [{'step': 'std', 'amount': 75000, 'clause': 'R-STD-NEW', ...}, ...]
```

Every implementation returns `{"old": ..., "new": ..., "recommendation": ...}`. Use `fy="2025-26"` for the Finance Act 2025 rules; an FY with no rules file raises a loud `ValueError` rather than silently using old numbers.

Plain language in, structured input or a question out:

```python
from project_a.parser import parse_plain_language

res = parse_plain_language("what is my tax on 12L")
res["status"]               # 'needs_clarification'
res["clarifying_questions"] # questions instead of guesses
res = parse_plain_language("Age 50. Gross 1.2 crore a year. 80C 1.5 lakh, no other deductions.")
res["status"], res["input"] # 'ok', TaxInput(...)
```

## 9. Tests

```bash
pytest -q project_a project_b          # 79 tests (55 + 24), about 13 s
pytest -q project_a -k oracle          # filter by name
RUN_LLM_200=1 GEMINI_API_KEY=... pytest -q project_a   # also push the large suite through impl (b)
```

The expected values in the test suite come from `project_a/tests/oracle.py`, a separately structured calculator, plus hand-derived anchor cases, so implementation (a) is not grading itself. A shared misreading of the law would still pass both, which is why the official-calculator check in section 6 matters.

## 10. Where each number lives

| Deliverable (hand-maintained) | Copy its numbers from |
|---|---|
| `RESULTS_A.md` (comparison table, Task 5 change log, final design) | `project_a/results/benchmark.json`, `project_a/results/task5.json` |
| `RESULTS_B.md` (per-problem table, real issues found, scale design) | `project_b/results/benchmark_b.json`, `project_b/results/profile.json` |
| `DECISION_MATRIX.md` | The two results documents above |
| `AI_USAGE.md` | Your own account of tools used and one AI mistake you caught |

The JSON files are overwritten on every run, so `git diff` after a rerun shows latency and throughput noise. That is expected.

## 11. Repository layout

```
.
├── run_all.sh / run_all.py          one command: tests + all results
├── requirements.txt                 pytest
├── RESULTS_A.md  RESULTS_B.md  DECISION_MATRIX.md  AI_USAGE.md
├── project_a/
│   ├── common.py                    TaxInput, rounding (s.288A/B), traceability auditor, recommendation
│   ├── rules_text/                  the rule prose per FY (clause IDs R-...); the prompt for impl (b)
│   ├── impl_a_rules/                (a) engine.py + rules_fy*.json
│   ├── impl_b_llm/                  (b) Gemini reads the rule text per request
│   ├── impl_c_compiled/             (c) dsl.py interpreter, compiled/fy*.json, compile_rules.py
│   ├── parser.py                    plain-language input: extract (rules or Gemini) -> deterministic gate
│   ├── gemini_client.py             cache, throttle, backoff, token and cost metadata
│   ├── generate_task1_data.py       test-suite generator
│   ├── benchmark.py  task5_law_change.py  verify_official.py  run_smoke.py
│   ├── data/                        test cases, plain-language sets, official-calculator checks
│   ├── results/                     benchmark.json, task5.json
│   └── tests/                       oracle.py, test_task2.py, ...
└── project_b/
    ├── injector.py                  the 12 corruption types at controlled rates
    ├── detectors/                   rules.py, statistical.py, llm_review.py
    ├── hybrid_pipeline.py           tier 1 rules -> tier 2 statistics -> tier 3 LLM on routed rows
    ├── profiler.py  fetch_nyc311.py  make_synthetic_sample.py  benchmark_project_b.py
    ├── data/                        synthetic (and, once fetched, real) 311 rows
    ├── results/                     benchmark_b.json, profile.json
    └── tests/
```

## 12. The design in 60 seconds

**Project A.** The tax arithmetic is deterministic and audited, so it belongs in rules. (a) is the hand-coded engine, with the numbers in per-FY JSON. (c) is a small rule language (`dsl.py`) that an LLM can draft from the rule text and a human reviews; it runs with no LLM. (b) hands the rule text to the model on every request. Every implementation returns a trace, and `common.verify_traceability` checks that each step cites a real clause, deductions add up, and the components reconcile with the total. That check catches inconsistent answers but not a consistent answer built on the wrong law, which is why the independent-oracle test suite and the official-calculator check exist. The plain-language parser may only extract; a deterministic gate decides whether to compute or ask, so missing or contradictory information produces a clarifying question and never a guess.

**Project B.** Cheap declarative rules run on every row, statistical checks run per batch, and an LLM sees only rows the first two tiers routed to it plus a small audit sample. The decision matrix ties each of the 12 problem types to the detector family that won on measured detection, false alarms and cost per million rows.

## 13. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `error: externally-managed-environment` | Your Python blocks system-wide `pip install` (PEP 668). Use `./run_all.sh` (creates `.venv`) or create a venv yourself (section 2) |
| `ModuleNotFoundError: No module named 'project_a'` | Run from the repo root and use `python -m project_a.<module>` rather than `python project_a/<file>.py` |
| `pytest: command not found` | Activate the venv, or `python -m pytest ...` |
| `IndexError: list index out of range` in `benchmark_project_b` | Sample under 10,000 rows. Regenerate with `python -m project_b.make_synthetic_sample --n 12000` or fetch the real data |
| Project A (b) shows `NOT MEASURED` | No `GEMINI_API_KEY` in the shell that runs the command. Export it, then rerun |
| `HTTP 429` or a very slow live run | Free-tier rate limit. Raise `GEMINI_MIN_INTERVAL_S` (for example 10) or lower `LLM_N`, `DET_N`, `LLM_WINDOW` |
| Live latency looks near zero | Cached responses. Benchmarks bypass the cache, but if you called the client yourself, delete `project_a/.gemini_cache.json` |
| Project B header says SYNTHETIC | Expected until `fetch_nyc311` has produced `project_b/data/nyc311_2023.jsonl` |
| `ValueError: No rules file for FY ...` | Intended. Add `rules_fy<YYYY_YY>.json`, `compiled/fy<YYYY_YY>.json` and `rules_text/fy<YYYY_YY>.md`, as in Task 5 |
| Results differ from `RESULTS_*.md` after a rerun | Only latency and throughput should vary. Anything else means data or code changed; check `git diff` |
| `./run_all.sh: Permission denied` | `chmod +x run_all.sh`, or `bash run_all.sh` |

## 14. Reproducibility notes

- Randomness is seeded (test-case generation, injection, sampling). Rerunning on the same data gives the same accuracy, detection and false-alarm numbers.
- Only wall-clock figures (latency, rows per second) depend on the machine.
- Live Gemini calls use temperature 0 and a fixed seed, but the 10x determinism test exists precisely because that does not guarantee identical output; report what you measure.
- Constants for the tax rules come from the Finance Acts 2024 and 2025 as the rule text records them. Confirm them against the official sources and the Income Tax Department calculator before relying on any figure.
