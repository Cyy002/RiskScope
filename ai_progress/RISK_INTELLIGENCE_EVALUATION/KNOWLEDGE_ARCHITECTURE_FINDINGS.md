# B1/B2 — Knowledge architecture findings (claude-b, 2026-11-01)
Method: read app/{retrieval,db,analyzer,engineering,chat}.py (read-only, no edits) + ran 15 new cross-domain cases through the real `chat_turn()` pipeline with a throwaway DB per case (tools/run_cases.py). Evidence: `runs/claude-b_nollm_deterministic_dev/` (deterministic path only — **no LLM was called in this run, so it is not a real-LLM baseline**; the real-LLM baseline is Claude A's task A3).

## What the "knowledge" is
- Documents: whatever rows exist in `documents` (demo project = 6 hand-seeded synthetic docs). Retrieval (`retrieval.get_context`) = ACL allowlist first (good, safe), then crude token-overlap scoring, top-6 excerpts ≤2400 chars. No FTS, no chunking, no embeddings, no per-chunk citations.
- Facts: the `facts` table has exactly 5 hand-seeded keys (supply/motor voltage+current, aux current), each linked to a document+version (ACL/staleness checked in `read_facts`). Nothing extracts facts from documents; there is no ingestion path (no API to add documents at all).
- Dependencies: a fixed hand-written edge list; `trace_impact` walks it from a per-focus root node. Cases outside the 10 built-in focuses get `custom` → no impact graph.
- Decision history / risk register / test records: none exist as data.

## How an analysis is really produced
1. Deterministic engineering rule exists for ONE thing: `power_continuous` (24V/current budget).
2. Every other focus goes through `_generic_decision_support`: **a fixed 3-option scaffold (G-A keep plan / G-B adjust schedule / G-C find substitute), all `unverified`, one fixed risk `R-UNVALIDATED-ANALYSIS`**; the only case-specific inputs are (a) `project_signals` values and (b) two regexes for "交期不能延後"/"禁止更換供應商".
3. The LLM may only paraphrase that scaffold; `_reply_is_trustworthy` (M7) rejects any schedule/cost/percent/power number the engine did not compute.
**So analytical content comes from (1) one electrical rule and (2) a template; NOT from the user's documents or general engineering knowledge, and the LLM is deliberately forbidden to add any.**

## Measured evidence (deterministic path, 15 dev cases = 16 turns, 12+ domains)
- **16 turns produced exactly 1 distinct reply** (byte-identical) — the same text for a critical-path problem, a battery-sizing problem, a prompt-injection purchase request, and a vaccine cold-chain excursion.
- None of the verifiable answers appears: critical path 10 wk (BB01), Tj 312.5 °C (BB04), −60萬 (BB07), 23.2 min error budget (BB14), 29.6 h runtime (BB15), 26.4 % reject probability (BB12), payback 2.67 y (BB02) — all absent.
- The BB05 contradictory-documents case and BB10 injected-instruction document are never even read for content (retrieved as `sources`, never reasoned over).
Expected consequence for the real-LLM path (to be confirmed by Claude A's baseline): replies may read more fluently but cannot contain case-specific reasoning or calculations without being M7-rejected → fall back to the identical template. Likely classes: *generic advice, no calculation, no prioritisation, no option trade-offs, M7 over-rejection of correct numbers* (the "right" answer for BB01 literally contains "10 週", a schedule-unit number M7 treats as fabricated).

## B2 — is a database/RAG the fix? (preliminary, pending A's real baseline)
**More documents or vector RAG alone would NOT help**: the bottleneck is not missing text — BB01–BB15 supply the needed facts inside the case documents/question and the system still ignores them. Stuffing them into the LLM prompt is exactly what M7 is built to block (and rightly so: unverified numbers).
What is missing is a **grounded quantitative reasoning layer**:
1. **Quantity ledger (knowledge layer, mine):** extract (value, unit, role, source doc id+version, character span) from question + ACL-visible documents; every quantity must be literally grounded (same rule as M6 grounding), carry provenance, and be tagged `document | user_assumption | derived`. Store with project/ACL/version in SQLite; FTS5 (verified available in the container's SQLite 3.53) over document chunks with stable chunk ids for citation. Mark documents by trust level; **document text is data, never instructions** (BB10).
2. **Calculators (core, Claude A's call):** a small library of deterministic, unit-tested methods selected by a router — critical path/float, series/parallel reliability, break-even/payback, power-thermal budget, error budget, sampling OC curve, energy budget. Each takes ledger quantities, returns result + formula + inputs' provenance, and registers its outputs as *engine-computed* so M7 can trust "10 週" the same way it trusts "14A".
3. **M7 generalisation (core):** trusted-number set = engine-computed ∪ literally present in grounded inputs; role/unit checks stay (no fabricated approval/cost).
4. **Contradiction/staleness detection (knowledge layer, mine):** same quantity key with different values across docs → surface both with dates/versions, do not pick silently (BB05).
Decision rule to honour the user's "don't build RAG for its own sake": implement 1+4 (needed: provenance, FTS for large doc sets, injection defence, contradiction handling) only after A's baseline confirms the failure classes above; evaluate with-vs-without on the same cases; drop it if it does not raise scores.

## Handoffs / coordination
- Per the commander's rule: no edits to app/*.py or app/static/*, no concurrent long Ollama runs. All my artifacts live under `tools/`, `BENCHMARK_CASES/dev/BB*.json`, `runs/`.
- Claude A: please run the real-LLM baseline with `python tools/run_cases.py --cases BENCHMARK_CASES/dev --out runs/<name> --llm` (env OLLAMA_URL/OLLAMA_MODEL; `--app-root ai_progress/RISK_INTELLIGENCE_EVALUATION/baseline_snapshot` pins the pre-change code). BB cases (15) are dev-set; do NOT reuse them as holdout. Rubrics are inside each JSON (`rubric`) and are not passed to the agent.
