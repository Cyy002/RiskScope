**START HERE → FINAL_CONCLUSION.md (verdict + 8-line summary), TEACHER_MANUAL.md (steps).**

# RiskScope — Final Delivery (status as of 2026-11-01, maintained by claude-b)

See also TEACHER_MANUAL.md (full walkthrough) and ../CLAUDE_CORE_HANDOFF.md. Demo evidence: evidence/demo_ABC_strict_* (strict criteria: FULL PASS needs every LLM reply ACCEPTED by M7).

## Start in 4 commands (macOS / Linux; Windows: `.\deploy\riskscope.ps1 <action>`)
```
deploy/riskscope.sh build      # image localhost/riskscope-portable:1.0 (arch-pinned)
deploy/riskscope.sh up         # http://127.0.0.1:8100 (own volume, new random demo tokens)
deploy/riskscope.sh smoke      # real Agent test; PASS only if a real LLM reply happened
deploy/riskscope.sh demo       # Demo A (engineering, 2 turns) / B (supplier Known-Unknown) / C (security), real LLM
deploy/riskscope.sh restart-test   # restart + verify credentials hash & saved analyses identical
```
Tokens: `deploy/riskscope.sh creds` (manager / engineer / outsider) — never paste them into chats/reports. Ollama: see deploy/README_PODMAN.md.

## Safety guards (verified)
Container must match `riskscope-portable*` and volume `riskscope_portable*`, image `localhost/riskscope-portable:*`, port 1024-65535 ≠ 8000, and existing resources must carry label `io.riskscope.portable=1` — otherwise REFUSED (rc 3). Host-network mode removed. restart-test no longer writes credentials to disk (hash compare in-container). Smoke exit codes: 0 real-LLM PASS, 2 deterministic-only, 1 FAIL.
Evidence: Codex fault-injection tests 5/5 pass against these scripts (`ai_progress/codex-p0-portability-review/followup-20261101/`, run with P0_REVIEW_DEPLOY_SOURCE); real engine: guard refusal of unlabeled resource, labeled purge, persistence OK (4 analyses identical), real qwen3:8b reply.

## Platform matrix (honest)
| Platform | Status | Evidence |
|---|---|---|
| macOS ARM64 + Podman 6.1.4 (applehv VM, Linux/aarch64 container) | REAL: build, up, login, ACL, real qwen3:8b, restart persistence | claude-b-portability/REPORT.md |
| Linux AMD64 | EMULATED only (QEMU in mac VM): build + 45/45 eval + lifecycle; NOT native | antigravity-portability/ |
| Windows AMD64 + Podman | NOT TESTED (script statically reviewed; $LASTEXITCODE checks added) | — |
| Qwen3.6 27B via this kit | NOT TESTED in kit (earlier GUI tests by Claude A on separate env) | — |

## M12.5.1 core fix (done by claude-b on top of Claude A's schema split) — evidence-based
- Nominal rating (`supply_continuous_current`, from document) and usable capacity (`supply_actual_current`, user scenario) are separate fields end to end: extraction → session → engineering (`nameplate_limit_*`/`actual_limit_*`) → facts (analyzer.py) → evidence → reply → M7 percentages.
- Added this round: bare multi-field scenario ("電源24V、實際可用8A、馬達11A、輔助3A") applies load currents as a labelled what-if (a lone "馬達是11A" still cannot override the document); "取代原本11A"/"舊馬達8A" old-value wording is not a request; models that mis-file "實際可用" under the nameplate key are re-keyed from the wording; previous-plan tracking narrates 11A→9A (not document 8A) with −2A/−48W; facts claim names nominal vs usable separately; labels instead of raw keys.
- Also: M7 percentage anchor accepts natural wording ("超出名目額定約 40%") but still rejects borrowed/fabricated percentages; no-op "replace with same value" is not a change. Results: `pytest tests` 194 passed (evidence/pytest_full.txt); scripts.evaluate 45/45; Codex 38 + extra: 40 cases, 38 pass, 2 fail (below); portable smoke PASS with real LLM; demo A/B/C PASS in container (evidence/demo_ABC_real_llm_qwen3-8b_container.txt).
- Tests I changed (stale old-schema fixtures, each replaced by an equivalent/stronger invariant, never deleted): test_user_supplied_values (closed schema now includes supply_actual_current), test_ollama_integration_codex (ignore `__previous_numbers__` sentinel), test_m8 (mis-filed model key is re-keyed; asserts nominal 10 / usable 8), test_m12 (percentages from nameplate/actual), test_m114 (nameplate restatement harmless), test_m125 (narrates vs previous plan 11A).
- Codex cases still failing — classified, not edited: `test_real_supply_change_still_applies` asserts the raw string "supply_continuous_current 由" in user-visible text (we now show the Chinese label 電源名目額定電流; Codex itself flagged raw keys as confusing) → test-assumption; `test_real_supply_replacement_keeps_both_new_ratings` needs the nameplate "20A" taken from text although the mocked model never extracted it → would require bypassing extraction (conflicts with M11.4 "unclaimed change" design, which instead warns); real behaviour: limit stays 10 and the 20A change is flagged unapplied.

## FINAL image evidence (core finalized by Claude A, incl. api.py sentinel fix) — 2026-11-01
- pytest 198 passed (Claude A). Image built from a CLEAN copy of the project (no .venv/ai_progress/runtime): `deploy/platform_acceptance.sh` VERDICT PASS (build, up, smoke, demo, restart-test) → evidence/Darwin-arm64-20261101T111643Z.md (macOS ARM64, VM-based Podman; not native Linux/Windows).
- Strict demo A/B/C on **qwen3.6:27b** with the final image: FULL PASS, all 3 LLM turns ACCEPTED by M7 → evidence/demo_ABC_strict_qwen3.6-27b_FINALimage.txt (27B container purged afterwards via the guarded purge).
- Live API check: GET /sessions/{id} no longer contains `__previous_numbers__`.
- Live demo for the user: http://127.0.0.1:8100 (qwen3:8b; token via `deploy/riskscope.sh creds`, do not paste into chats). Production :8000 untouched.

## Open blockers / honest limits
1. Core changes are NOT yet independently re-reviewed by Codex (quota) nor deployed; production 0.4 untouched (still pre-M12.5). Deploy needs backup+rollback (60_NEXT_HANDOFF.md) + user authorization.
2. Demo A/B/C pass in-container with qwen3:8b AND qwen3.6:27b (evidence/*). 8B sometimes fails M7 (unverifiable percentage) → fail-closed deterministic reply; demo accepts that as correct behaviour but requires ≥1 real LLM reply.
3. app/config.py endpoint allowlist rejects host.docker.internal / LAN IPs / compose service names (security design).
4. Windows & native Linux AMD64 never run (script static review; amd64 only QEMU-emulated by Antigravity).
5. Upgrade of production: see 60_NEXT_HANDOFF.md M12.4 section (backup → verify → switch → rollback to 0.4/0.2 image tags).

## Secrets
OpenAgents workspace access token appeared in plaintext in past work logs → rotate it (workspace credential, NOT RiskScope's tokens). RiskScope production tokens untouched; demo tokens are random per volume. Build context excludes .env, ai_progress/, DB, credentials; evidence files contain no tokens (checked).
