#!/usr/bin/env python3
"""One command: python run_all.py   (set GEMINI_API_KEY to also measure the LLM columns; set nothing to run fully offline)
Regenerates every number in RESULTS_A.md / RESULTS_B.md into project_*/results/*.json and exits non-zero if any test fails."""
import subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).parent.resolve(); sys.path.insert(0, str(ROOT))


def hdr(t): print("\n" + "=" * 78 + f"\n  {t}\n" + "=" * 78)


def main():
    t0 = time.time()
    hdr("1. test suites (pytest)")
    if subprocess.call([sys.executable, "-m", "pytest", "-q", str(ROOT / "project_a"), str(ROOT / "project_b")], cwd=ROOT): sys.exit("TESTS FAILED")
    hdr("2. Project A: regenerate suite, benchmark, Task 5, official-calculator status")
    from project_a import generate_task1_data; generate_task1_data.generate_test_cases()
    from project_a.benchmark import run_benchmarks; run_benchmarks()
    from project_a.parser import evaluate_parser; evaluate_parser()
    from project_a.task5_law_change import run_experiment; run_experiment()
    from project_a.verify_official import main as v; v()
    hdr("3. Project B: profile + 12-problem benchmark + hybrid")
    from project_b.profiler import profile_raw_data; profile_raw_data()
    from project_b.benchmark_project_b import run; run()
    hdr(f"done in {time.time() - t0:.0f}s; JSON in project_a/results and project_b/results")


if __name__ == "__main__":
    main()
