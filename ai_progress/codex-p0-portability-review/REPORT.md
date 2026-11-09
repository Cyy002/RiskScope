# Codex P0 Podman 可移植性獨立審查

日期：2026-11-01。限定短週期審查；未修改產品程式或部署檔案。

結論：**目前不能據此認定已滿足教授跨平台重現要求。** 8 項契約測試為 **5 passed、2 failed、1 skipped**。兩個部署設定問題需要 Claude-b 修正；本執行環境未找到 Podman，因此無本輪容器實測。未重新審查 M12.5.1 工程語意。

## 已確認問題與最小修復建議

### P1 — 複製環境範例會破壞容器連向宿主機模型的設定

- 位置：`.env.example:1,7,17`、`compose.yml:18`。
- 重現：依範例說明複製成 `.env`，其生效值為 `OLLAMA_URL=http://127.0.0.1:11434`。Compose 的 `${OLLAMA_URL:-http://host.containers.internal:11434}` 因此採用前者。
- 影響：預設獨立網路容器會連自己的 loopback，而不是主機 Ollama；網頁健康檢查仍可能成功，不能作為模型或 Agent 全流程成功證據。
- 證據：測試 05 失敗。這是設定求值與網路拓撲的靜態驗證，未聲稱本輪實際呼叫容器中的 Ollama。
- 建議：分開 host/container 環境範例，或讓共用範例不覆蓋 Compose 的 gateway 預設；文件明確說明每個平台的模型位置、監聽及防火牆需求。
- 另有文件錯誤：範例註解說不設定 URL 會自動採用 loopback，但 `app/config.py:8` 的真實預設為空，表示未設定模型。

### P1 — 私密檔案未從容器建置範圍排除

- 位置：`.containerignore:1–6`，建置 context 為 `compose.yml:4` 的 `.`。
- 缺少 `.env` 與 `ai_progress/backups/` 排除；專案可見有 backups 目錄，但本輪**未開啟備份或實際憑證內容**。
- 證據：測試 06 對現有簡單 ignore 清單失敗；這是 manifest 安全契約，不是完整 Podman ignore 引擎模擬。
- 影響範圍：這些路徑沒有被排除在可供 builder 使用的內容之外。實際是否傳送、傳送範圍與快取行為依 builder；本輪未測。
- **未證實最終映像包含秘密**：現有 Containerfile 僅 COPY app/scripts/data 與依賴檔案，未 COPY `.env` 或 ai_progress。不能把建置內容風險寫成已發生的映像洩漏。
- 建議：部署負責人排除 `.env`、備份、測試憑證與稽核證據等私人路徑；保留所需公開範例及依賴。不要為了測試讀取正式秘密。

### P2 — 入口文件及預設與本輪隔離交付目標不一致

- `README.md:69–75` 的替代命令仍用映像 0.1、容器 `riskscope`、精確 volume `riskscope_runtime`、正式埠 8000 與 `--rm`。在目前工作主機不應直接照跑。
- `compose.yml:6–10` 也用 0.1 與埠 8000。Compose 的 logical volume 通常有專案名稱前綴，**不能僅憑名稱就認定它必定掛載精確的正式 volume**；需以部署工具輸出的實際名稱驗證。
- 建議：新增隔離交付入口，預設獨立 image/container/volume/port，遇到正式保留名稱拒絕執行；明確區分展示部署與正式部署。舊命令需標示為歷史而非現行操作入口。

## 八項獨立測試

| 編號 | 驗證 | 證據類別 | 結果 |
|---|---|---|---|
| 01 | 空資料目錄建立 schema、三個測試帳號及 0600 憑證 | macOS 主機 Python，臨時 SQLite | PASS |
| 02 | 兩個全新實例的隨機憑證不同、自己的登入成功、跨實例憑證被拒 | 主機實際驗證函式 | PASS |
| 03 | URL、模型名、73 秒設定傳入 Ollama 請求；think:false | **mock HTTP transport** | PASS |
| 04 | Containerfile/Compose/config/依賴沒有 Mac 絕對路徑或強制 ARM64 旗標 | 靜態檢查 | PASS |
| 05 | 複製範例後仍須保留容器到宿主機模型位址 | 靜態設定契約 | FAIL |
| 06 | 建置內容排除 `.env` 與備份路徑 | 靜態安全契約 | FAIL |
| 07 | 認證 API 實際跑檢索、工程計算、依賴追蹤與分析保存；全新 Python 程序仍可認證讀回 | **真實確定性 Agent/API，無 LLM、無容器** | PASS |
| 08 | 乾淨 Podman volume 初始化、同一容器再次啟動、憑證與使用者保留 | 預備好的真實 Podman 測試 | **SKIP：執行環境無 Podman** |

測試 07 不是固定回傳 mock：檢查 11A／264W、來源文件、影響節點、tool_calls、requires_human_review 與已保存的 analysis_id；未經授權 POST 會被拒，沒有建立任何 action。重啟的是 Python 程序，不是 Podman。

測試 08 必須顯式提供已建置的 image SHA256；使用 UUID 命名的全新資源、`--pull=never`、`--network=none`，不開 host port、不掛 host 路徑，也不接受正式 volume 名稱。清理僅限自己建立的名稱。它**尚未在引擎執行**，需先由 Claude-b 審閱並在其測試環境驗證。

## 跨平台與模型限制

| 環境 | 本輪實際證據 | 本輪不能宣稱 |
|---|---|---|
| macOS ARM64 | Python/API/SQLite + 靜態與 mock 測試 | Podman 建置、volume 權限、容器重啟、真實 LLM |
| Linux AMD64 獨立主機 | 無 | 已實測成功 |
| Windows AMD64 + Podman | 無 | 已實測成功、Windows volume 權限已驗證 |

Containerfile 使用通用 `python:3.12-slim`，沒有硬編碼 ARM64；這仍不證明 AMD64 套件輪子、建置或執行成功。`USER risk` 的 UID 10001 與掛載 volume 的寫入權限，還需在真正引擎上檢查，不能由主機 tmp_path 測試推論。

`app/config.py:32–39` 目前僅允許 HTTP loopback 與 `host.containers.internal`。`http://ollama:11434` sidecar 名稱及一般 LAN IP 會被拒；這是既有安全設計，不能為了跨平台直接關閉 allowlist。若 Claude-b 選擇這些部署拓撲，須交 Claude 實作有界、明確的可配置允許政策。本輪只證明已允許的 gateway URL、模型名稱與回覆 timeout 可設定，未驗證實際連線。

真實模型完整驗收仍需要：以新憑證對隔離容器登入、確認實際模型名稱及 endpoint、執行分析並保存來源/工具結果、記錄回覆來源與時間、區分可信度拒絕後備援與真正模型成功。單獨 `/health`、mock 回應或本輪確定性分析都不夠。

## 重現與證據保存

從專案根目錄執行：

```bash
.venv/bin/python -m pytest ai_progress/codex-p0-portability-review/test_portability_contracts.py -q -ra -p no:cacheprovider
```

預設使用 `snapshot/` 的凍結來源，避免 Claude 平行修改造成結果漂移。若驗收修復版，可設 `P0_REVIEW_SOURCE` 為該版本的獨立來源目錄，保留原本 snapshot/log 不變，並將新結果另存。測試 05/06 的斷言針對本次簡單 Compose／ignore 結構；若部署結構重設，需證明等效契約再調整測試解析，不能把解析器不支援等同產品缺陷。

Podman 生命週期測試另需 `P0_REVIEW_IMAGE=sha256:<64位十六進位>`；未提供或引擎不存在時跳過，絕不自動拉映像、建置或操作正式容器。

證據：`pytest.log`、`results.xml`、`snapshot_manifest.json`、`environment_and_scope.json`、`test_portability_contracts.py`、來源 `snapshot/`。未保存生成的測試 DB 或憑證至交付包。測試只執行一輪，未重跑 Claude 的完整測試集。

本輪未安裝 Podman、未啟動 machine／正式服務、未讀正式 Token／volume、未呼叫真實模型。資料安全結論限於**本輪沒有操作正式環境**，不是新一次正式資料完整性稽核。來源雜湊於測試結束核對未變；專案當時沒有 `.git`，不能宣稱有 Git 分支或乾淨工作樹。

## 交接

下一負責人：Claude-b 修復部署問題並完成真實容器生命週期與平台證據；Claude 僅在模型拓撲確實需要時處理 core allowlist/config。Copilot 將本輪結果列入交付矩陣，保留上述證據類別與未測狀態。請整合負責人將此報告摘要併入 `00_STATUS.md`／`60_NEXT_HANDOFF.md`；Codex 不與其他 Agent 同時寫共用總表。

本輪限定審查完成後停止。尚未具備宣稱教授 P0 全部通過的證據，也沒有正式部署授權。
