# Fire AI: Rules vs. LLMs Take-Home Assignment

Complete implementation and empirical defense for the **Fire AI AI/ML Engineer Take-Home Assignment** by evaluating deterministic rules, statistical anomaly detectors, query-time LLMs, and hybrid architectures across two real-world enterprise projects.

---

## Quick Start (One Command Reproducibility)

To run the complete benchmark suite and reproduce every reported number in `RESULTS_A.md` and `RESULTS_B.md`:

```bash
# Clone the repository
git clone <your-repo-url>
cd <repo-folder>

# Run all test suites, benchmarks, and pipelines
python3 run_all.py
# Or on Linux / macOS:
bash run_all.sh
```

---

## Repository Structure & Deliverables

```
├── project_a/                       # Project A: Indian Income-Tax Engine
│   ├── common.py                    # Shared TaxInput, s.288A/B rounding, traceability auditor
│   ├── gemini_client.py             # Gemini client with free-tier cache, rate-limiter, backoff
│   ├── parser.py                    # Task 3: English & Hinglish plain-language parser
│   ├── generate_task1_data.py       # Task 1: 220+ structured test cases & 50 NL scenarios
│   ├── benchmark.py                 # Task 4: Accuracy, determinism, latency & cost harness
│   ├── task5_law_change.py          # Task 5: Finance Act 2025 migration & silent failure analysis
│   ├── data/
│   │   ├── test_cases_200.json      # 220 structured test cases with ground-truth expected taxes
│   │   └── plain_language_50.json   # 50 plain-language scenarios with classification metadata
│   ├── impl_a_rules/                # Implementation (a): Hand-coded rules
│   │   ├── engine.py
│   │   ├── rules_fy2024_25.json
│   │   └── rules_fy2025_26.json
│   ├── impl_b_llm/                  # Implementation (b): LLM at query time
│   │   └── calculator.py
│   ├── impl_c_compiled/             # Implementation (c): LLM-compiled rule DSL
│   │   ├── runtime.py
│   │   ├── dsl.py                   # Safe, deterministic AST expression interpreter
│   │   └── compiled/
│   │       ├── fy2024_25.json
│   │       └── fy2025_26.json
│   └── rules_text/                  # Statutory provisions text cited by clause ID
│       ├── fy2024_25.md
│       └── fy2025_26.md
│
├── project_b/                       # Project B: NYC 311 Data-Quality Engine
│   ├── profiler.py                  # Task 1: Real 2023 NYC 311 data profiler
│   ├── injector.py                  # Task 2: 12-type controlled corruption injector
│   ├── detectors/                   # Task 3: Three detector families
│   │   ├── rules.py                 # Declarative schema, type, PII regex, lat/lon bounds
│   │   ├── statistical.py           # Z-score null spikes, Jaccard near-duplicates
│   │   └── llm_review.py            # Gemini semantic contradiction auditor
│   ├── hybrid_pipeline.py           # Task 5: Tiered hybrid quality pipeline
│   ├── benchmark_project_b.py       # Task 4: 12-problem recall, false alarm & cost matrix
│   └── data/
│       └── sample_nyc311_2023.json  # 2023 NYC 311 baseline service requests
│
├── RESULTS_A.md                     # Project A comparison table, change log, 100k-user design
├── RESULTS_B.md                     # Project B evaluation table, real issues, 50M rows/day design
├── DECISION_MATRIX.md               # One row per component with quantitative justification
├── AI_USAGE.md                      # Disclosure of AI tools & s.87A marginal relief error caught
├── run_all.py                       # Single-command verification runner
└── run_all.sh                       # Executable bash wrapper
```

---

## Core Findings Summary

* **Project A (Income-Tax Engine)**:
  * Hand-coded rules (a) and compiled DSL (c) achieved **100.0% rupee-exact accuracy** with **0.23–0.69 ms latency** and **$0 run-time cost**.
  * Query-time LLM (b) had **27.7% calculation errors** and 13.3% non-deterministic drift on marginal relief, costing $0.75 per 1,000 requests with 1.45-second latency.
  * **Winner**: Compiled DSL rule engine for arithmetic, guarded by a hybrid plain-language extractor that asks clarifying questions instead of guessing.

* **Project B (Data Quality Engine)**:
  * Declarative rules caught schema drops, type errors, date formats, swapped coordinates, and timestamp reversals with **96–100% recall** at <0.05 ms/row and $0 cost.
  * Statistical checks caught aggregate agency null spikes with **100% recall**.
  * LLM review excelled only on nuanced semantic contradictions (resolution text contradicting "Closed" status and unmapped complaint descriptors).
  * **Winner**: The Tiered Hybrid Pipeline achieves **94.8% overall recall** at **56,932 rows/second** and **$20.70 per million rows** (a **98.6% cost reduction** vs pure LLM).
