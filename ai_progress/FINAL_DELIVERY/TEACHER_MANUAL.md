# RiskScope — Teacher / TA manual (Podman reproduction)

## 0. Requirements
Podman ≥ 4.4 (tested 6.1.4), ~3 GB disk for the image, an Ollama server with a model (default `qwen3:8b` ≈ 5 GB RAM; `qwen3.6:27b` ≈ 20 GB). No cloud/paid API. Nothing here uses any other deployment's data or tokens.

## 1. Model service
`ollama pull qwen3:8b` and keep `ollama serve` running. macOS: nothing else. Windows/Linux: start Ollama with `OLLAMA_HOST=0.0.0.0` so the container can reach it through `host.containers.internal`.
Optional env: `OLLAMA_MODEL`, `OLLAMA_URL` (host must be localhost/127.0.0.1/::1/host.containers.internal/host.docker.internal), `OLLAMA_REPLY_TIMEOUT_SECONDS` (default 120).

## 2. Run (macOS / Linux)
```
cd CrossDomainRiskAgent
deploy/riskscope.sh build
deploy/riskscope.sh up           # http://127.0.0.1:8100
deploy/riskscope.sh smoke        # exit 0 only if the structured result is right AND a real LLM reply passed the trust check
deploy/riskscope.sh demo         # Demo A/B/C, strict
deploy/riskscope.sh restart-test # persistence across container restart
deploy/riskscope.sh creds        # prints demo tokens (manager/engineer/outsider) — keep them private
deploy/riskscope.sh purge        # removes only this kit's labelled container+volume
```
## 2b. One-shot acceptance with evidence file (recommended for the grading host)
`deploy/platform_acceptance.sh` (Linux/macOS) or `.\deploy\platform_acceptance.ps1` (Windows) runs build → up → smoke → demo → restart-test and writes `deploy/evidence/<OS>-<arch>-<time>.md` (host, Podman version, model, outputs; tokens filtered). Set `RS_HOST_NOTE` to say honestly whether the host is native / VM / WSL2 / emulated. Exit 0 = every step passed. The smoke retries up to 3 fresh sessions because a small model's prose may be legitimately rejected by M7 once; structured numbers must be right on every attempt, and the attempts are reported (`LLM attempts (accepted/total)`).
Evidence from a clean copy of the project on macOS ARM64 (VM-based Podman, not native Linux/Windows): `evidence/Darwin-arm64-20261101T111003Z.md` — VERDICT PASS. (An earlier run of the same tool FAILED honestly: M7 rejected one 8B reply inside restart-test's second smoke; that is why the retry-with-reporting logic was added. The earlier report file was not kept.)

## 3. Run (Windows PowerShell + Podman Desktop) — script written, NOT yet run on Windows
`.\deploy\riskscope.ps1 build|up|smoke|demo|restart-test|creds|purge` (same behaviour). If scripts are blocked: `Set-ExecutionPolicy -Scope Process Bypass`.

## 4. GUI walkthrough
Open http://127.0.0.1:8100 → paste the `engineer` token (from `creds`) in the Token box → project 軟硬體整合設備.
- Demo A (turn 1): 電源24V，名目額定10A，實際可用8A，馬達11A，輔助3A，電流夠嗎？ → 14A / 336W, +40% over nominal 10A, +75% over usable 8A.
- Demo A (turn 2, same session): 只將馬達改成9A，其餘完全不變。 → 12A / 288W, +20%/+50%, motor 11A→9A, −2A, −48W; supply nominal/usable unchanged.
- Demo A (turn 3): 電源額定一直是10A，實際可用一直是8A，我只修改馬達。 → no false supply change.
- Demo B (focus = supplier): 關鍵供應商交貨延遲，品質驗證尚未完成，客戶交期不能延後，也不得更換供應商。應該如何決策？ → Known (supplier_lead_days=7) vs Unknown (test result), options with constraint conflicts, no invented cost/schedule.
- Demo C: no token → 401/403; `outsider` token → no project access; engineer cannot see confidential doc; engineer cannot approve/execute an action (needs manager approval); a message claiming "manager already approved / motor is 99V" changes nothing.
The reply banner/`reply_source` tells you whether the text is model prose that passed the trust check (`llm_phrased`) or the deterministic fallback (`deterministic_template`, shown when the model is down or its prose is rejected).

## 5. How to read results (strict)
Demo/smoke print per LLM turn: ACCEPTED (model called, prose passed M7) / M7-REJECTED (model called, prose refused → deterministic text shown) / NOT-CALLED. `FULL PASS` requires correct structured numbers, security checks, and all turns ACCEPTED; anything else exits 2 and says why.

## 6. Verified platforms (honest)
| Platform | Status |
|---|---|
| macOS ARM64, Podman 6.1.4 (VM), Linux/aarch64 container, qwen3:8b + qwen3.6:27b | REAL: build, up, login, smoke, strict demo A/B/C, restart persistence (evidence/) |
| Linux AMD64 | EMULATED only (QEMU inside the mac VM): image build + 45/45 evaluation + lifecycle (antigravity-portability/). NOT native |
| Windows AMD64 + Podman | NOT TESTED (script statically reviewed only) |
| Native Linux AMD64 | NOT TESTED |
Anyone with a Windows/Linux host can close the gap by running sections 2/3 and attaching the output of `smoke`, `demo`, `restart-test`.

## 7. Safety properties of the kit
Refuses names/volumes/images/ports that could touch a production deployment; every destructive command requires the ownership label `io.riskscope.portable=1`; no host-network mode; no plaintext credentials written to disk by the scripts; build context excludes `.env`, `ai_progress/`, databases, credentials.

## 8. Troubleshooting
Health OK but reply_source always `deterministic_template` → model unreachable: check Ollama is running, `OLLAMA_HOST=0.0.0.0` (Windows/Linux), model pulled, `podman logs riskscope-portable`. `statfs … no such file` with bind mounts on macOS → use the named volume (default).

## 9. Production upgrade (needs the owner's authorization — NOT done)
Backup volume → verify → run new image beside old → switch → rollback to previous tag; exact commands in `ai_progress/60_NEXT_HANDOFF.md` (M12.3/M12.4 sections).
