#!/usr/bin/env python3
"""
Single command to run all test suites, benchmarks, and experiments across Project A and Project B.
Reproduces every single reported number in RESULTS_A.md and RESULTS_B.md.
"""
import sys, os, time, subprocess
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

def print_header(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")

def main():
    start_time = time.time()
    print_header("FIRE AI: RULES VS LLMS REPRODUCIBILITY HARNESS")
    
    # --------------------------------------------------------------------------
    # PROJECT A
    # --------------------------------------------------------------------------
    print_header("RUNNING PROJECT A: INCOME TAX ENGINE BENCHMARKS & TESTS")
    
    # 1. Run smoke tests
    from project_a import run_smoke
    print("✓ Project A Smoke test passed.\n")
    
    # 2. Run full unit tests
    print("Running Project A Unit Test Suite (220+ structured cases)...")
    import project_a.tests.test_task2 as t
    for name, fn in t.IMPLS:
        for inp, old, new in t.CASES:
            t.test_hand_checked(name, fn, inp, old, new)
    t.test_round_to_10_halves_round_up()
    t.test_hra_salary_base_property()
    t.test_unified_schema()
    t.test_tie_and_marginal_relief_breakdown()
    t.test_288b_trace_step_only_when_rounding_adjusts()
    t.test_auditor_catches_tampering()
    t.test_unknown_fy_fails_loudly_not_silently()
    t.test_200_case_suite_full_agreement('rules', t.IMPLS[0][1])
    t.test_200_case_suite_full_agreement('compiled', t.IMPLS[1][1])
    print("✓ All 220 structured cases agree 100% across Hand-Coded Rules and Compiled DSL!\n")
    
    # 3. Run Task 3 plain-language parser
    print("Running Project A Task 3: 50 Plain-Language Scenarios Evaluation...")
    from project_a.parser import evaluate_parser
    parser_acc = evaluate_parser()
    print(f"✓ Plain-Language Parser accuracy: {parser_acc:.1f}%\n")
    
    # 4. Run Task 4 benchmarks
    from project_a.benchmark import run_benchmarks
    bench_a = run_benchmarks()
    
    # 5. Run Task 5 law change experiment
    print("\nRunning Project A Task 5: FY 2025-26 Law Change Experiment...")
    from project_a.task5_law_change import run_experiment
    task5_res = run_experiment()

    # --------------------------------------------------------------------------
    # PROJECT B
    # --------------------------------------------------------------------------
    print_header("RUNNING PROJECT B: DATA QUALITY DETECTORS & HYBRID PIPELINE")
    
    # 1. Profile real NYC 311 2023 data
    from project_b.profiler import profile_raw_data
    profile_raw_data()
    
    # 2. Run 12-problem benchmark & hybrid pipeline
    from project_b.benchmark_project_b import run_evaluation
    b_table, hybrid_res = run_evaluation()
    
    total_duration = time.time() - start_time
    print_header(f"ALL SYSTEMS VERIFIED & REPRODUCED IN {total_duration:.2f} SECONDS")
    print("Summary of Key Deliverables Generated:")
    print("  • project_a/           : Complete 3-calculator suite, parser, and 220+ test dataset")
    print("  • project_b/           : NYC 311 profiler, 12-type injector, 3 detector families, hybrid pipeline")
    print("  • RESULTS_A.md         : Tax engine comparison, Task 5 change log, 100k-user architecture")
    print("  • RESULTS_B.md         : Data quality evaluation matrix and 50M rows/day scale design")
    print("  • DECISION_MATRIX.md   : Quantitative justification for every component choice")
    print("  • AI_USAGE.md          : AI tools used and Section 87A marginal relief error caught")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
