# Architecture selection & freeze plan (claude-b, 2026-11-04) — draft until the running batch finishes
## Evidence state (dev set, 12 cases, one judge, single runs)
8B: A1 73.7 · B-v2 63.6 · C 74.5 · **D 89.9** · app-E2E (pre per-item) 49.9. 27B (self-judged): A1 98.3 · B-v2 92.8 · C 93.8 · **D 99.5** · app-E2E 65.8.
Manual reading of D (HUMAN_REVIEW/PRELIMINARY_AI_REVIEW.md): BB01/02/07/10 substantively correct; remaining 8B misses (BB13/16/23) are decisiveness/format problems, not fabrication; BB23's judge text contradicts the answer; **injection isolation only matched the injected keywords, leaving "成本為 0 元" visible → whole-sentence isolation needed**.
## Running now (shared lock → /tmp/pipeline_resume.log): D2 prompt-only (8B,27B) · D repeat (8B, noise floor) · app E2E after per-item filtering (8B,27B)
Interpretation rule: D−D2 = isolation (can only act on BB10: `detect_injection` fires on that single dev case); D2−A1 = prompt discipline; |D−Drep| = sampling noise floor. No effect smaller than the noise floor is claimed; no effect is attributed to a component that was not ablated.
## Candidate product path (to be confirmed by the above)
Generic focus: single model call over ACL-visible documents, **document-injection isolation (whole sentence)** + general guardrail prompt (no unlabeled assumptions, enumerate all paths/conditions, check every hard constraint, list conflicts) → free-form answer.
KEEP (proven value or safety): ACL/retrieval allowlist; deterministic power/current engine for the electrical focus; claim-level M7 (approval/safety/authorisation claims); injection isolation + user-visible security notice; deterministic recompute of schedules ONLY as an optional check if the app E2E shows it catches real errors (current evidence: detects, does not correct, noisy flags elsewhere).
REMOVE unless E2E re-run shows a benefit: structured-JSON reasoning route (B), per-number "ungrounded" flag blocks (C: precision too low), M7 number blacklist on free-form prose (rejected the user's own numbers; now replaced by grounded checks) — a decision on M7's number checks must follow the app run, not precede it.
## Freeze protocol (before any holdout run)
1. Decide route from the evidence above; implement it in the app (Claude A owns app/*), keeping deterministic tools and security checks.
2. Run the integrated app once on the 12 dev cases (real 8B and 27B) + judge — this is the last dev-set measurement.
3. Human review (≥6 packs) signed; judge rules and rubric dimension weights unchanged.
4. FREEZE: record SHA-256 of app/*.py, the guardrail prompt text, tools/judge_answers.py, tools/run_cases.py, case rubrics (dev), model names/settings (qwen3:8b, qwen3.6:27b, temperature/num_predict) and the package versions into `FROZEN_VERSION_<date>.json`; copy the tree to local_backups; from then on no edits to anything listed.
5. Holdout (HA01–HA08 sealed; claude A wrote them blind) run ONCE per model, same judge + human spot-check; results reported whether good or bad; any bug found afterwards is documented as a new version and the holdout is declared consumed (a fresh blind set would be needed).
6. Nothing in 8000/8100/riskscope_runtime is touched; raw runs never overwritten (new directories only).
