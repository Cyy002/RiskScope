# Binding verification (P0 round, claude-b, 2026-11-01) — arithmetic correct ≠ analysis correct
## Four verification levels (never conflated; `app/binding.py`)
| Level | Question | Who decides | Granted automatically? |
|---|---|---|---|
| L1 presence | does the number occur in a source (question / ACL-visible doc, with version)? | ledger lookup by id or by value | yes |
| L2 binding | is it bound to the right entity/attribute/unit? checks: id exists; declared unit's dimension matches the source's; declared *meaning* overlaps the source label/context; one source quantity is NOT reused by several variables unless all declare the same non-empty meaning; literal value matching several sources = ambiguous; header-unit numbers flagged `unit_inferred` | rule checks | yes — **failure ⇒ calculation REJECTED, value withheld** |
| L3 arithmetic | recompute the formula with a safe evaluator (model-stated results ignored) | tool | yes |
| L4 professional validity | is the method/conclusion right for the domain? | registered deterministic method only (`critical_path`) or a human expert | **never by default**: every result says `professional_validity: not_validated`; wording is "輸入對應與算術已核對（專業結論尚未驗證）", never "已證實正確" |
Status values: REJECTED_BINDING · ARITHMETIC_FAILED · UNVERIFIED_ASSUMED_INPUT (input not in any source) · INPUTS_BOUND_AND_ARITHMETIC_CHECKED · METHOD_CRITICAL_PATH.
## Root cause of BB07 "Result too large"
`safe_eval` (prototype v1) built a dict of ALL operator results eagerly, so `100 * 80000` also evaluated `100 ** 80000` → OverflowError. Not a unit problem. Fixed (only the selected operator runs; `**` has range caps). Regression test `test_bb07_root_cause_large_right_operand_no_longer_overflows`.
## Other root causes fixed
- Unit normalisation: 萬/萬元/億 expand to the elementary number (8萬件 → 80,000); 週/天/月 convert to the declared unit; % stays in % (declared). Test `test_man_unit_is_expanded_not_used_raw`.
- Why BB01's model bound everything to "9週": the case document writes durations without units ("A 設計 2；B 後端 4（A）" under header "（工期，週；前置）"), so the ledger had only 2 quantities. New `Ledger.bare` (refs b1…, kept out of `.items`) extracts header-unit table numbers with `unit_inferred`.
- Schedules: v2 prompt requires `kind: critical_path` with per-task duration refs + predecessors; `critical_path()` returns total, critical path, floats (BB01: 10 weeks, A→B→D→E, C float 1, F float 7; naive sum would be 14).
## Before measurement (offline replay of v1 8B prototype outputs, 17 cases, `tools/binding_metrics.py`)
35 calculations: **14 (40%) died from the eager-pow arithmetic bug**; 21 were stamped "工具驗算". Re-verified with the new rules: 13 REJECTED_BINDING (**37% wrong/ambiguous binding**), 7 UNVERIFIED_ASSUMED_INPUT (20%), 13 passed L1–L3. **Of the 21 v1-stamped results, 38% would have been rejected for binding ("false verified" rate of v1 stamps).** File: `runs/proto_qwen3-8b/_binding_metrics_v1_replay.json` (v1 outputs untouched).
## Tests (independent positive + negative; `tests/test_binding.py`, ledger tests)
BB01 replay (4 tasks bound to one quantity) rejected though arithmetic passes · distinct correct bindings pass L1–L3 and keep L4 "not_validated" · wrong meaning rejected · unit-dimension conflict rejected · 萬 expansion · assumed literal flagged · critical path ≠ sum (+cycle error) · bare/header-unit extraction · dates not numbers.
## v2 experiment (queued behind the running jobs through the same lock: `tools/pipeline_v2.sh`)
Same cases/caps/judge; new output dirs `runs/protoV2_qwen3-8b`, `runs/protoV2_qwen3.6-27b` (v1 dirs kept for Before/After). Metrics to report: rejected-binding rate, assumed-input rate, arithmetic-failure rate, accepted calcs matching reference answers, accepted calcs NOT matching (false-verified candidates, human-reviewed), unsupported-number tags, judge score vs A0/A1/B-v1.
## Coordination note (Claude A)
A's `app/reasoning.py` independently added ref ids (`q#`) and "derived_calculations"; these overlap `app/binding.py`. Proposal: reasoning.py should import `verify_calculation` / `critical_path` (meaning/unit/duplicate-binding/header-unit/萬 handling are already tested there) instead of re-implementing; refs are compatible (`q#`, `b#`, positional `Q#`). Ledger.py is shared: my additions are `bare`, `all_items`, `extract_bare_numbers`, `by_ref` also searches bare. Some of A's reasoning tests currently fail mid-edit (not caused by these changes: verified by disabling the bare extraction).
