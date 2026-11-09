# Two acceptance risks (user, 2026-11-03) — claude-b notes
## 1. Whole-draft rejection vs per-item degradation (offline simulation on REAL saved model outputs; app end-to-end numbers pending in `runs/appE2E_*`)
`tools/draft_policy_analysis.py` replays saved prototype JSON through `app/ledger` + `app/binding` and asks: would a "reject the whole draft if ANY calculation fails binding/arithmetic or ANY statement carries an ungrounded number" policy discard it, and what would a per-item policy keep?
| run (turns) | whole-draft rejected | reasons (turn counts) | retainable items if per-item | judge mean: rejected vs accepted drafts |
|---|---|---|---|---|
| B-v1 qwen3:8b (18) | **13 (72%)** | binding 7 · arithmetic 5 · ungrounded text number 4 | ~90% | 61.5 vs 74.8 |
| B-v1 qwen3.6:27b (13) | **9 (69%)** | assumed input 3 · binding 2 · arithmetic 3 · ungrounded text 9 | ~70% | **94.7 vs 95.8** (self-judged) |
| B-v2 qwen3:8b (18) | 12 (67%) | binding 5 · arithmetic 5 · critical-path binding 3 · ungrounded 3 · assumed 1 | ~90% | judge pending |
Reading: a whole-draft policy would throw away two thirds of the real analyses; for 27B the discarded drafts were judged as good as the accepted ones (self-judged, so an upper bound) and 70% of their items passed the checks. Safety is not the issue (nothing unverified would be shown); **usability is** (the user would mostly see the old template). Recommendation (to be confirmed with app end-to-end data): per-item degradation — drop/flag only the failing calculation or statement, keep verified parts, and mark any conclusion that DEPENDS on a rejected calculation as "未驗證" (never presented as fact). Safety invariants unchanged: no unverified number shown as verified, no approval claims, ACL/injection handling. Caveat: simulation uses the prototype schema, and "ungrounded text number" includes numbers a model may legitimately derive; some of those flags are over-strict.
## 2. Three validity layers for critical_path (changed in `app/binding.py` + test; reasoning.py comment only)
`critical_path()` now returns `method_validity: algorithm_checked` (the algorithm is deterministic and unit-tested, given its inputs), `input_validity: caller_must_verify_each_duration_and_dependency` (the CALLER binds every duration to a source via `verify_calculation`; this function claims nothing), `conclusion_validity: not_validated`, `professional_validity: not_validated`, plus the explicit assumptions (single-point durations, complete/correct dependency list, finish-to-start only, no resource levelling). Previous value `method_validated:critical_path` is gone; `tests/test_reasoning.py` assertion updated accordingly and `tests/test_binding.py` locks the three layers.
## 3. BB07 tracked as separate issues
| id | issue | status | evidence |
|---|---|---|---|
| U1 | evaluator computed every operator eagerly → `100 * 80000` overflowed (`Result too large`) | FIXED, test `test_bb07_root_cause_…` | v1 replay: 14/35 calc died of it |
| U2 | 元 / 萬元 / 萬 normalisation of INPUTS (8萬件 → 80,000; 300萬元 → 3,000,000 元; % kept in % points) | FIXED + new tests `test_u2_*` (separate from U1) | |
| U3 | MODEL-level scale slip in prose ("break-even 10件" instead of 10萬件, B-v1 27B BB07) | **OPEN – no tool detects it**: the verified calculation was absent/rejected and the prose number was not cross-checked against a computed value at another scale | judge flagged it as critical |
## Status of the comparison
Resume pipeline running under the shared lock (`/tmp/pipeline_resume.log`): A1 judged (27B, 8B), A0-27B judged, remaining: A0 subsets, B-v2 8B judge, B-v2 27B + judge; then `pipeline_app_e2e.sh` (integrated app, real 8B and 27B, same 12 cases, + judge). Human spot-check of ≥6 cases still to do.
