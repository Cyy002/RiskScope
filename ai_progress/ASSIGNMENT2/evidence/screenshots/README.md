# 正式交付截圖清單 (Claude A + claude-b，2026-11-09/10)

全部為真實操作截圖（非合成示意圖），對應真正運行中的 RiskScope 容器（獨立測試 VM
`riskscope-codex-apple-20261107`，與正式機 `riskscope-machine` 完全分離）。部分來自
Claude A 本輪重新乾淨操作，部分來自 claude-b「教授第一次驗收模擬」的真實瀏覽器點擊。

| # | 檔案 | 內容 | 對應作業二要求 |
|---|---|---|---|
| 01 | `01_podman_desktop_dashboard.png` | Podman Desktop 首次啟動畫面，提示「Podman needs to be set up」 | Podman 部署（誠實呈現：這台機器的非標準 Podman 安裝方式會讓 Desktop GUI 這樣顯示） |
| 02 | `02_podman_desktop_no_container_engine.png` | Podman Desktop「Containers」頁顯示 No Container Engine | 同上，誠實記錄 GUI 整合限制——不影響 CLI 部署本身成功與否 |
| 03 | `03_login.png` | RiskScope 登入頁（Bearer Token 輸入框，未填入真實 Token） | 對話觸發前的授權登入 |
| 04 | `04_dashboard_after_login.png` | 登入後的專案總覽（manager 身分，6 份授權文件、工作項目狀態） | 授權資料檢索 |
| 05 | `05_agent_chat_reply_with_tool_check.png` | 對話式 Agent 完整真實回覆：14A/336W、超額 40%/75%、風險 R-POWER | Agent 對話觸發 + 真實 Tool 執行（工程計算） |
| 06 | `06_decision_analysis_form.png` | 決策推演頁的輸入表單（決策問題、評估情境、管理優先序） | Agent 對話觸發（跨領域決策路徑） |
| 07 | `07_decision_analysis_tool_check_result.png` | 確定性檢核卡：CONTINUOUS LOAD CHECK 11A/10A額定，標示 `requires_human_review` | 真實 Tool 執行與工程驗證 |
| 08 | `08_impact_tracing_and_manual_review_request.png` | 可追溯工程依賴路徑（M-02/PS-01 多條路徑）+ 人工審核/模擬操作申請表單 | 方案比較（依賴/影響追蹤）+ 管理者模擬核准入口 |
| 09 | `09_manager_approval_confirm.png` | 人工審核中心，TEST-01→blocked 已 approved，準備執行模擬操作確認對話框 | 管理者模擬核准 |
| 10 | `10_manager_approval_executed.png` | 核准後執行完成，狀態變為 `executed` | 管理者模擬核准（完整流程結果） |
| 11 | `11_failure_case_outsider_access_denied.png` | outsider 身分登入，顯示「此帳號沒有 demo-chamber 專案存取權限」 | 錯誤處理/失敗案例之一（另一案例見 `FAILURE_CASES.md` 的 F2/F3，API 層級證據） |
| 12 | `12_podman_desktop_containers_after_binary_path.png` | 設定 `podman.binary.path` 後，Containers 頁正確顯示全部 3 個真實容器（riskscope-portable/-prof/-teacher） | Podman 可重現啟動——GUI 整合（見下方「Podman Desktop 修復」） |
| 13 | `13_podman_desktop_images.png` | Images 頁正確顯示 4 個真實映像（3 個 riskscope-portable 版本 + python base） | 同上 |
| 14 | `14_podman_desktop_volumes.png` | Volumes 頁正確顯示 3 個真實 volume | 同上 |
| 15 | `15_podman_desktop_container_logs_running.png` | riskscope-portable-prof 的即時 Logs（真實 Uvicorn 啟動與 HTTP 請求紀錄） | 同上；也證明該容器真的在跑真實的 RiskScope 應用 |

## Podman Desktop 修復（2026-11-10/11）
01/02 記錄的是**修復前**的真實限制（誠實保留，不刪除）。後續排查直接解壓縮 Podman Desktop 的
`app.asar` 讀取其「Podman」內建擴充功能原始碼確認：該限制的根因是找不到安裝在非標準路徑
（`~/.local/podman/bin/podman`）的執行檔，而 GUI 上的「Set up」按鈕會跳出系統安裝精靈、安裝
*另一套*獨立的 Podman（需要管理員密碼），因此未曾點擊。真正的官方解法是擴充功能本就支援的
`podman.binary.path` 設定（UI 顯示名稱「Path to Podman Binary」，在 Settings → Preferences →
Podman）。使用者本人在 Podman Desktop 裡設定該欄位後，12–15 號截圖證實 Containers、Images、
Volumes、Logs 全部正確顯示——不需要重新安裝、不需要重建或重設任何既有 machine。完整技術細節見
`deploy/README_PODMAN.md` 常見問題一節與 `ai_progress/ASSIGNMENT2/ASSIGNMENT2_FINAL_STATUS.md`。

## 誠實說明
- 所有畫面的 Token 欄位皆為空白或未入鏡；實際登入時 Token 經由系統剪貼簿/accessibility
  API 直接填入輸入框，從未顯示或列印在任何截圖、終端機輸出或 OpenAgents 對話紀錄中。
- 01/02 兩張刻意保留「修復前」的失敗畫面，因為這是本機真實遇到過的限制，不應該被挑選性隱藏；
  12–15 號截圖證實修復後的真實狀態。
- 05 的回覆文字每次重新詢問可能因模型隨機性而措辭略有不同，但結構化數字（14A/336W/40%/75%）
  由確定性工具計算，不受模型輸出影響；本截圖是 2026-11-10 的一次真實重跑。
