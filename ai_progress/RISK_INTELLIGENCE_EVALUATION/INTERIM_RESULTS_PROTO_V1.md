# INTERIM — B prototype v1 (LLM-led + tool-verified, before binding fix), judge-scored (claude-b, 2026-11-01 23:05)
NOT a decision document: A0 (old RiskScope) and A1 (direct Qwen) judge scores are still queued; judge = qwen3.6:27b (self-judging bias on 27B answers); deterministic caps applied; raw outputs in `runs/proto_*`.
| Arm | cases | judge mean /100 | derived answers (rubric numbers) | judge-listed critical failures | notes |
|---|---|---|---|---|---|
| A0 old RiskScope (mechanical scorer, earlier) | 8B 30 / 27B 12 | 5.6 / ≈6.5 | 0 / 28, 0 / 11 | 0 (nothing said) | 100% fixed scaffold |
| B-v1 qwen3:8b | 17 | **63.5** | 6 / 17 | **15 of 17 cases have ≥1** (wrong binding BB01; 0W power BB04; compound-interest misuse BB17; NPV double count BB20; BOM-freeze violated BB11; data marked "假設值" BB21 …) | useful content but many real errors |
| B-v1 qwen3.6:27b | 12 | **94.6** (11/12 ≥ 90) | 9 / 11 | 1 (BB07: 10件 instead of 10萬件 — the 萬 unit bug) | self-judged → treat as upper bound until A1 and a human spot-check; BB10 injection refused + 50萬 overspend; BB14 43.2/23.2 correct |
## What this already shows
1. The fixed scaffold, not the model, was the main limiter: the same 27B that scored ≈6 inside A0 scores ~95 (judged) when it may reason over the documents. The 8B version is far better than A0 but unreliable (wrong bindings/formulas) → needs the new binding verification, and a safety review of every accepted number.
2. Real defects of v1 caught by the judge map onto my fixes: BB01 binding, BB07 萬 unit, "假設值" mislabel (document numbers without units were not in the ledger → inflated `ungrounded` count: 50 on 27B) → v2 + `Ledger.bare`.
3. Not yet shown: that B beats direct Qwen (A1) — if A1 scores similarly, the value of B is its verification/provenance/safety, not the raw answer quality; then decision must weigh unsupported-claim rate, critical failures and traceability, not only the judge score.
## Pending (queue, same lock): judge A1 direct 27B/8B, judge A0 27B/8B subsets, v2 (binding-verified) 8B then 27B + judge. Then the 3-way table, human spot-check of ≥6 cases, and only then an adoption decision.
