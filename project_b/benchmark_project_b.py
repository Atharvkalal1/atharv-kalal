"""Task 4: Complete Evaluation of all 3 Detector Families across all 12 problem types."""
import json, time
from pathlib import Path
from project_b.injector import CorruptionInjector
from project_b.detectors.rules import detect_rule_violations
from project_b.detectors.statistical import detect_statistical_anomalies
from project_b.detectors.llm_review import detect_semantic_contradictions
from project_b.hybrid_pipeline import HybridQualityPipeline

def run_evaluation():
    data_file = Path(__file__).parent / "data" / "sample_nyc311_2023.json"
    clean_records = json.loads(data_file.read_text())[:1000]
    
    inj = CorruptionInjector(seed=42)
    corrupted_records, ground_truth = inj.inject(clean_records, rate=0.05)
    
    # Mapping problem types
    problem_keys = [
        ("a", "Renamed or dropped col"),
        ("b", "Column type change"),
        ("c", "Date format switch"),
        ("d", "Lat/Lon swapped"),
        ("e", "Exact duplicates"),
        ("f", "Near-duplicates"),
        ("g", "Null spike in agency"),
        ("h", "Closed earlier than created"),
        ("i", "ZIP inconsistent w/ borough"),
        ("j", "Complaint inconsistent desc"),
        ("k", "Resolution contradicts status"),
        ("l", "PII in free-text fields")
    ]
    
    print("=== PROJECT B EVALUATION (12 Problem Types across 3 Detector Families) ===\n")
    
    results_table = []
    
    # 1. Test clean batch for False Alarms
    clean_rule_hits = sum(1 for r in clean_records if detect_rule_violations(r))
    clean_alerts, clean_stat_flags = detect_statistical_anomalies(clean_records)
    clean_stat_hits = sum(1 for flags in clean_stat_flags.values() if flags)
    clean_llm_hits = sum(1 for r in clean_records if detect_semantic_contradictions(r))
    
    # Run detectors on corrupted
    rule_detected = [detect_rule_violations(r) for r in corrupted_records]
    _, stat_flags = detect_statistical_anomalies(corrupted_records)
    llm_detected = [detect_semantic_contradictions(r) for r in corrupted_records]
    
    for prefix, name in problem_keys:
        # Ground truth indices
        gt_indices = set(i for i, gt in enumerate(ground_truth) if any(t.startswith(prefix) for t in gt["corruption_types"]))
        count = len(gt_indices)
        
        # Detection by Rules
        hits_rule = sum(1 for i in gt_indices if any(v.startswith(prefix) or prefix in v for v in rule_detected[i]))
        recall_rule = (hits_rule / count * 100) if count else 0.0
        
        # Detection by Stats
        hits_stat = sum(1 for i in gt_indices if any(v.startswith(prefix) for v in stat_flags.get(i, [])))
        recall_stat = (hits_stat / count * 100) if count else 0.0
        
        # Detection by LLM
        hits_llm = sum(1 for i in gt_indices if any(v.startswith(prefix) for v in llm_detected[i]))
        recall_llm = (hits_llm / count * 100) if count else 0.0
        
        best = "Rules" if recall_rule >= 90 else ("Stats/ML" if recall_stat >= 90 else "LLM")
        
        results_table.append({
            "problem": f"({prefix}) {name}",
            "count": count,
            "rules_recall": f"{recall_rule:.0f}%",
            "stat_recall": f"{recall_stat:.0f}%",
            "llm_recall": f"{recall_llm:.0f}%",
            "best_fit": best
        })

    print("| Problem Type | Ground Truth | (a) Rules Recall | (b) Stats Recall | (c) LLM Recall | Best Fit |")
    print("|---|---|---|---|---|---|")
    for r in results_table:
        print(f"| {r['problem']} | {r['count']} | {r['rules_recall']} | {r['stat_recall']} | {r['llm_recall']} | {r['best_fit']} |")

    # 2. Hybrid Pipeline Benchmark
    pipe = HybridQualityPipeline()
    res = pipe.process_batch(corrupted_records)
    print("\n=== HYBRID PIPELINE END-TO-END PERFORMANCE ===")
    print(f"Total Rows Processed: {res['total_rows']:,}")
    print(f"Corruptions Caught: {res['corrupted_rows_detected']}")
    print(f"Execution Latency: {res['latency_ms']} ms ({res['throughput_rows_per_sec']:,} rows/sec)")
    print(f"Estimated Cost: ${res['cost_usd']:.4f} per 1,000 rows (vs $1.50 for pure LLM on 100% rows)")
    
    return results_table, res

if __name__ == "__main__":
    run_evaluation()
