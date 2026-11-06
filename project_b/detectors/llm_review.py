"""Detector family (c): LLM review of batch samples (Gemini). Live only: without GEMINI_API_KEY nothing is simulated.
One call reviews `batch_rows` rows (default 25). The model is shown only the rows and the 12-type taxonomy, never reference stats."""
from __future__ import annotations
import json, os
from project_a import gemini_client as G

TAXONOMY = """a renamed/dropped column (row lacks an expected column or has a renamed one)
b column type change (a numeric field arrives as a string)
c date format differs from the others (e.g. MM/DD/YYYY hh:mm AM vs ISO)
d latitude/longitude swapped (NYC lat ~40.7, lon ~-73.9)
e exact duplicate of another row in this list
f near-duplicate of another row (same request, slightly altered timestamp/text, different unique_key)
g null spike: many rows of one agency have a missing field
h closed_date earlier than created_date
i ZIP code inconsistent with borough
j complaint_type inconsistent with descriptor
k resolution_description contradicts status (e.g. Closed but text says pending; Open but text says resolved)
l personal data (phone, email, SSN, person name) inside free text"""


def rows_to_text(rows, start=0):
    return "\n".join(f"{start + i}|" + "|".join(f"{k}={'' if v is None else v}" for k, v in r.items()) for i, r in enumerate(rows))


def build_prompt(rows, start=0):
    return (f"You are a data-quality reviewer for NYC 311 service-request rows. Report ONLY real problems.\nProblem types:\n{TAXONOMY}\n\n"
            "Each line is `index|col=value|...`. Return JSON: {\"findings\": [{\"row\": <index>, \"type\": \"<a-l>\", \"field\": \"<column>\", \"reason\": \"<short>\"}]}. "
            "For type g use row null and add \"agency\". If nothing is wrong return {\"findings\": []}.\n\nROWS:\n" + rows_to_text(rows, start))


def est_tokens(text): return max(1, len(text) // 4)


def review(rows, batch_rows=int(os.environ.get("LLM_BATCH", 25))):
    """Returns (findings, usage) where usage has calls, prompt_tokens, output_tokens, latency_s (all measured)."""
    if not G.has_key(): raise RuntimeError("GEMINI_API_KEY not set")
    findings, u = [], dict(calls=0, prompt_tokens=0, output_tokens=0, latency_s=0.0)
    for s in range(0, len(rows), batch_rows):
        out, meta = G.generate_json(build_prompt(rows[s:s + batch_rows], s), system="Precise data-quality auditor. JSON only.", use_cache=False)
        u["calls"] += 1; u["prompt_tokens"] += meta["prompt_tokens"]; u["output_tokens"] += meta["output_tokens"]; u["latency_s"] += meta["latency_s"]
        for f in out.get("findings", []):
            findings.append({"row": f.get("row"), "type": str(f.get("type", ""))[:1].lower(), "field": f.get("field"), "msg": f.get("reason", ""), **({"agency": f["agency"]} if f.get("agency") else {})})
    return findings, u


def cost_usd(prompt_tokens, output_tokens):
    c = G.estimate_cost(prompt_tokens, output_tokens)   # per-1000-requests scaling inside; here return raw $ for these tokens
    r, l = G.REFERENCE_RATES, G.LIST_RATES
    return {"reference": (prompt_tokens * r[0] + output_tokens * r[1]) / 1e6, "list": (prompt_tokens * l[0] + output_tokens * l[1]) / 1e6}


def project_cost_per_million_rows(sample_rows, batch_rows=25, out_tokens_per_call=300):
    """PROJECTION (not a measurement): prompt tokens from the real prompt text (chars/4), output tokens assumed."""
    pt = sum(est_tokens(build_prompt(sample_rows[s:s + batch_rows], s)) for s in range(0, len(sample_rows), batch_rows))
    calls = -(-len(sample_rows) // batch_rows); ot = calls * out_tokens_per_call; k = 1e6 / len(sample_rows)
    c = cost_usd(pt * k, ot * k)
    return {"basis": "PROJECTION: prompt tokens ~ chars/4 of the real prompt; output tokens assumed 300/call; Gemini 2.5 Flash rates in gemini_client.py",
            "prompt_tokens_per_row": round(pt / len(sample_rows), 1), "usd_per_million_rows_reference_rates": round(c["reference"], 2), "usd_per_million_rows_list_rates": round(c["list"], 2)}
