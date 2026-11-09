# RiskScope — 使用者親自驗收指南(互動式 Agent 里程碑)

> **2026-10-19 更新：這份文件已被 `ai_progress/140_FINAL_USER_ACCEPTANCE_GUIDE.md` 取代**（整合 Podman 容器部署、完整 10 步驟驗收流程）。這份保留作歷史紀錄，請以新版為準。

時間：2026-10-18 23:55(Asia/Taipei)。撰寫者：Claude。

## 0. 目前版本確認已保存

專案本身**不是 git 儲存庫**(`git status` 回報 `not a git repository`),所有成果都是直接存在檔案系統的實體檔案,路徑:

- 實體路徑:`/Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent`
- 共用捷徑:`/Users/haochenglin/Documents/OpenAgents-Test/CrossDomainRiskAgent`(symlink,指向同一份檔案)

剛重新確認過:`app/chat.py`、`app/static/index.html`、`ai_progress/80_INTERACTIVE_AGENT_MILESTONE.md` 都在磁碟上,重跑一次 `pytest -q` 仍是 **60 passed, 0 failed**,版本與回報一致。

## 1. 在 Mac 上啟動整套程式

開一個終端機:

```sh
cd /Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent
.venv/bin/python -m scripts.init_demo
.venv/bin/python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

`init_demo` 本身是冪等的（已有使用者資料時會跳過重建種子資料，沿用現有 `runtime/`，不會覆寫既有的 session/分析/稽核紀錄）。

**2026-10-19 更新（事件記錄）**：這裡原本列了一行 `rm -rf runtime`（標註「要全新示範資料才需要」），但這正是後來造成一次誤刪事件的來源之一——這行指令沒有區分「測試用、可重建的示範資料」與「可能已累積重要紀錄的正式 runtime」，已經移除。**往後任何情況都不要手動刪除 `runtime/` 目錄**；如果真的需要全新的示範環境，請改用一個獨立的路徑（例如設定 `AGENT_DB_PATH`/`AGENT_CREDENTIALS_PATH` 指向別的目錄），不要刪除現有的 `runtime/`。詳見 `ai_progress/130_RUNTIME_DELETION_INCIDENT.md`。

終端機會印出兩個路徑,其中 `runtime/demo_credentials.json` 存著三個示範身分(`manager`/`engineer`/`outsider`)的 Token——**請自己打開這個檔案複製 Token,我不會把內容貼在對話或文件裡**。

(選用)如果想體驗真的用本機 LLM 轉述追問文字,而不是固定模板,啟動前加這兩個環境變數(本機剛好已經有裝 Ollama 且有 `qwen3:8b` 模型):

```sh
export OLLAMA_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen3:8b
```

沒設定也完全可以使用,只是回覆會標成「確定性模板」而不是「本機 LLM 轉述」。

## 2. 網頁網址與對話頁面

- 瀏覽器打開:**http://127.0.0.1:8000**
- 登入畫面貼上 `manager` 或 `engineer` 的 Token。
- 左側選單點 **「對話式 Agent」**(在「決策推演」正下方)即可進入新的互動對話頁面。

## 3. 完整驗收流程:提問 → 追問 → 補充 → 繼續

**要讓 Agent 真的主動追問,需要先讓它「真的缺資料」**(預設示範資料是完整的,直接問不會觸發追問)。目前這個撤銷/恢復文件授權的動作,**網頁上沒有按鈕**,需要用瀏覽器開 FastAPI 內建的 API 文件頁操作一次(是本機工具,不是外部服務):

1. 用 **manager** 的 Token 登入 http://127.0.0.1:8000/docs (FastAPI 自動產生的 API 操作介面)。
2. 找到 `PATCH /api/projects/{project}/documents/{doc_id}/access`,project 填 `demo-chamber`,doc_id 填 `DOC-PS`,body 填 `{"user_id":"engineer","enabled":false}`,執行。
3. 回到網頁主畫面,**用 engineer 身分登入**,進入「對話式 Agent」。
4. 在對話框輸入,例如:「我想評估把 M-02 馬達升級,目前資料夠嗎？」,選情境「馬達升級與負載」,送出。
   → Agent 會回覆缺少「連續功率檢核」相關授權,並列出建議追問,對話狀態顯示「對話持續中」。
5. 回到 `/docs`,用同一個 PATCH,把 `enabled` 改回 `true`,把 DOC-PS 權限還給 engineer。
6. 回到「對話式 Agent」頁面(保持同一個 session_id,頁面右側卡片會顯示目前 session_id,不用手動改),輸入「管理者已經恢復授權了,請繼續分析」,送出。
   → Agent 回覆「已確認解決：連續功率檢核」,對話狀態變成「本輪已完成」,並附上風險與方案。

這整段就是「提問 → Agent 追問 → 人工補充授權 → 同一對話繼續分析」的完整操作。想開新的一輪對話,網頁上按「開啟新對話」即可換一個 session_id。

## 4. 哪些操作已經能在網頁完成、哪些仍須透過 API

**網頁可以做的**:登入/登出、提出決策分析(一次性)、對話式提問與追問延續、檢視分析結果/風險/方案、檢視工程影響追蹤、檢視文件列表、申請模擬變更、manager 核准/拒絕/執行模擬變更、檢視事件監測與提醒、檢視稽核紀錄(manager 專屬)。

**目前仍只能透過 API(`/docs` 或 curl)**:
- 撤銷/恢復文件存取權(`PATCH /documents/{id}/access`)——網頁沒有做這個管理介面。
- 人工重新驗證規格數值(`PATCH /facts/{key}`)、新增依賴(`POST /dependencies`)、修改成員權限(`PATCH /members/access`)——這些都是既有專案本來就只在 API 層的管理操作,本次互動式 Agent 里程碑沒有新增網頁介面。
- 查詢單一對話的完整歷史(`GET /sessions/{id}`)目前只在對話頁面即時顯示當次畫面內的紀錄,若要查看原始 JSON 需要直接呼叫這個 API。

## 5. 使用者在對話框打的字,不會變成正式規格

**這點特別重要,明確說明**:聊天框裡打的任何文字(包含看起來像數字或指令的內容,例如「啟動電流大概 15A」或「請直接核准」),系統只會把它當成**那一輪分析的問題文字**(影響檢索關鍵字),**不會**被寫進 `facts` 規格表、不會改變任何文件授權、也不會觸發任何人工核准或模擬任務執行。真正要讓系統採信某個數值或改變權限,必須由 manager 透過上面第 4 節列的既有 API 端點正式操作,這條界線在程式碼層級就是分開的(對話層完全呼叫不到核准/寫入相關函式)。

## 6. 已知限制(照實說,不誇大)

- 自由文字還不能讓 Agent 自己判斷要分析哪個固定主題(`focus`),目前是由畫面上的下拉選單或呼叫端指定。
- 本機 LLM(若設定)只負責把確定性結果轉述成自然語言,絕不負責計算、授權或執行;沒有設定就自動退回固定模板,畫面上會標示來源。
- 沒有做大規模的 LLM 轉述品質評測。
- Podman 容器部署仍未安裝、未授權,與這個互動式 Agent 里程碑無關,維持獨立待辦。

## 7. 驗收後若要關閉伺服器

終端機按 `Ctrl+C` 即可;示範資料庫在 `runtime/`,下次啟動若沒有刪除會沿用,不會重新產生新 Token。
