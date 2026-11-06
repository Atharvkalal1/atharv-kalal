"""Task 5: tiered hybrid pipeline.
  Tier 1 rules on every row (declarative, $0) -> Tier 2 statistics per batch ($0) -> Tier 3 LLM only on routed rows:
     routed = rows where exactly one family fired (disagreement) or the finding is semantic (j, k) and unconfirmed, plus a small random audit sample.
Without GEMINI_API_KEY tier 3 is NOT executed; the pipeline still reports exactly which rows would be routed and the projected cost."""
from __future__ import annotations
import random, time
from project_b.detectors import rules, statistical, llm_review
from project_a import gemini_client as G


class HybridPipeline:
    def __init__(self, ref, contract, audit_rate=0.01, seed=0, llm=None):
        self.ref, self.contract, self.audit_rate, self.rnd = ref, contract, audit_rate, random.Random(seed)
        self.llm = G.has_key() if llm is None else llm

    def process(self, batch):
        t0 = time.perf_counter()
        f1 = rules.detect(batch, self.contract); f2 = statistical.detect(batch, self.ref); t12 = time.perf_counter() - t0
        k1 = {(f["row"], f["type"]) for f in f1 if f["row"] is not None}; k2 = {(f["row"], f["type"]) for f in f2 if f["row"] is not None}
        both, only = k1 & k2, k1 ^ k2
        routed = {r for r, t in only if t in ("j", "k", "l", "f")} | {r for r, t in (k1 | k2) if t in ("j", "k") and (r, t) not in both}
        routed |= {i for i in range(len(batch)) if self.rnd.random() < self.audit_rate}
        findings = {}
        for f in f1 + f2: findings.setdefault((f["row"], f["type"], f.get("agency")), f)
        info = {"rows": len(batch), "tier1_findings": len(f1), "tier2_findings": len(f2), "routed_to_llm": len(routed),
                "routed_pct": round(100 * len(routed) / max(1, len(batch)), 2), "tier12_seconds": round(t12, 4), "llm_executed": False}
        if routed and self.llm:
            idx = sorted(routed); sub = [batch[i] for i in idx]
            lf, u = llm_review.review(sub)
            for f in lf:
                if isinstance(f["row"], int) and 0 <= f["row"] < len(idx):
                    f = dict(f, row=idx[f["row"]]); findings.setdefault((f["row"], f["type"], f.get("agency")), dict(f, source="llm"))
            info |= {"llm_executed": True, "llm_calls": u["calls"], "llm_prompt_tokens": u["prompt_tokens"], "llm_output_tokens": u["output_tokens"],
                     "llm_usd_reference": round(llm_review.cost_usd(u["prompt_tokens"], u["output_tokens"])["reference"], 5)}
        elif routed:
            proj = llm_review.project_cost_per_million_rows([batch[i] for i in sorted(routed)][:200] or batch[:25])
            info |= {"llm_projected_usd_per_million_routed_rows": proj["usd_per_million_rows_reference_rates"], "llm_projection_basis": proj["basis"]}
        info["wall_seconds"] = round(time.perf_counter() - t0, 4)
        return list(findings.values()), info
