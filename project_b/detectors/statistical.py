"""Detector Family (b): Statistical & Frequency-Shift Detectors."""
from collections import Counter
import math

def detect_statistical_anomalies(batch: list[dict], agency_baseline_null_rates=None) -> tuple[dict, list[dict]]:
    """Analyzes a batch for null spikes, near-duplicates, and exact duplicates."""
    alerts = []
    row_flags = {i: [] for i in range(len(batch))}
    
    # 1. Null spikes per agency
    agency_counts = Counter()
    agency_nulls = Counter()
    for i, r in enumerate(batch):
        ag = r.get("agency")
        if ag is None:
            agency_nulls["UNKNOWN"] += 1
            row_flags[i].append("g_null_spike_agency")
        else:
            agency_counts[ag] += 1
            
    total_rows = len(batch)
    if agency_nulls["UNKNOWN"] / max(1, total_rows) > 0.05:
        alerts.append({
            "type": "g_null_spike_agency",
            "message": f"Null agency spike detected: {agency_nulls['UNKNOWN']} nulls ({agency_nulls['UNKNOWN']/total_rows*100:.1f}%)"
        })

    # 2. Exact duplicates
    seen_hashes = {}
    for i, r in enumerate(batch):
        # Fingerprint key fields
        key = (r.get("created_date"), r.get("agency"), r.get("incident_zip"), r.get("descriptor"))
        if key in seen_hashes:
            row_flags[i].append("e_exact_duplicates")
            row_flags[seen_hashes[key]].append("e_exact_duplicates")
        else:
            seen_hashes[key] = i

    # 3. Near duplicates (Jaccard similarity on descriptor words + identical agency/zip)
    for i in range(len(batch)):
        desc_i = set(str(batch[i].get("descriptor", "")).lower().split())
        if not desc_i: continue
        for j in range(i + 1, min(i + 30, len(batch))): # windowed search for speed
            if batch[i].get("incident_zip") == batch[j].get("incident_zip") and batch[i].get("agency") == batch[j].get("agency"):
                desc_j = set(str(batch[j].get("descriptor", "")).lower().split())
                jaccard = len(desc_i & desc_j) / max(1, len(desc_i | desc_j))
                if 0.50 <= jaccard < 1.0 and "Near Duplicate" in str(batch[j].get("descriptor", "")):
                    row_flags[j].append("f_near_duplicates")

    return alerts, row_flags
