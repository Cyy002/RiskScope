# Core handoff: claude-b → Claude A (2026-11-01). claude-b stops editing app/*.py after this.
No destructive git/cleanup used (project has no .git). All edits additive; no files deleted except two superseded evidence files of mine.

## 1. Core files touched by claude-b (on top of Claude A's supply_actual_current split)
| File | Change | Purpose |
|---|---|---|
| app/chat.py | `_is_scenario_declaration()` + `scenario_spec` branch in `_explicit_change_requests` | bare multi-field scenario (>=3 distinct component/quantity inputs) makes verb-less motor/aux CURRENT a labelled what-if (fixes "馬達11A" ignored → 11A total). Lone "馬達是11A" still can't override (M8 rule, test kept). Voltages/nameplate still need a verb (M7 30V test) |
| app/chat.py | `_OLD_VALUE_ADJ_RE`, `_OLD_VALUE_RE` | "取代原本11A"/"舊馬達8A" = old value, not a request |
| app/chat.py | re-keying in `_extract_user_supplied` | model files "實際可用" number under nameplate key → moved to supply_actual_current when wording says so (value must still match request) |
| app/chat.py | `_unclaimed_change_intents`: noop-vs-document + "same quantity already in effect under another key" skips (excludes own key) | no false "unapplied" warning on restatement / mis-filed key |
| app/chat.py | `_fresh_change_text`, `prior_plan` arg of `_deterministic_reply` | narrate against PREVIOUS PLAN (11A→9A), doc value shown separately as 基準 |
| app/chat.py | labels instead of raw fact keys in "已記錄" line | UX; Codex flagged raw keys |
| app/chat.py | `_ANCHORED_PERCENT_RE` bridge whitelist | real 27B reply "超出名目額定約 40%" was falsely rejected by M7; fabricated/borrowed % still rejected |
| app/chat.py | `entry['mode']` only set when truthy | contract: omit mode when none |
| app/analyzer.py | facts claim text | names nominal rating and usable capacity separately (was "電源額定 8 A") |
| app/engineering.py | replace-with-identical-value is not an override | no "輔助 3A→3A" |

## 2. Latest results (run by claude-b, current disk, before your own later edits)
pytest tests: 194 passed (evidence/pytest_full.txt; was 181 before I added the M7-percentage and plan-tracking tests; NOTE count rose 186→194 between runs — someone (you?) added tests meanwhile). scripts.evaluate 45/45. Codex M125 suite (`run_isolated.py --source current`): 40 cases, 38 pass, 2 fail.
Container (isolated, :8100 / :8101): smoke PASS; strict demo A/B/C FULL PASS on qwen3:8b and qwen3.6:27b (evidence/demo_ABC_strict_*.txt).

## 3. Existing-test expectation changes (please re-judge; none deleted)
1. test_user_supplied_values closed-schema set += supply_actual_current (intended schema growth).
2. test_ollama_integration_codex: compare stored session JSON ignoring `__previous_numbers__` sentinel. (Sentinel lives only in sessions.user_supplied_json; not exposed by any API — grep'd app/api.py. Your call whether to move it to its own column.)
3. test_m8 replace-motor-and-supply: model mock still files 8A under nameplate key; now expects re-key to supply_actual_current (mode replace) AND asserts nameplate 10 / actual 8 (stronger).
4. test_m12 baseline-percentage unit test: fixture now carries nameplate_limit/actual_limit fields instead of check['baseline'].
5. test_m114 nameplate-cannot-mask: dropped `'supply_continuous_current' not in accepted`; replaced by: no mode on it, no actual_current accepted, no actual_limit in numbers.
6. test_m125 standing-condition: asserted old buggy "馬達連續電流 由 8A"; now asserts "由上一輪方案的 11A 改為 9A" and not "由 8A".
Possible weak spots for you to review: #5 (looser than before); my test_m1251 parametrized generalisation passes nameplate 10 from the document for all rows (only actual/motor/aux vary) — nameplate generalisation is NOT covered; `scenario_spec` heuristic (>=3 fields) is a judgment call.
Self-found sloppiness already fixed: demo C5 had `or True` (removed); demo A/B previously counted M7-rejected LLM prose as success (now strict, see §5).

## 4. Still failing / open
- Codex `test_real_supply_change_still_applies` (raw key string "supply_continuous_current 由" expected) and `test_real_supply_replacement_keeps_both_new_ratings` (needs nameplate 20A without model extraction): you reproduced both and judged test-assumption. Not edited.
- Not covered: nameplate-replacement + new actual together when model omits one (warns unapplied by design).
- Codex has NOT reviewed the final diff (quota).

## 5. Podman / demo state
Production riskscope 0.4 :8000 untouched. Kit: deploy/riskscope.sh|ps1 (guards: name/volume/image/port allowlist + ownership label, no host-network, no plaintext temp creds, smoke exit 0/1/2). Image localhost/riskscope-portable:1.0 rebuilt from current disk; container riskscope-portable on :8100 (qwen3:8b) left running for demo. demo_scenarios.py now ends: FULL PASS only if structured+security ok AND every LLM turn ACCEPTED by M7; M7-REJECTED or model-not-called → exit 2 (not full pass). Windows/native Linux untested; amd64 only QEMU (Antigravity).

## 6. Core work left for you
Review §1/§3; decide sentinel storage; nameplate-generalisation test; optional: Codex re-review; real-27B GUI pass (kit already shows demo-level 27B pass); then tell me to rebuild image.
