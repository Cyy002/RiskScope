# Architecture experiment: LLM-led reasoning + tool verification + provenance + guards (claude-b, 2026-11-01)
Authorised by the user: replace the fixed-scaffold core if experiments show it limits value. Hypothesis to TEST (not assume): the failure is the architecture (fixed G-A/B/C scaffold + "paraphrase only" + M7 number blacklist), so letting the model reason over the case documents while TOOLS verify every number gives far higher decision value without losing safety.

## Candidate B (prototype, isolated: `tools/proto_llm_led.py`, no app/* edits)
1. Ledger (`app/ledger.py`): every quantity from the question + ACL-visible documents gets an id Q#, source, version, span.
2. LLM (one call, JSON) returns a structured analysis: core issue, facts **with source ids**, unknowns (+how to obtain), hard constraints, conflicts, **calculations as formulas over Q ids**, risks with cause chains + severity basis, options (feasibility / constraint violations / pros / cons), ordered actions, "what would change the decision".
3. Tools: a safe AST arithmetic evaluator recomputes every calculation (model-stated results are ignored; assumed inputs are flagged ⚠).
4. Deterministic renderer shows provenance; any number in model prose not grounded in the ledger nor tool-computed is tagged ⚠未佐證 (counted); approval-like claims tagged; instruction-like document text (injection) is reported and never obeyed; document conflicts shown side by side (never picked silently).
5. (Existing, unchanged) ACL, retrieval allowlist, human-approval gate, M7 for claim checks.
Comparison arms (same 12 hard cases, same rubric, same judge, same deterministic caps): A0 current RiskScope (baseline, kept), A1 direct Qwen (control), **B prototype** with qwen3:8b and qwen3.6:27b. Judge = qwen3.6:27b blind; self-judging bias on 27B answers is flagged; deterministic checks (derived numbers present, forbidden phrases) cap the score, and the ungrounded-number count + all raw JSON are saved for human spot-check.
## Decision rule
Adopt B (and then integrate into app/ with tests) only if it beats A0 by a large margin AND is not worse than A1 on critical failures/ungrounded numbers, with prototype 8B≥ A0 and 27B≥ A1-class value. Otherwise analyse and iterate (e.g. two-stage, retrieval, per-domain calculators). No claim of improvement without these numbers; holdout stays sealed until a stable candidate exists.
## Queue
All batches through `tools/ollama_queue.sh`: direct-Qwen (running) → judge_all.sh → proto_all.sh (proto 8B → judge → proto 27B → judge). Logs /tmp/{direct,judge_all,proto_all}.log.
