# RiskScope on Podman — portable run (teacher/TA guide)

Needs: Podman >= 4.4 (tested 6.1.4), an Ollama server with a model pulled (default `qwen3:8b`, ~5 GB; `qwen3.6:27b` needs ~20 GB RAM). No production data/tokens are used: a fresh named volume is initialised on first start and generates NEW random demo tokens.

**Tested status (Claude A, 2026-11-09, on an independent test VM `riskscope-codex-apple-20261107`,
`applehv` backend — the pre-existing `libkrun` backend aborts on this machine, so `applehv` is
used instead; this does not touch the separate production machine/container):**
`build` → succeeds. `up` → container starts and `/health` returns `{"status":"ok", ...}`. `smoke`
→ result pending a clean re-run (one run hit an LLM-extraction timeout while a large, unrelated
model-evaluation batch was concurrently saturating the same shared Ollama server — resource
contention, not a confirmed app defect; see `ai_progress/RISK_INTELLIGENCE_EVALUATION/`). Do not
treat `smoke`/`restart-test` as passing until this file is updated with a clean run's result.

## 0. Ollama must be reachable from the container
The app only accepts `localhost`, `127.0.0.1`, `::1`, `host.containers.internal` as model host (by design, no cloud).
- macOS: nothing extra (`ollama serve`; `ollama pull qwen3:8b`).
- Windows (Podman Desktop/WSL2) & Linux: set `OLLAMA_HOST=0.0.0.0` for Ollama so the container can reach it via `host.containers.internal`; on Linux you may instead use `RS_HOST_NETWORK=1 OLLAMA_URL=http://127.0.0.1:11434`.
- Variables: `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_REPLY_TIMEOUT_SECONDS` (default 120).

## 1. Linux / macOS
```
deploy/riskscope.sh build
deploy/riskscope.sh up          # http://127.0.0.1:8100, volume riskscope_portable_data
deploy/riskscope.sh smoke       # real Agent test, exits non-zero if the LLM was not really used
deploy/riskscope.sh restart-test  # restart container, verify data/credentials persist, re-run smoke
deploy/riskscope.sh creds       # prints login tokens (manager / engineer / outsider)
deploy/riskscope.sh purge       # removes ONLY the portable container+volume
```
## 2. Windows PowerShell
`.\deploy\riskscope.ps1 build|up|smoke|restart-test|creds|purge` (same behaviour; set `$env:OLLAMA_MODEL` etc. first).

## 3. GUI
Open http://127.0.0.1:8100, paste the `engineer` token from `creds`, ask e.g. "電源24V、名目額定10A、實際可用8A，馬達11A、輔助3A，電流夠嗎？".

## Notes
Own names/port (`riskscope-portable`, 8100) never collide with other deployments. Named volumes inherit uid 10001 ownership; if you use a bind mount add `:U` (Linux). Image is plain `python:3.12-slim` + pure-Python deps, so it builds natively on ARM64 and AMD64.
