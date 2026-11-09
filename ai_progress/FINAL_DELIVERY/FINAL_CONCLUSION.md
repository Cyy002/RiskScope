# RiskScope — Final conclusion (2026-11-01, claude-b; core finalized by Claude A)

## Where / how
- Project: `/Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent` — start: `deploy/riskscope.sh build && deploy/riskscope.sh up` (Windows: `.\deploy\riskscope.ps1 build|up`). Isolated demo already running: **http://127.0.0.1:8100** (qwen3:8b).
- Login: paste the `engineer` (or `manager`) token printed by `deploy/riskscope.sh creds` into the Token box. Tokens are random per volume; never commit/paste them.
- Watch the demo: GUI → 對話式 Agent, send the three Demo-A messages (TEACHER_MANUAL.md §4); or `deploy/riskscope.sh demo` (strict A/B/C); or `deploy/platform_acceptance.sh` (everything + evidence file).
- Image: `localhost/riskscope-portable:1.0`, id `679c8effdb71…a956`, linux/arm64, Podman 6.1.4. Its app/{chat,engineering,analyzer,config,api}.py SHA-256 match the finalized disk sources (checked).

## Evidence (FINAL_DELIVERY/evidence/)
| Item | Result |
|---|---|
| pytest (Claude A final core) | 198 passed |
| scripts.evaluate | 45/45 reference constraint paths |
| Codex M12.5 independent set | 38/40; the 2 failures = outdated test assumptions (reproduced by both Claudes, originals untouched) |
| Codex deploy-guard fault injection | 5/5 |
| platform_acceptance on a CLEAN project copy, fresh volume/new tokens (macOS ARM64, VM Podman) | VERDICT PASS: Darwin-arm64-20261101T111643Z.md |
| Strict demo A/B/C, qwen3.6:27b, final image | FULL PASS, 3/3 LLM turns ACCEPTED by M7 (demo_ABC_strict_qwen3.6-27b_FINALimage.txt) |
| Strict demo A/B/C, qwen3:8b | FULL PASS (earlier runs; 8B occasionally M7-rejected → reported, not hidden) |
| Real Chrome GUI run (puppeteer, headless) login → chat → 3 turns | all 3 replies shown as "本機 LLM 轉述" (accepted); 14A then 12A; no false nominal-rating change (gui_turn1-3.png, gui_run_log.json; script deploy/gui_check.js) |
| Session API sentinel | `__previous_numbers__` absent from GET /sessions/{id} (live check) |
| Restart persistence | credentials hash + all saved analyses identical after `podman restart` |
| Secret scan of deliverables | no demo token found in FINAL_DELIVERY/deploy/scripts/app |

## Professor's P0 (Podman reproduction on different platforms) — verdict
| Requirement | Status |
|---|---|
| Build + run via Podman, clean init, own tokens, real Agent analysis with a real LLM, ACL, persistence | **PASSED on macOS ARM64** (real run, final image) |
| Not dependent on this Mac's paths / production data / tokens | PASSED (clean-copy run; build context excludes secrets; scripts refuse production names) |
| Linux AMD64 | **NOT proven natively.** Only QEMU-emulated image build + 45/45 evaluation + lifecycle (Antigravity). A GitHub-Actions workflow for native linux/amd64 is prepared (`.github/workflows/podman-linux-amd64.yml`) but has NOT been run, and without a model it could only prove build/ACL/persistence, not LLM analysis |
| Windows AMD64 + Podman | **NOT TESTED.** `riskscope.ps1` / `platform_acceptance.ps1` written, statically reviewed, never executed |
**Conclusion: the P0 requirement is met and evidenced on macOS ARM64 only. "Different platforms" is NOT yet evidenced for Windows or native Linux; do not claim it until someone runs `deploy/platform_acceptance.(sh|ps1)` there and attaches the generated evidence file.**

## Known limits
Small-model prose is non-deterministic: M7 may reject a reply (then the deterministic text is shown; scripts report it, FULL PASS requires acceptance). Ollama endpoint allowlist: localhost/127.0.0.1/::1/host.containers.internal/host.docker.internal only (LAN IPs, compose service names rejected by design). Windows/Linux need `OLLAMA_HOST=0.0.0.0` for host Ollama reachability. 27B needs ~20 GB RAM.

## Needs the user
1. Run the acceptance script on a real Windows machine and a native Linux AMD64 machine (or approve running the prepared GitHub workflow in a private repo).
2. Authorize production upgrade of 0.4 (:8000) — backup/switch/rollback commands in `ai_progress/60_NEXT_HANDOFF.md` (M12.3/M12.4); nothing was changed in production.
3. Rotate the OpenAgents workspace access token that appeared in plaintext in past logs (separate from RiskScope's tokens; RiskScope production tokens were not touched).
