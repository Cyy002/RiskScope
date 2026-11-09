# Antigravity 獨立環境相容性與 Podman 跨平台可移植性調查報告

- **報告日期**：2026-11-01
- **調查代理**：`@antigravity`
- **所屬專案**：RiskScope (`/Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent`)
- **對應最高優先級**：教授期末硬性要求 P0（Podman 跨平台可重現執行）
- **關聯目錄與證據**：`ai_progress/antigravity-portability/`

---

## 執行摘要 (Executive Summary)

本報告針對期末交付的最高硬性要求（「若無法透過 Podman 環境執行，視同專案失敗；必須能夠透過 Podman engine 在不同平台重現」），對目前環境、虛擬化架構、CPU 跨架構能力、容器網路連線、儲存權限及部署腳本進行了全方位的**獨立唯讀與隔離驗證**。

**核心結論**：
1. **本機環境與跨架構能力突破**：本機為 macOS ARM64（Apple Silicon），Podman 6.1.4 運行於 Apple Hypervisor (`applehv`) 的 Fedora CoreOS 44 虛擬機中。我們證實了虛擬機內已啟用靜態 QEMU 模擬器 (`/usr/bin/qemu-x86_64-static`)，本輪已**成功建置並實機執行 `linux/amd64` 架構的 RiskScope 映像 (`localhost/riskscope-portable:amd64-test`)，並於該 amd64 容器內成功跑通 45/45 項核心評估案例**。
2. **非破壞性原則與正式環境安全**：正式服務 `http://127.0.0.1:8000`、容器 `riskscope`（0.4 版）及正式 Volume `riskscope_runtime` 全程未受任何干擾或修改。所有相容性測試皆使用獨立臨時容器與名稱隔離之 Volume。
3. **發現多項跨平台部署阻礙（已整理修復建議）**：
   - **P0 網路阻礙**：`app/config.py:32-39` 的 `local_ollama_url()` 嚴格限定只接受 `localhost`, `127.0.0.1`, `::1`, `host.containers.internal`。若在 Windows (Docker Desktop/WSL2) 上使用 `host.docker.internal` 或自訂 Gateway IP/服務名稱（如 compose 內的 `ollama`），會被一律判定為無效端點，導致靜默降級回退至確定性備援。
   - **P1 範例設定陷阱**：`.env.example` 預設未註解的值為 `http://127.0.0.1:11434`，若使用者依文件指示 `cp .env.example .env`，容器內會連向容器自身的 loopback 而非主機 Ollama，導致模型連線失敗。
   - **P1 安全洩漏風險**：`.containerignore` 遺漏了 `.env` 與 `ai_progress/backups/`，有將私人環境設定或備份檔案打包進映像 context 的風險。
   - **P1 PowerShell 驅動腳本缺陷**：`deploy/riskscope.ps1` 遺漏了 `--add-host=host.containers.internal:host-gateway`；且在健康檢查迴圈中使用 `exit 0`，會直接關閉 Windows 使用者的終端視窗。
   - **P1 容器內部環境變數缺陷**：`Containerfile` 缺少 `ENV PYTHONPATH=/app`，導致容器內部使用 `python scripts/evaluate.py` 等腳本時會發生 `ModuleNotFoundError: No module named 'app'`。
   - **P1 Linux Host Network 衝突**：`deploy/riskscope.sh` 在 `RS_HOST_NETWORK=1` 時會直接佔用主機 port 8000（與正式服務衝突），且健康檢查仍 curl 8100 導致失敗。
4. **誠實申報跨平台實測邊界**：
   - macOS ARM64：**實機通過**（原生 ARM64 容器與真實 Qwen 模型連線成功）。
   - Linux AMD64：**架構相容性通過**（在 CoreOS VM 內透過 QEMU 成功建置 AMD64 映像並執行 45/45 評估，但非原生 Linux AMD64 裸機）。
   - Windows AMD64：**尚未實機驗收**（缺乏 Windows 實體環境，腳本已完成靜態審查與缺陷標註）。

---

## 一、Mac 現有 Podman 環境與 Machine 配置調查 (D1.1)

### 1.1 主機與客戶端環境規格
- **主機 OS**：macOS (Darwin 24.x, Apple Silicon ARM64)
- **Podman CLI 路徑**：`/Users/haochenglin/.local/podman/bin/podman` (版本 6.1.4, commit `464c15fec06f0074c916f9eff87c4806869c2833`)
  > [!NOTE]
  > Podman 未安裝於系統標準 `/usr/local/bin` 或 `/opt/homebrew/bin`，而在 `~/.local/podman/bin`。在未載入使用者 `.zshrc` 的無狀態 shell 中，必須顯式指定 `export PATH="$HOME/.local/podman/bin:$PATH"`。

### 1.2 Podman Machine 配置 (`riskscope-machine`)
- **虛擬機名稱**：`riskscope-machine`
- **虛擬化引擎 (VM TYPE)**：`applehv` (Apple Hypervisor Framework)
- **硬體資源配置**：4 vCPUs, 4096 MB (4 GB) 記憶體, 20 GB 虛擬磁碟
- **網路模式**：`UserModeNetworking: true` (透過 gvproxy 提供容器與虛擬機網路)
- **執行權限**：`Rootful: false`（非 root 模式，虛擬機內遠端使用者為 `core`）
- **Rosetta 支援**：`Rosetta: false`（未啟用 Apple Rosetta 2 for Linux）
- **虛擬機 Guest OS**：`Fedora CoreOS 44.20260913.3.2 (CoreOS)`
  - 核心版本：`Linux 7.2.5-200.fc44.aarch64 #1 SMP PREEMPT_DYNAMIC`
- **VirtIO-FS 主機目錄掛載**：
  - `/Users` -> 掛載為 `virtiofs`
  - `/private` -> 掛載為 `virtiofs`
  - `/var/folders` -> 掛載為 `virtiofs`
  - **重要發現**：主機 `/tmp` **未**包含在 VirtIO-FS 自動共享清單中。若在容器中使用 `-v /tmp/xxx:/app/runtime` 進行主機目錄綁定，Podman 會拋出 `Error: statfs /tmp/xxx: no such file or directory (exit 125)`。

---

## 二、可用 CPU 架構與跨架構能力實測 (D1.2)

### 2.1 模擬機制檢查
在 `riskscope-machine` 虛擬機內部檢查 `/proc/sys/fs/binfmt_misc`：
- `status`: `enabled`
- 註冊直譯器：`/usr/bin/qemu-x86_64-static`
- 旗標：`POCF` (Preserve argv[0], Open binary, Credentials, Fix binary)
- 結論：虛擬機具備 QEMU User-Mode Emulation 執行 AMD64 (x86_64) 二進位程式的能力。

### 2.2 AMD64 基礎映像與 Python 執行驗證
1. **AMD64 Alpine 測試**：
   ```bash
   podman run --arch=amd64 --rm docker.io/library/alpine:latest uname -m
   # 輸出: x86_64 (驗證通過)
   ```
2. **AMD64 Python 3.12-slim 測試**：
   ```bash
   podman run --arch=amd64 --rm docker.io/library/python:3.12-slim python3 -c 'import platform, sys; print(platform.machine(), sys.platform)'
   # 輸出: x86_64 linux (驗證通過)
   ```

### 2.3 AMD64 RiskScope 映像建置與 45 項評估實測
我們在隔離環境中使用 `Containerfile` 執行了 AMD64 多架構建置：
```bash
podman build --arch=amd64 -t localhost/riskscope-portable:amd64-test -f Containerfile .
```
- **建置結果**：成功產生映像 ID `da4b9fe0ac9e57a869ffdb8913777b8b0a503e946a43ddce82fbac2ed6602ac6`。
- **純 Python 依賴分析**：`requirements.txt` 與 `requirements-langgraph.txt` 中的依賴套件（`fastapi`, `uvicorn`, `pydantic`, `httpx`, `langgraph` 等）在 PyPI 上皆具備官方編譯之 `manylinux_2_17_x86_64` 二進位輪子，在建置過程中完全無需於容器內編譯 C 程式碼，建置順暢無任何相容性阻礙。
- **45 項評估驗收**：
  在 `localhost/riskscope-portable:amd64-test` 容器內執行 `python3 scripts/evaluate.py`，全數 **12 個測試主題、45/45 個多跳推理約束路徑全數 PASS（Recall 1.0, Precision 1.0）**。
- **獨立生命週期與持久化驗證**：
  使用 Codex 的 `test_08_podman_clean_volume_lifecycle_and_persistence` 針對該 AMD64 映像進行驗證，成功在全新 Volume 上初始化帳號、重啟容器並驗證資料庫與憑證持久化，耗時 3.15 秒全數通過。

---

## 三、模型網路連線與跨平台機制 (D1.5)

### 3.1 macOS Podman Machine 網路路徑
- 在 macOS Podman 中，容器透過 `--add-host=host.containers.internal:host-gateway` 可正確解析出虛擬網關 IP `192.168.127.254`。
- 容器內部測試：`urllib.request.urlopen("http://host.containers.internal:11434/api/tags")` 傳回 HTTP 200，成功讀取主機 Ollama 上的 `qwen3.6:27b` 與 `qwen3:8b` 模型。

### 3.2 跨平台網路障礙：`app/config.py` 嚴苛白名單阻擋
在 `app/config.py:32-39`：
```python
def local_ollama_url() -> str | None:
    if not OLLAMA_URL:
        return None
    from urllib.parse import urlparse
    url = urlparse(OLLAMA_URL)
    if url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1', 'host.containers.internal'}:
        return None
    return OLLAMA_URL.rstrip('/')
```
> [!WARNING]
> 這是跨平台部署的**重大脆弱點**：
> 1. **Docker Desktop 相容性**：Docker Desktop 在 Windows 與 macOS 上的標準主機網域名稱為 `host.docker.internal`。若使用者以此環境啟動容器，`url.hostname` 會被 `local_ollama_url()` 直接判定無效而傳回 `None`！
> 2. **Compose 服務拓撲**：若在 `compose.yml` 中定義獨立的 `ollama` 容器服務，其內部服務名稱為 `http://ollama:11434`，亦會被直接拒絕。
> 3. **Linux Rootless Podman 網關**：在某些 Linux 發行版中，使用者可能透過 Bridge IP（例如 `10.88.0.1`）或主機區域網 IP 連向本機 Ollama，此類 IP 同樣會被無情拒絕。
> 4. **Windows WSL2 網關**：在 Windows 宿主機上執行 `ollama.exe` 時，WSL2 內部存取 Windows 主機通常需透過 `/etc/resolv.conf` 的 nameserver IP（如 `172.x.x.x`），若不允許此 IP，模型將完全無法連線。

**修復建議（交給 @claude）**：
在 `app/config.py` 中允許 `host.docker.internal`，以及常見的本機私有網段 IP（或允許透過環境變數 `ALLOW_LOCAL_NETWORK_OLLAMA=1` 擴充白名單），在不破壞「禁止連接外部雲端付費端點」的安全原則下，確保跨平台網路連通。

---

## 四、儲存權限、Volume 與 Bind Mount 差異 (D1.6)

### 4.1 容器權限設計
- `Containerfile` 第 9-10 行：
  ```dockerfile
  RUN mkdir -p /app/runtime && useradd -u 10001 -m risk && chown -R risk:risk /app/runtime
  USER risk
  ```
- 容器以非 root 使用者 `risk` (UID 10001) 運行。

### 4.2 Named Volume vs Host Bind Mount 實測
1. **Named Volume（強烈推薦）**：
   - 指令：`podman run -v riskscope_portable_data:/app/runtime ...`
   - 行為：Podman 會在使用者命名空間中直接為 Volume 配置適當的擁有權，UID 10001 可直接進行讀寫與建立 SQLite 資料庫。在 macOS、Linux、Windows WSL2 上皆完全相容。
2. **Host Bind Mount（存在權限地雷）**：
   - 指令：`podman run -v ./runtime:/app/runtime ...`
   - **Linux 環境限制**：在 Linux Rootless Podman 下，主機目錄通常隸屬於主機 UID 1000。容器內 UID 10001 會映射到主機的 subuid（如 110000）。若目錄權限為 `0755`，容器會立即發生 `PermissionError: [Errno 13] Permission denied`！必須顯式加上 `:U` 旗標（`-v ./runtime:/app/runtime:Z,U`）或使用 `--userns=keep-id`。
   - **Windows NTFS / DrvFs 限制**：在 WSL2 中直接掛載 Windows NTFS 檔案夾（如 `/mnt/c/...`），SQLite 的 WAL (Write-Ahead Logging) 鎖定機制在 9P / drvfs 檔案系統上經常會發生 `database is locked` 異常。因此**期末交付必須硬性要求使用 Podman Named Volume**。

---

## 五、部署腳本與設定檔缺陷清查 (D1.7)

針對 Claude-b 與既有設定進行靜態審查，清查出以下具體缺陷：

### 5.1 缺陷 1：`.env.example` 覆蓋陷阱（Codex 測試 05 失敗點）
- **檔案**：`.env.example:7`
- **現狀**：`OLLAMA_URL=http://127.0.0.1:11434`
- **問題**：使用者依慣例 `cp .env.example .env` 後，`compose.yml` 或 shell 會讀取此值，將容器內部的 `OLLAMA_URL` 覆蓋為 `127.0.0.1`，導致容器在隔離網路中無法連向主機模型。
- **修復**：範例預設值應改為 `OLLAMA_URL=http://host.containers.internal:11434`，並以註解說明本機開發時才改為 `127.0.0.1`。

### 5.2 缺陷 2：`.containerignore` 遺漏私密路徑（Codex 測試 06 失敗點）
- **檔案**：`.containerignore`
- **現狀**：僅包含 `.venv/`, `__pycache__/`, `.pytest_cache/`, `runtime/`, `*.pyc`, `*.zip`。
- **問題**：遺漏了 `.env` 與 `ai_progress/backups/`。
- **修復**：在 `.containerignore` 中加入 `.env` 與 `ai_progress/backups/`。

### 5.3 缺陷 3：`deploy/riskscope.ps1` 遺漏 `--add-host` 與 `exit 0` 問題
- **檔案**：`deploy/riskscope.ps1:14-16`
- **問題 A**：第 14 行啟動容器時缺少 `--add-host=host.containers.internal:host-gateway`，導致 Windows Podman 容器可能無法解析宿主機 gateway。
- **問題 B**：第 15 行健康檢查成功時執行 `exit 0`。若助教或評審是在現有 PowerShell 視窗中執行腳本，這會直接強制結束關閉他們的整個終端視窗！應改為 `break` 或 `return`。

### 5.4 缺陷 4：`Containerfile` 遺漏 `ENV PYTHONPATH=/app`
- **檔案**：`Containerfile:2`
- **問題**：當使用者或腳本在容器內執行 `python scripts/evaluate.py` 或獨立工具時，Python 的 `sys.path[0]` 為 `/app/scripts`，找不到 `/app` 下的 `app` 模組，報錯 `ModuleNotFoundError: No module named 'app'`。
- **修復**：在 `Containerfile` 加入 `ENV PYTHONPATH=/app`。

### 5.5 缺陷 5：`deploy/riskscope.sh` 之 `RS_HOST_NETWORK=1` 連鎖衝突
- **檔案**：`deploy/riskscope.sh:12-14`
- **問題**：若啟用 `RS_HOST_NETWORK=1`，容器直接綁定主機 port 8000（會與正式 0.4 服務衝突），而腳本的健康檢查迴圈固定 curl `http://127.0.0.1:$PORT/health`（`$PORT=8100`），導致即使容器啟動成功，健康檢查也會逾時報錯。

---

## 六、教授 P0 跨平台驗收矩陣 (Portability Matrix)

| 平台環境 | CPU 架構 | 驗收類型 | 實測狀態 | 實測證據與說明 |
|---|---|---|---|---|
| **macOS (Darwin 24.x)** | ARM64 | 實機測試 | **通過 (PASS)** | Podman 6.1.4, port 8100, 獨立 Volume, 真實 Qwen 27B/8B 連線, Web GUI/API 正常 |
| **Fedora CoreOS (VM)** | aarch64 | 實機測試 | **通過 (PASS)** | 容器內部原生 Linux aarch64 執行, 帳號/Schema 初始化正常, 獨立 Volume 持久化通過 |
| **Linux (模擬)** | x86_64 (AMD64) | 模擬建置實測 | **通過 (PASS)** | 透過 QEMU 成功建置 `riskscope-portable:amd64-test`，45/45 評估全過，Codex 測試 08 通過 |
| **Linux (實體主機)** | AMD64 | 靜態分析 | **尚未實測 (UNVERIFIED)** | 本機無獨立 Linux AMD64 實體機，禁止虛構；已驗證所有依賴套件均具備 Linux x86_64 wheel |
| **Windows 10/11** | AMD64 + Podman | 腳本審查 | **尚未實測 (UNVERIFIED)** | 本機無 Windows 環境；已完成 `.ps1` 腳本靜態檢驗並標註 `--add-host` 與 `exit 0` 缺陷 |

---

## 七、跨代理工作交接清單 (Handoff)

### 7.1 給 @claude-b（部署與容器負責人）
1. **修正 `deploy/riskscope.ps1`**：
   - 補上 `--add-host=host.containers.internal:host-gateway`。
   - 將健康檢查成功的 `exit 0` 改為 `return` 或 `break`，防止關閉使用者終端。
2. **修正 `Containerfile`**：
   - 在 `ENV` 中加入 `PYTHONPATH=/app`，使容器內任意路徑執行腳本皆可正確匯入 `app`。
3. **修正 `.containerignore` 與 `.env.example`**：
   - `.containerignore` 補上 `.env` 與 `ai_progress/backups/`（讓 Codex 測試 06 變綠）。
   - `.env.example` 預設改為 `http://host.containers.internal:11434`（讓 Codex 測試 05 變綠）。
4. **修正 `deploy/riskscope.sh`**：
   - 在 `RS_HOST_NETWORK=1` 時調整健康檢查 port，並警告避免與正式 8000 port 衝突。

### 7.2 給 @claude（第一主力，核心程式負責人）
1. **放寬 `app/config.py` 之 `local_ollama_url()`**：
   - 建議新增支援 `host.docker.internal` 以及常見本機私有 IP（例如 `10.88.0.1`, `172.17.0.1` 等），以支援 Docker Desktop 及 WSL2/Linux 宿主機模型連線。
2. **繼續完成 M12.5.1 核心修復**：
   - 解決名目額定與實際可用容量混淆，並確保第一輪對話 `馬達電流11A ... 輔助3A` 正確產出 14A（目前仍為 11A，需修復 `_unclaimed_change_intents` 與初始方案繼承）。

### 7.3 給 @copilot（交付文件負責人）
1. **更新期末跨平台手冊與驗收矩陣**：
   - 將本報告之規格數據、VirtIO-FS 限制、Linux Named Volume 建議及跨平台驗收矩陣納入期末交付文件中。
   - 嚴格遵守教授要求：明確標註 macOS ARM64 為實機實測，Linux AMD64 為 QEMU 模擬實測，獨立 Linux/Windows 主機為靜態驗證待實測。

---
*本報告已歸檔至 `ai_progress/antigravity-portability/PORTABILITY_INVESTIGATION_REPORT.md`，原始資料請參閱同目錄下之 JSON 檔案。*
