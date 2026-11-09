# RiskScope on Podman — portable run (teacher/TA guide)

Needs: Podman >= 4.4 (tested 6.1.4), an Ollama server with a model pulled (default `qwen3:8b`, ~5 GB; `qwen3.6:27b` needs ~20 GB RAM). No production data/tokens are used: a fresh named volume is initialised on first start and generates NEW random demo tokens.

**Tested status (Claude A, 2026-11-09, on an independent test VM `riskscope-codex-apple-20261107`,
`applehv` backend — the pre-existing `libkrun` backend aborts on this machine, so `applehv` is
used instead; this does not touch the separate production machine/container):**
`build` → succeeds. `up` → container starts and `/health` returns `{"status":"ok", ...}`. `smoke`
→ **PASS (deterministic + real LLM)**, clean run with the Ollama queue idle (an earlier run hit an
LLM-extraction timeout while an unrelated model-evaluation batch was concurrently saturating the
same shared Ollama server — resource contention, not an app defect; confirmed by re-running clean).
`restart-test` → **PASS**, `PERSISTENCE OK: credentials hash and 3 saved analysis record(s)
identical after restart`, smoke re-run after restart also PASS.

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
deploy/riskscope.sh demo        # full scenario walkthrough (conversation/ACL/tool checks/options/approval/error-handling)
deploy/riskscope.sh restart-test  # restart container, verify data/credentials persist, re-run smoke
deploy/riskscope.sh creds       # prints login tokens (manager / engineer / outsider)
deploy/riskscope.sh down        # stops and removes ONLY the portable container (keeps the volume)
deploy/riskscope.sh purge       # removes the portable container AND volume (full reset)
```
Or, for a single command after `build`+`up` that runs the whole demo and auto-builds/starts if needed:
`deploy/demo_run.sh` (see `ai_progress/ASSIGNMENT2/DEMO_EVIDENCE.md` for a real recorded run and the
packaging bug this script had — fixed in commit `b5f30a8` — before relying on it).

## 2. Windows PowerShell
`.\deploy\riskscope.ps1 build|up|smoke|restart-test|creds|purge` (same behaviour; set `$env:OLLAMA_MODEL` etc. first).

## 3. GUI
Open http://127.0.0.1:8100, paste the `engineer` token from `creds`, ask e.g. "電源24V、名目額定10A、實際可用8A，馬達11A、輔助3A，電流夠嗎？".

## 4. 常見問題 (Troubleshooting)
- **`podman machine start` 卡住或 abort（例如 `libkrun` 相關錯誤）**：改用 `applehv`/`vfkit` 後端的
  machine（`podman machine init --vm-type applehv ...`），這台機器上 `libkrun` 後端本身會 abort，
  與本專案程式碼無關。確認 `podman machine list` 裡要用的 machine 不是你的正式/其他專案 machine。
- **`smoke` 的 LLM 檢查逾時或被判 `NOT-CALLED/FAILED`**：最常見原因是 Ollama 同時被另一個程序占用
  （例如有人正在跑模型評分批次）。確認 `ollama ps`／沒有其他重負載在跑，再重新執行一次 `smoke`。
- **`up` 卡在等 `/health`，最後印出 `health check failed`**：執行 `podman logs riskscope-portable`
  看容器內實際錯誤；多半是 `OLLAMA_URL` 指到容器打不到的位址（檢查第 0 節的平台對應設定）。
- **`REFUSED: ...` 訊息**：`riskscope.sh` 刻意拒絕任何可能撞到正式部署名稱/埠號/映像標籤的操作，
  這是設計行為，不是 bug——不要繞過這些檢查，改用預設的 `riskscope-portable`/8100 設定即可。
- **換一台電腦重新執行**：`purge` 之後再 `build`→`up`，會產生全新的隨機 demo token（不會沿用舊的）。

## Notes
Own names/port (`riskscope-portable`, 8100) never collide with other deployments. Named volumes inherit uid 10001 ownership; if you use a bind mount add `:U` (Linux). Image is plain `python:3.12-slim` + pure-Python deps, so it builds natively on ARM64 and AMD64.
