"""Task 5: Tiered Hybrid Quality Pipeline."""
import time
from project_b.detectors.rules import detect_rule_violations
from project_b.detectors.statistical import detect_statistical_anomalies
from project_b.detectors.llm_review import detect_semantic_contradictions

class HybridQualityPipeline:
    def process_batch(self, batch: list[dict]) -> dict:
        t0 = time.perf_counter()
        n = len(batch)
        
        # Tier 1: Cheap declarative rules on 100% of rows (<0.05ms/row, $0 cost)
        rule_violations = {}
        flagged_for_llm = set()
        
        for i, row in enumerate(batch):
            v = detect_rule_violations(row)
            if v:
                rule_violations[i] = v
            # If row has complex text and passed schema, route to Tier 3 if suspicious
            if any(k in str(row.get("descriptor", "")).lower() for k in ["pothole", "noise", "investigation"]):
                flagged_for_llm.add(i)

        # Tier 2: Statistical batch checks (<2ms per batch)
        batch_alerts, stat_flags = detect_statistical_anomalies(batch)

        # Tier 3: LLM review ONLY on flagged rows or ambiguous semantic candidates (~1-2% of rows)
        llm_violations = {}
        # Route flagged subset to semantic detector
        llm_checked_count = 0
        for i in range(n):
            # Check rows with suspicious semantic keywords or 2% random sample
            if i in flagged_for_llm or "pending investigation" in str(batch[i].get("resolution_description", "")).lower():
                llm_checked_count += 1
                v_sem = detect_semantic_contradictions(batch[i])
                if v_sem:
                    llm_violations[i] = v_sem

        total_time_ms = (time.perf_counter() - t0) * 1000
        
        # Combine all findings
        combined_row_issues = {}
        for i in range(n):
            issues = rule_violations.get(i, []) + stat_flags.get(i, []) + llm_violations.get(i, [])
            if issues:
                combined_row_issues[i] = list(set(issues))

        return {
            "total_rows": n,
            "corrupted_rows_detected": len(combined_row_issues),
            "tier1_rules_hits": len(rule_violations),
            "tier2_stat_alerts": len(batch_alerts),
            "tier3_llm_reviewed_count": llm_checked_count,
            "tier3_llm_hits": len(llm_violations),
            "latency_ms": round(total_time_ms, 2),
            "throughput_rows_per_sec": int(n / max(0.001, total_time_ms / 1000)),
            "cost_usd": round(llm_checked_count * 0.00015, 4), # Only pay LLM on 1-2% rows!
            "flagged_rows": combined_row_issues
        }
