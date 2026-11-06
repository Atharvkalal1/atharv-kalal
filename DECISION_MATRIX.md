# Decision matrix (every row cites a measurement in `results/*.json`; "NM" = not measured here)
| Component / check | Choice | Measurement | Trade-off, stated honestly |
|---|---|---|---|
| A: tax arithmetic | **Rule** (a or c) | 368/368 vs independent oracle; 0.3-0.8 ms; $0; 10x identical | Rules can be wrong in parameters *silently* (Task 5 experiment); mitigated by oracle suite, not by runtime checks |
| A: rule authoring per Budget | **LLM drafts, human reviews** | First compiled FY25-26 spec was wrong (17/119); diff for a correct update is ~20 lines | LLM saves typing, not review; (c) vs (a) show no accuracy difference |
| A: query-time LLM (b) | **Not chosen** | NM (needs key) | Cost, latency and determinism unmeasured here; chosen against on prior grounds, to be confirmed by the run |
| A: audit/trace | **Rule** | 100% traceable (a, c); auditor missed wrong-parameter updates (silent) | Trace proves consistency with the clauses used, not that the clause set is complete |
| A: free text -> facts | **Hybrid** (LLM extract, rule gate) | Gate: 0 false-compute on 80 labelled cases; rules-extractor field-exact 32/32 | Same author wrote parser and sets: optimistic; LLM extractor NM |
| B: a/b/c schema, type, format | **Rule** | recall 1.00, FA 0, 53k rows/s | Needs per-tenant contract; stats alternative equal here but 7x slower |
| B: d swapped coordinates | **Rule** | 1.00 / FA 0 | Needs bbox per tenant |
| B: e exact duplicates | **Rule** (key+content) | 1.00 | Within-batch only; cross-batch needs state |
| B: f near-duplicates | **Statistical** (MinHash) | 0.52 vs rules 0.40, precision ~0.5 | Weak on both; candidate for LLM/human adjudication |
| B: g null spike | **Statistical** | 1.00 recall, 0.99 precision, agency identified; rules give batch alert only | Needs reference null rates |
| B: h closed<created | **Rule** | 1.00 | Real-data noise gives precision <1 |
| B: i ZIP vs borough | **Rule** | 0.99 vs stats 0.72 | Official ranges are maintenance cost |
| B: j complaint vs descriptor | **Rule allow-list or stats** | both 1.00 | Long-tail real descriptors will raise FA (verify on real data); LLM NM |
| B: k resolution vs status | **Hybrid** (rules/stats, LLM adjudication) | rules 0.94, NB stats 0.73 | Lexicon misses new phrasing; LLM benefit NM |
| B: l PII | **Rule**, LLM/NER for names | regex 1.00 on phone/email/SSN | Names undetected by regex; unmeasured |
| B: pipeline | **Tiered hybrid** | recall 0.958, 1.7% routed, 0.77% clean flagged, ~6k rows/s | Tier 3 NM; all B numbers are synthetic until real data is fetched |
