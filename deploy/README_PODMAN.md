# RiskScope on Podman — portable run (teacher/TA guide)

Needs: Podman >= 4.4 (tested 6.1.4), an Ollama server with a model pulled (default `qwen3:8b`, ~5 GB; `qwen3.6:27b` needs ~20 GB RAM). No production data/tokens are used: a fresh named volume is initialised on first start and generates NEW random demo tokens.

**Tested status (macOS, Apple Silicon, 2026-11-09/10):** `build` (including a `--no-cache` cold
build from a clean checkout) → succeeds. `up` → container starts and `/health` returns
`{"status":"ok", ...}`. `smoke` → **PASS** (both the deterministic engineering calculation and a
real local-LLM reply). `demo` → **FULL PASS** (all 6 course-required capabilities: conversation,
ACL/authorization, tool checks, option comparison, simulated approval, error handling), verified
both via the CLI script and by hand in the real browser UI (login → chat → engineering check →
risk/option comparison → manager approval → two rejection cases). `restart-test` → **PASS**,
data and credentials survive a container restart.

**Tested status (Windows 11 real PC, 2026-11-15):** Podman 5.8.10 on WSL2 + Ollama `qwen3:8b` (RTX 5060):
`Start_RiskScope.bat` end-to-end PASS — container reaches host Ollama, first A1 after a cold start = 14A/336W,
walkthrough steps 1-10 (approval flow, engineer/outsider permissions) PASS.

**Tested status (Linux, GitHub Actions ubuntu-latest linux/amd64, Podman 5.7.0, 2026-11-15):** `build`, `up`,
`/health`, token rejection, engineer login, outsider ACL and the deterministic calculation PASS
(https://github.com/Cyy002/RiskScope/actions/runs/43712945894). No Ollama on the runner, so the real-LLM reply is NOT verified on Linux.

## 0. Ollama must be reachable from the container
The app only accepts `localhost`, `127.0.0.1`, `::1`, `host.containers.internal` as model host (by design, no cloud).
- macOS: nothing extra (`ollama serve`; `ollama pull qwen3:8b`).
- Windows (Podman Desktop/WSL2) & Linux: set `OLLAMA_HOST=0.0.0.0` for Ollama so the container can reach it via `host.containers.internal`. On Windows, `host-gateway` resolves to the podman machine itself (169.254.1.2 under pasta), so `riskscope.ps1 up` maps `host.containers.internal` to the machine's default gateway (= the Windows host) instead, and the launcher recreates the container if that address changed after a reboot; on Linux you may instead use `RS_HOST_NETWORK=1 OLLAMA_URL=http://127.0.0.1:11434`.
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
`.\deploy\riskscope.ps1 build|up|smoke|demo|restart-test|creds|down|purge` (same behaviour; set `$env:OLLAMA_MODEL` etc. first).

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
- **Podman Desktop GUI 顯示「No Container Engine」或「Podman needs to be set up」**：若 `podman`
  是透過非標準路徑安裝（例如手動展開官方 `.pkg` 到使用者目錄，而非走 Podman Desktop 自己的安裝
  流程），Podman Desktop 可能偵測不到該執行檔。**已實測排查（Claude A，2026-11-10，直接解壓縮
  Podman Desktop 的 `app.asar` 讀取官方原始碼確認，不是猜測）**：
  - 單純把路徑加進 GUI 工作階段的 `PATH`（`launchctl setenv PATH "..."`）不夠：其「Podman」內建擴充
    功能的偵測邏輯（`podman-cli.ts`）用 `which -a podman` 找執行檔，但只會額外查
    `/opt/podman/bin:/usr/local/bin:/opt/homebrew/bin:/opt/local/bin` 這幾個固定路徑，不含使用者
    自訂安裝路徑。
  - 畫面上的「**Set up**」按鈕（`mac-os-installer.ts`）**確認會執行 `open <官方.pkg> -W`**，也就是
    跳出 macOS 系統安裝精靈（需要輸入管理員密碼）把 Podman 安裝到 `/opt/podman/bin/`——這會建立
    *另一套*獨立的 Podman，不是修好現有這一套，因此沒有點擊測試，以免違反「不重新安裝、不建立
    另一套 Podman」的限制。
  - **找到真正的官方解法**：這個擴充功能其實有一個專門給這種情況用的設定，
    `podman.binary.path`（UI 上顯示名稱是「**Path to Podman Binary**」，在 Settings → Preferences
    的「Podman」分類底下）。原始碼（`getPodmanCli()`）會**優先**使用這個自訂路徑，PATH 搜尋只是
    找不到時的備援。只要把它設成實際安裝路徑（這台機器是
    `/Users/haochenglin/.local/podman/bin/podman`），理論上不需要重新安裝、不需要碰任何 machine，
    Podman Desktop 就會直接用現有這一套 CLI，連帶原本就在 `~/.config/containers/podman-connections.json`
    裡的 3 台 machine（含正式機）也應該會被正常偵測到（純讀取，不會自動建立或修改）。
  - **沒有能完成最後一步**：Podman Desktop 的介面是用沒有標準無障礙標籤的元件畫的（整個視窗用
    System Events 檢視只看到 `button 1`/`group 1` 這種通用、無名稱的元素，連側邊欄「Settings」
    文字都抓不到語意名稱），點擊座標的方式在這台機器上也不支援（`click at {x,y}` 回傳系統錯誤
    -25200）。在沒有辦法先確認「即將點到的到底是哪個按鈕」的情況下，盲目用座標或通用索引點擊
    有風險（旁邊可能就是會動到 machine 的按鈕），所以沒有進一步嘗試。
  - **需要你親自做的 30 秒操作**：開啟 Podman Desktop → 左側齒輪圖示「Settings」→「Preferences」
    → 找到「Podman」分類 → 「Path to Podman Binary」欄位填入
    `/Users/haochenglin/.local/podman/bin/podman` → 存檔。完成後回報，我可以立刻重新檢查
    Containers/Images/Volumes/Logs 是否正確顯示。
  - **這與本專案程式碼完全無關**；`podman ps`/`podman logs`/`podman machine list` 在 Terminal 裡
    一律正確顯示容器與機器狀態（已多次驗證），在你設定上面那個欄位之前，教師可持續改用 Terminal
    驗證，或若是用官方標準流程安裝 Podman（而非手動展開 `.pkg`），通常不會遇到這個問題。

## Notes
Own names/port (`riskscope-portable`, 8100) never collide with other deployments. Named volumes inherit uid 10001 ownership; if you use a bind mount add `:U` (Linux). Image is plain `python:3.12-slim` + pure-Python deps, so it builds natively on ARM64 and AMD64.
