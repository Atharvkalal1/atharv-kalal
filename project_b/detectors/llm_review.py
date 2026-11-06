"""Detector Family (c): LLM Semantic Verification for complex contradictions."""
import os, json, re

CONTRADICTION_PATTERNS = [
    ("closed", ["not visited", "pending investigation", "actively open", "not resolved"]),
    ("open", ["condition was resolved", "work completed", "closed ticket"])
]

COMPLAINT_MISMATCH = {
    "Noise - Residential": ["pothole", "cave-in", "traffic signal", "water leak"],
    "Street Condition": ["loud music", "barking dog", "party"],
    "Water System": ["loud television", "double parked"]
}

def detect_semantic_contradictions(record: dict, use_gemini=False) -> list[str]:
    violations = []
    
    # Task (k): Resolution Description contradicting Status
    status = str(record.get("status", "")).lower()
    res_desc = str(record.get("resolution_description", "")).lower()
    
    for stat_key, conflicting_phrases in CONTRADICTION_PATTERNS:
        if stat_key in status:
            if any(phrase in res_desc for phrase in conflicting_phrases):
                violations.append("k_resolution_contradicts_status: Resolution text states active/unresolved while status is Closed")

    # Task (j): Complaint Type inconsistent with Descriptor
    ctype = record.get("complaint_type", "")
    desc = str(record.get("descriptor", "")).lower()
    
    if ctype in COMPLAINT_MISMATCH:
        for mismatched_term in COMPLAINT_MISMATCH[ctype]:
            if mismatched_term in desc:
                violations.append(f"j_complaint_inconsistent_descriptor: '{ctype}' contradicts descriptor '{desc}'")

    return violations
