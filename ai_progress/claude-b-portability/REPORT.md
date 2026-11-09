# claude-b portability report (2026-11-01)

## Done (verified, host: macOS ARM64, Podman 6.1.4 applehv VM, Linux container aarch64)
- Production: podman machine was stopped (Mac reboot); started machine + `podman start riskscope` (0.4 unchanged, /health ok). No image/volume change.
- Built `localhost/riskscope-portable:1.0` from the unmodified Containerfile; fresh volume `riskscope_portable_data`, port 8100, new random tokens (no prod token/volume used).
- New files: deploy/riskscope.sh, deploy/riskscope.ps1, deploy/README_PODMAN.md, scripts/portable_smoke.py (+ this report).
- Smoke (inside container, stdlib only): health, no-token rejected, engineer login, outsider ACL denied, chat 200, REAL qwen3:8b reply (reply_source=llm_phrased, diag success ~35s).
- restart-test: PERSISTENCE OK (credentials + db survive `podman restart`).

## Open (core, owner = claude)
Smoke check "total current 14A" FAILS on a fresh volume: turn-1 text "馬達電流11A ... 輔助負載3A" yields total_current_a=11 (motor stays doc 8A, `unclaimed_change_intents=['8A']`). Same as Codex M12.5 finding (first-turn 11A ignored). Also earlier reply said "電源額定 8 A" (nominal/usable conflation).

## NOT verified
Windows (.ps1 untested, no host), native Linux AMD64 (never run; macOS VM is Linux/aarch64 only, not a substitute), amd64 image build, Ollama-from-container on Win/Linux (needs OLLAMA_HOST=0.0.0.0 — documented, untested), Qwen3.6 27B via this kit (only qwen3:8b run).
Verdict: P0 cross-platform NOT yet fully satisfied; macOS-ARM64 path proven.

## Update 2 (2026-11-01)
Fixed Codex P1/P2 + Antigravity findings: .env.example (container URL default), .containerignore (.env, backups/ai_progress, db, creds), PYTHONPATH in Containerfile, ps1 add-host + no `exit` in loop, host-network health port, platform pinning in build (shared base tag had been overwritten by an amd64 pull → my image came out amd64; now arm64 verified), prod-name/port guard (rejects `riskscope`, `riskscope_runtime`, 8000), compose.yml/README no longer point at production names. Codex contract tests vs fixed source: 7 passed, 1 skipped. Rebuilt arm64 image, restart-test: persistence OK, real LLM OK. Still failing only the core 14A check (task #3, owner claude A).
