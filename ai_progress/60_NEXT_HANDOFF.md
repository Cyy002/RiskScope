# RiskScope v0.1 — 交接報告(最新：runtime 誤刪事件調查 + M3/M4/M5 部署成果)

執行者：Claude。時間：2026-10-19 16:10(Asia/Taipei)。供使用者檢查，以及 Codex/Antigravity/Copilot 恢復後接手。

## 0. 最優先事項：`rm -rf runtime` 事件調查結論

依使用者「M4 部署成果確認與資料安全專項驗收」指示，已完成非破壞性調查，完整報告見 `ai_progress/130_RUNTIME_DELETION_INCIDENT.md`。摘要：

- 被刪除內容全部是本次對話期間 Claude 自己用 `scripts.init_demo` 與測試 API 呼叫產生的示範/測試資料（demo 帳號、2 個驗證用 session、對應分析與稽核紀錄），沒有找到使用者自建資料受影響的證據。
- **這個結論只能依賴本次對話自己的工具呼叫紀錄**——沒有 git 歷史、沒有 Time Machine 本機快照（已確認查無任何快照），無法獨立佐證，已在報告中明確標示這個限制，不誇大確定性。
- 容器用的 `riskscope_runtime` volume（M4 驗收的實際資料）完全沒有受影響，剛非破壞性重新確認過仍完整。
- 根本原因：`scripts/evaluate.py` 的 `init_db()` 冪等設計一偵測到空白就自動重新播種；而我在 M2/M3 階段每次測試前執行 `rm -rf runtime` 的習慣，從第一次就不必要（pytest 從不依賴這個目錄）。已移除 `90_USER_ACCEPTANCE_GUIDE.md` 裡類似的指令，承諾不再對任何 `runtime/` 執行刪除。
- Podman Machine/容器經非破壞性檢查，持續正常運作，沒有重裝或重建。

## 1. 本次實際完成什麼

1. **M3 — Ollama 真實整合修復**：修復造成系統持續回退「確定性模板」的根因（`think:false`、`compose.yml` 環境變數、一個真實 bug、例外處理）。真實驗證成功。
2. **M4 — Podman 實機部署並通過驗收**：使用者正式授權安裝後，已完成 Podman Desktop 安裝、Podman Machine 建立並啟動、RiskScope 容器建置與執行、容器連接主機 Ollama、真實端到端對話測試、重啟持久化測試、ACL/人工核准測試。**9/10 項驗收完全通過**，第 10 項（Podman Desktop GUI 畫面）未經人工操作確認。
3. **M5 — 改善現有 Agent 回答品質**：回覆從籠統一句話改成具體列出已確認條件、計算結果、風險、依據、未確定條件、建議下一步。
4. 沿用先前已完成且不重做的部分：P0 ACL 修復、P1 Session 多輪延續、互動式 Agent 第一版、M2 工程數值暫存與分析。

## 2. 修改/新增了哪些東西

**RiskScope 專案內**（M3 階段完成，本輪未再修改）：`app/llm_client.py`、`app/chat.py`、`app/analyzer.py`、`compose.yml`、`.env.example`、`.gitignore`、3 個測試檔的 monkeypatch 目標修正。

**本機系統層級**（本輪 M4 新增，經使用者明確授權）：
- `/Applications/Podman Desktop.app`（新增）
- `~/.local/podman/bin/`、`~/.local/podman/lib/`（新增，官方簽署執行檔，用唯讀展開取出，未經 root 安裝）
- `~/.config/containers/containers.conf`（新增）
- `~/.zshrc` 新增一行 PATH 設定
- Podman machine `riskscope-machine`（新增，4 CPU/4GiB/20GiB，applehv provider）
- Podman image `riskscope-poc:0.1`、volume `riskscope_runtime`（新增）

## 3. 哪些功能尚未完成

- **Podman Desktop GUI 畫面未經人工確認**：只用 CLI 驗證過底層狀態一致，沒有真的打開應用程式視窗看畫面。
- 沒有測試 Podman machine 層級的 stop/start（只測過容器層級）。
- 這次用 `podman build`+`podman run` 直接指令完成部署，不是 `podman compose`（這台機器沒有 compose provider）；`compose.yml` 檔案正確但未被用來啟動這次的環境。
- 自由文字仍不能讓 Agent 自己判斷 `focus`；沒有使用 LangGraph interrupt/resume；LLM 回覆延遲仍有波動（0.3-30 秒）。
- 使用者第八節提出的示範 Token 輪替，仍只有規劃（見第 8 節），未實作。

## 4. 測試通過與失敗數量

```
.venv/bin/python -m pytest -q          → 84 passed, 0 failed（本機 .venv，與容器部署互相獨立）
.venv/bin/python -m scripts.evaluate   → 12 案 45/45 不變
.venv/bin/python -m pip check           → 乾淨
```

容器內的功能驗證（真實 HTTP 請求，非自動化 pytest）：網頁/API 啟動、容器連主機 Ollama、真實 LLM 回覆、數值抽取+Session、重啟持久化、ACL/人工核准——全部 ✅，詳見 `ai_progress/120_M4_PODMAN_DEPLOYMENT_ACCEPTANCE.md` 第二節逐項對照表。

## 5. LLM 成功回覆的證據

透過**容器**（不是本機 dev server）實測：撤銷文件授權 → 對話中提供「馬達連續電流大約是8A」→ 正確抽取並套用（`reply_source=llm_phrased`，抽取 2.55 秒/轉述 19.2 秒皆成功）→ 恢復授權 → 同一 session 繼續 → 正確解決（11A/264W/fail）。完整逐字內容見 `ai_progress/120_M4_PODMAN_DEPLOYMENT_ACCEPTANCE.md`。

## 6. Podman 部署狀態

**已部署並通過驗收**（9/10 項，見第 1 節第 2 點）。目前 `riskscope-machine` 正在運作中，容器 `riskscope` 正在 `127.0.0.1:8000` 執行。

## 7. 是否存在安全或架構風險

- **沒有發現新的安全退化**：ACL/人工核准在容器環境下用真實請求重新驗證過。
- **`rm -rf runtime` 事件**：已完成專項調查，詳見第 0 節與 `ai_progress/130_RUNTIME_DELETION_INCIDENT.md`。結論是只影響可重建的測試資料，但這個結論的確定性有其限制（見第 0 節），不是「調查完就沒事」。
- 安裝過程全程沒有使用或索取 Mac 管理員密碼，沒有繞過 Gatekeeper/SIP，沒有移除其他已安裝軟體，所有服務只綁 `127.0.0.1`，沒有對外網路暴露。
- 架構風險：本輪由 Claude 單人完成，Codex/Antigravity 尚未參與審查。

## 8. 示範登入 Token 曾出現在截圖中——規劃(本輪仍未實作)

維持上一輪的規劃(新增 manager 專屬 `rotate-token` 端點,只改 `users.token_hash` 一欄,不影響其他資料)。本輪專注在 Podman 部署,沒有變更這部分範圍。等待使用者明確授權後再實作。

## 9. 下一次使用者驗收的完整步驟 / 如何重新開啟 RiskScope

### 用容器(本輪新完成的部署方式)

> **⚠️ 下面這條指令已過時（`0.1`／`--rm`）**，見本檔案最後「容器生命週期與部署建議（M12.3）」一節的正確做法與理由。原文保留只做歷史對照。

```sh
export PATH="$HOME/.local/podman/bin:$PATH"   # 新終端機視窗已經寫進 ~/.zshrc，通常不用再手動打
podman machine start riskscope-machine         # 如果機器已經停止
podman ps                                      # 確認 riskscope 容器是否還在跑
# 容器不在了的話，重新啟動（資料從 riskscope_runtime volume 讀回，不會遺失）：
podman run --name riskscope --rm -d -p 127.0.0.1:8000:8000 \
  -e OLLAMA_URL=http://host.containers.internal:11434 \
  -e OLLAMA_MODEL=qwen3:8b \
  -v riskscope_runtime:/app/runtime \
  riskscope-poc:0.1
```

瀏覽器開 **http://127.0.0.1:8000**。Token 請自己執行 `podman exec riskscope cat /app/runtime/demo_credentials.json` 查看。

### 想確認 Podman Desktop GUI

打開 `/Applications` 裡的「Podman Desktop」，確認是否能看到 `riskscope-machine` 與 `riskscope` 容器——這部分我沒有實際操作過，請自行確認。

### 本機方式（不透過容器，先前就一直可用）

```sh
cd /Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent
export OLLAMA_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen3:8b
.venv/bin/python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

## 10. 哪些成果尚待 Codex 獨立審查

- M3 的 `think:false`/逾時策略（見上一輪交接內容，未變）。
- M4 的安裝替代方案（繞過官方 `.pkg` 安裝流程、改用 `pkgutil --expand` + `applehv` provider）是否有 Codex 從 Podman 角度會建議的更標準做法。
- 本輪新修的 `init_db()` 憑證路徑推導邏輯（見下方 10.1）。

### 10.1 2026-10-20 低額度續接：`init_db()` 憑證覆寫修復

Codex 重現的問題（`ai_progress/codex-review-runtime/runtime-probe-results.json`）已修復：`app/db.py` 的 `init_db()` 在 `path` 有指定但 `credentials_path` 沒有指定時，改成從 `path` 自己的目錄推導憑證檔，不再誤寫進全域預設憑證檔。新增 `tests/test_db_credentials_isolation.py`（3 項），加上 `tests/test_core.py` 共 **40 passed, 0 failed**；正式預設憑證檔全程未被接觸。本輪依使用者指示未重跑全部 85 項測試與 45 項評估，留待安全漏洞集中修復完成後一次執行。

**仍未處理、不得視為完成**：Session 歷史 ACL 洩漏修復待正式驗收、LLM 虛構工程數值、LLM 虛構核准結論、Podman Desktop GUI 使用者驗收、Codex 獨立複驗。

## 11. 停止原因

沒有遇到無法解決的阻礙。`rm -rf runtime` 事件已完成非破壞性調查(第 0 節);M3、M5 已完成並真實驗證;M4 的 10 項驗收 9 項通過,第 10 項(GUI 視覺確認)需要使用者親自操作才能完成,已明確列出。依使用者本輪「本輪不新增其他功能,不重做已通過的 M3、M5,也不進行不必要的容器重建」「完成確認後保存結果並停止,等待我後續指示」,在這裡停下來,不會擅自進行 Token 輪替實作、不會重新安裝或重建 Podman、不會展開新功能。


## 2026-10-20 Codex 限定安全複驗

- Session 歷史 ACL：目前程式與隔離測試通過，共15項（既有7＋獨立8）；確定性／LLM摘要、多來源及top-8之外的證據撤權均遮蔽，正常授權可讀。詳見 `codex-review-reverify/SESSION_ACL_RESULT.md`。
- init_db：修正不完整，4項通過、1項失敗。同目錄的另一個DB仍推導到預設憑證檔並覆寫，使檔案Token不匹配原DB。P1，交Claude修正，證據 `codex-review-reverify/DB_CREDENTIAL_RESULT.md`、`credential-collision.json`。
- 全程隔離資料；正式runtime開啟嘗試0，不讀取或輪替正式Token，未改核心。未驗證容器是否含最新修正。
- 本輪兩項複驗結束即停止；下一責任人Claude處理憑證路徑碰撞，之後再安排複驗。其他LLM缺陷與GUI仍未結案。

## 2026-10-20 Claude 接續：`init_db()` 同目錄憑證碰撞修復

針對 Codex 上述發現（`app/db.py:169`，同目錄兩個資料庫推導出同一憑證檔名）已修復：改成憑證檔名同時加上 `path` 自己的檔名字根（`{stem}.{預設憑證檔名}`），不再只靠目錄區分。新增測試 `test_second_database_in_same_directory_does_not_collide_with_default`，連同既有測試共 `tests/test_core.py` + `tests/test_db_credentials_isolation.py` **41 passed, 0 failed**；另外直接重跑 Codex 留下的 `ai_progress/codex-review-reverify/test_independent.py` → **10 passed, 0 failed**（原本失敗的同目錄碰撞案例現在通過）。全程只用 `tmp_path` 暫存檔案，正式 `runtime/` 與正式憑證未被讀取或修改。

**仍未處理、不得視為完成**：LLM 虛構工程數值、LLM 虛構核准結論、Podman Desktop GUI 使用者驗收、本次修正的 Codex 第三次獨立複驗。依指示完成後立即停止，不自動展開下一項。

## 2026-10-20 M6：LLM 虛構工程數值來源驗證修復

Codex 故障注入發現：使用者訊息完全沒提到任何數字，模擬 LLM 仍回傳 `motor_voltage=24V`／`motor_continuous_current=1A`，`engineering.convert()` 只檢查單位維度，沒檢查數值來源，導致檢核從 `unknown` 誤判成 `pass`（見 `ai_progress/codex-review-ollama/review_probes.py` 的 `ungrounded_numeric_extraction`）。修復：`app/chat.py` 新增 `_grounded_in_message()`，要求模型宣稱的「數值＋單位」必須逐字出現在使用者自己的訊息文字中才接受，逐欄位獨立檢查（使用者只給一部分時，模型自行補的另一部分仍個別被拒）。正式文件授權值（status=`ok`）與既有 session 延續規則都不受影響。新增 `tests/test_llm_value_grounding.py`（6 項，對應無數值拒絕捏造／正常提供接受／部分提供只接受可驗證部分／合法單位換算／正式文件優先／session 延續不退化），連同既有相關測試共 **59 passed, 0 failed**；全程用 `tmp_path` 隔離資料庫與 mock 的 `call_ollama`，正式 runtime／憑證未被接觸。

**仍未處理、不得視為完成**：LLM 虛構核准結論、Podman Desktop GUI 使用者驗收、`init_db` 修復的 Codex 第三次獨立複驗。依指示完成後立即停止，不自動展開下一項。

## 2026-10-20 M7：LLM 核准與安全結論防護修復

Codex 故障注入發現：確定性檢核回報 `fail`、真實總電流/總功率是 11A/264W，模擬 LLM 仍能宣稱「已確認總電流1A、總功率24W，已核准可以立即執行」，這段文字會直接以 `reply_source:"llm_phrased"` 顯示給使用者（見 `ai_progress/codex-review-ollama/review_probes.py` 的 `unvalidated_prose`）。修復：`app/chat.py` 新增 `_reply_is_trustworthy()`，在顯示 LLM 轉述文字前比對三項可信依據——核准用語需要 `actions` 資料表有真實 `approved` 紀錄、安全/通過用語需要確定性檢核狀態真的是 `pass`、文字裡的電壓/電流/功率數字需要和確定性 `numbers` 完全相符；三者皆用否定詞回看窗避免誤判「尚未核准」之類的否定句。任一項不符就捨棄 LLM 文字，改用確定性模板，`reply_source`／`llm_diagnostic` 如實反映實際路徑。新增 `tests/test_llm_reply_trustworthiness.py`（6 項，對應虛構核准／虛構安全結論／虛構數值皆拒絕、真實核准紀錄可正確顯示、忠實解釋保留、備援來源標記正確），連同既有相關測試共 **69 passed, 0 failed**；測試 D 用既有 `/actions` 端點建立真實核准紀錄，沒有新增或繞過審核流程。全程用 `tmp_path` 隔離資料庫與 mock 的 `call_ollama`，正式 runtime／憑證未被接觸。

**已知限制**：核准比對是「專案內是否存在任一筆已核准紀錄」，不是逐一比對本次對話對應的具體動作；關鍵詞＋數值比對仍可能被更隱晦的措辭或跨句否定繞過，建議交 Codex 下一輪獨立複驗補更多自然語言變化案例。

**仍未處理、不得視為完成**：Podman Desktop GUI 使用者驗收、`init_db` 修復的 Codex 第三次獨立複驗、本輪 M7 修復的 Codex 獨立複驗、全專案完整回歸。依指示完成後立即停止，不自動展開下一項。

## 2026-10-20 M7.1：核准紀錄關聯安全修復

使用者發現 M7 的已知限制：`_approved_action_exists()` 只檢查專案內是否存在任一筆已核准的 action，Action A 核准、討論 Action B 時仍可能被誤判成「已核准」。修復：改為 `_approved_action_for_this_conversation(conn, project, session_id, message)`，要求該 action 同時 (1) 屬於目前這個 session_id 的分析、且 (2) 其 task_id 逐字出現在使用者這一輪訊息裡（沿用 M6 的 grounding 手法比對 `simulated_tasks` 這個固定集合，不採信 LLM 自稱的 action ID）。新增 `tests/test_llm_approval_linkage.py`（6 項）並修正 `test_llm_reply_trustworthiness.py` 的測試 D，連同既有相關測試共 **75 passed, 0 failed**；所有核准都經既有 `/actions`+`/actions/{id}/review` 端點正常建立，manager-only 審核流程未變動。全程 `tmp_path` 隔離，正式 runtime／憑證未被接觸。

**已知限制**：task_id 關聯仍是訊息文字的逐字比對，無法理解同義詞或間接描述。

**仍未處理、不得視為完成**：Podman Desktop GUI 使用者驗收、`init_db` 修復的 Codex 第三次獨立複驗、M7/M7.1 的 Codex 獨立複驗、全專案完整回歸。依指示完成後立即停止，不自動展開下一項。

## 2026-10-20 整合回歸驗收（第一階段）

`pytest -q tests/` → **107 passed, 0 failed**，ACL/Session/init_db/M3 Ollama/M6/M7/M7.1/工程計算與人工審核全部維持通過，沒有發現功能退化。隔離的 `scripts.evaluate` 執行（`AGENT_DB_PATH`/`AGENT_CREDENTIALS_PATH` 指向暫存目錄）確認 45/45（`path_recall`/`path_precision`=1.0，`constraint_correct` 全真）。正式 `runtime/agent.sqlite3`、`demo_credentials.json` 執行前後 SHA256 一致，未被初始化或覆寫。

**從專案根目錄跑不帶路徑的 `pytest -q` 會多收集到一個失敗**：`ai_progress/codex-review-reverify/test_independent.py`（Codex 在 M7 之前留下的一次性複驗腳本，非 `tests/` 正式測試）裡一則固定寫死的模擬回覆文字「11A／264W」用在 `supplier` 焦點（該焦點完全沒有跑工程檢核，沒有任何確定性數字可比對），M7 的 `_reply_is_trustworthy()` 因此正確拒絕——這是 M7 防護生效的預期行為，不是本輪回歸。日後「完整回歸」請明確用 `pytest -q tests/`，不要從根目錄無範圍執行。

**Podman 容器狀態**（本輪僅唯讀檢查，未啟動/重建/重啟）：`riskscope-machine` 目前未啟動，沒有容器在執行。已建置的 `riskscope-poc:0.1` 映像建於 2026-10-19（M4 部署時），本輪及前兩輪修改的 `app/chat.py`（M6/M7/M7.1）、`app/db.py`（init_db 同目錄碰撞修復）都是 2026-10-20 才改的，**目前映像不含這些修復**。下次部署前需要 `podman build` 重新建置；沿用既有 `riskscope_runtime` volume 名稱啟動新容器即可保留既有 runtime 資料，不需刪除或重建這個 volume。

**仍未處理、不得視為完成**：Podman Desktop GUI 使用者驗收、`init_db`／M7／M7.1 的 Codex 獨立複驗、容器重新建置與部署驗收。依指示完成後立即停止，不自行開始部署、獨立審查或新功能開發。

## 2026-10-20 Podman 正式部署準備與新版建置

使用者授權啟動 `riskscope-machine` 做唯讀檢查：原容器已因 `--rm` 隨機器停止自動移除，映像 `riskscope-poc:0.1` 與 volume `riskscope_runtime`（`MountCount:0`，資料完整，`demo_credentials.json` 權限 `0600` 讀取被正確拒絕、沒有洩漏內容）皆未受影響。確認 `app/api.py` 的 `lifespan()` 啟動時呼叫 `init_db()` 不帶參數，剛好落在本輪 init_db 修復**不會改變行為**的既有分支——新版與正式資料庫、憑證 100% 相容，不需任何轉換。非破壞性匯出 volume 備份到 `/tmp/riskscope_backup/riskscope_runtime_20261020_112715.tar`（已驗證完整）。用現有原始碼建置新映像 `localhost/riskscope-poc:0.2`（保留 `0.1`），程式層級確認四項修復（M6/M7/M7.1/init_db 碰撞修復）都在新映像內；用拋棄式 volume 做隔離啟動測試，`/`、`/openapi.json` 皆 200，正常啟動。全程未掛載、未接觸正式 `riskscope_runtime`，只清除了自己建立的拋棄式容器與 volume。

**下一步（需使用者另行授權）**：把 `riskscope-poc:0.2` 正式掛載 `riskscope_runtime` 並切換服務。

**仍未處理、不得視為完成**：正式切換新容器、Podman Desktop GUI 使用者驗收、`init_db`／M7／M7.1 的 Codex 獨立複驗。依指示完成新版建置後立即停止，等待使用者授權正式切換。

## 2026-10-20 RiskScope 0.2 正式部署與啟動驗收（使用者已授權切換）

已正式切換：容器 `riskscope`（`--rm -d`，`localhost/riskscope-poc:0.2`，掛載正式 `riskscope_runtime:/app/runtime`，`127.0.0.1:8000`）正常啟動。備份已複製到持久位置 `ai_progress/backups/riskscope_runtime_20261020_112715.tar`（權限 `600`，完整性已驗證）。功能驗證：登入（manager/engineer 皆 200）、既有任務狀態、既有已核准 action、既有稽核紀錄全部讀取正常且與 M4 時期資料一致；啟動前後 `agent.sqlite3` SHA256 不變。對實際運行程序 `podman exec` 確認 M6/M7/M7.1/init_db 四項修復全部存在於運行中的容器，不只是映像檔案。

**使用者可開啟** `http://127.0.0.1:8000` 自行操作驗收。

**容器啟停方式**：停止 `podman stop riskscope`（因為是 `--rm`，停止會自動移除容器本身，但資料留在 `riskscope_runtime` volume，不會遺失）；重新啟動用上面同一條 `podman run ...localhost/riskscope-poc:0.2` 指令即可。

> **⚠️ 本節記錄的是當時實際採用的做法，`--rm` 後來（M12.1/M12.2）被查明是「podman machine 停止/重啟後容器被自動移除」的根因**。下次正式部署（0.4 或之後版本）請改用本檔案最後「容器生命週期與部署建議（M12.3）」一節的做法；本節原文保留不動，只做歷史對照。

**仍未處理、不得視為完成**：Podman Desktop GUI 使用者視覺驗收、`init_db`／M7／M7.1 的 Codex 獨立複驗。本輪完成啟動驗證後停止，等待使用者親自操作。

## 2026-10-20 M8：動態工程決策分析修復（分兩階段，含 Session 409 續接修復）

兩個根因：(1) `app/engineering.py` 的 `power_continuous()` 原本永遠不讓使用者數值覆寫已授權（`ok`）的文件事實，不論使用者多明確地提出新方案；(2) `app/analyzer.py` 的 `_open_session()` 一旦本輪分析沒有未知項就把 session 關閉，之後同一 session 任何追問一律 409——這是「連續追問也無法修正」的真正原因（Codex 獨立複驗確認）。

修復 1：`app/chat.py` 新增 `_change_intent_mode()`，只在使用者文字明確出現「換成/更換/替換/改用」（replace）或「新增/額外/再加」（add）等語句時才允許覆寫；`app/engineering.py` 支援 `mode='replace'`/`'add'`，覆寫結果標記 `proposed_change`（不寫入 `facts`），並附上 `baseline`（純文件版結果）供前後對照。修復 2：`_open_session()` 新增 `user_supplied` 參數，只有「狀態已關閉且這次完全沒有提出任何新數值」才 409；只要帶有新數值（只會透過 `/chat`），即可在同一 session 繼續評估新方案。單純重複問同一句話仍然 409（不影響 `tests/test_session_continuity.py` 既有的劫持/關閉測試）。

新增 `tests/test_m8_scenario_planning.py`（8 項），`pytest -q tests/` → **115 passed, 0 failed**（107 既有 + 8 新）。正式 runtime SHA256 執行前後一致。

**Codex 另外發現、本輪刻意不處理**：(1) 同句「替換＋新增」可能混淆操作模式；(2) 原負載完全缺漏時，「新增」語句目前等同直接提供該值（因為沒有基準可疊加），語意上可能需要額外提示使用者先補基準值。留待下一輪評估。

**仍未處理、不得視為完成**：Podman Desktop GUI 使用者視覺驗收、`init_db`／M7／M7.1／M8 的 Codex 獨立複驗、45 項評估重新執行。依指示完成後立即停止，不自行開始下一項。

## 2026-10-20 M8 最後一輪：完成真正的多輪決策對話

修復前輪保留的三個問題：(1) `app/analyzer.py` 新增 `_is_repeat_question()`——改成「狀態已關閉且沒有新數值且問題文字與本 session 內任何一次問過的完全相同」才 409；只要問題文字不是逐字重複，即使完全沒提供新數值也視為有效追問，可以繼續要求解釋風險、比較方案、質疑建議、詢問缺少資料。(2) `app/chat.py` 的 `_change_intent_mode()` 改成比較每個數字最近的意圖關鍵字（取距離最短者），修正同句「替換＋新增」時所有數字都被誤判成同一種模式的問題。(3) `app/engineering.py` 的 `power_continuous()`：原負載缺漏/過期/未授權時遇到「新增」語句，不再把新增量當成系統全部總量，該事實狀態維持原樣（檢核仍回報 `unknown`），新增量另外記錄在 `result['pending_additions']`，回覆明確要求補充基準、不虛構。

新增 `tests/test_m8_scenario_planning.py` 3 項（i/j/k），共 11 項；`pytest -q tests/` → **118 passed, 0 failed**（115 既有 + 3 新）。`sessions` 資料表結構完全未變，未修改或刪除任何既有測試，`tests/test_session_continuity.py` 的劫持/關閉測試照常通過。正式 runtime SHA256 執行前後一致。

**仍未處理、不得視為完成**：Podman Desktop GUI 使用者視覺驗收、`init_db`／M7／M7.1／M8 的 Codex 獨立複驗、45 項評估重新執行。依指示完成後立即停止，不自行開始下一項。

## 2026-10-20 M9/M9.1：Qwen3.6 27B 隔離實測與回覆逾時修復

M9（純評估，無程式變更）：隔離環境測得 27B 數值抽取準確快速（3-4秒），M6/M8 防護正常，但 `_llm_reply()` 固定45秒逾時對27B（典型回覆需約61秒）不足，三次測試全數逾時退回確定性模板；`think:true` 對小提示120秒內未完成，確認必須維持 `think:false`。

M9.1（修復）：`app/config.py` 新增 `reply_timeout_seconds()`——環境變數 `OLLAMA_REPLY_TIMEOUT_SECONDS` 優先，否則查 `REPLY_TIMEOUT_DEFAULTS_BY_MODEL`（8B=45秒不變、27B=120秒，其他模型維持45秒不猜測）；`app/chat.py` 的 `_llm_reply()` 改用這個函式而非寫死45。確認 uvicorn／compose／前端 fetch 都沒有會提早中斷的其他逾時機制。新增 `tests/test_m9_reply_timeout.py`（7項），`pytest -q tests/` → **125 passed, 0 failed**。真實27B驗證（唯一一次）：透過完整 `/chat` 流程，77.07秒完成（抽取9.88秒＋回覆66.96秒），`reply_source:"llm_phrased"`，未被 M7 降級，確認通過可信度檢查。8B既有45秒行為、M6/M7/M7.1/M8邏輯、正式 runtime 與 Podman 0.2 全部未變動。

**仍未處理、不得視為完成**：Podman Desktop GUI 使用者視覺驗收、`init_db`／M7／M7.1／M8／M9.1 的 Codex 獨立複驗、45 項評估重新執行、是否正式切換 27B 為預設模型。依指示完成後立即停止，不自行開始下一項。

## 2026-10-20 M10：新版 Podman 建置與隔離驗收

建置 `localhost/riskscope-poc:0.3`（保留 0.1/0.2），程式層級確認 M6/M7/M7.1/M8/M9.1/init_db 修復全部存在。用拋棄式 volume（非正式 `riskscope_runtime`）啟動隔離容器，`OLLAMA_MODEL=qwen3.6:27b`：首頁/健康檢查/API 皆 200；容器內確認 `reply_timeout_seconds()`=120、`local_ollama_url()` 正確連到宿主機 Ollama。快速測試 36 項全過（M6/M7/M7.1/M8/M9.1 相關，不重跑全部 125 項）。唯一一輪真實 27B 完整對話（含追問）：第一輪替換馬達＋修正供電容量，48.8秒完成，`reply_source:"llm_phrased"`，正確算出14A/336W並保留11A/264W baseline對照；第二輪同一已關閉session、無新數字的追問，回傳200（非409，確認M8 session延續修復在容器內同樣生效）。

**資料保護**：全程只用拋棄式volume，正式`riskscope_runtime`（MountCount始終0）與正式容器（持續運作未重啟）皆未受影響；專案目前不是git repo，先前備份的`ai_progress/backups/*.tar`（含正式DB與憑證）無進版控風險，權限鎖600；本輪未輸出任何憑證內容。

**下一步（需使用者另行授權）**：把`riskscope-poc:0.3`＋27B正式掛載`riskscope_runtime`並切換服務。

**仍未處理、不得視為完成**：Podman Desktop GUI使用者視覺驗收、`init_db`／M7／M7.1／M8／M9.1／M10的Codex獨立複驗、45項評估重新執行。依指示完成後立即停止，等待使用者授權正式切換。

## 2026-10-20 M11.2/M11.3：真實瀏覽器端到端驗收

用 Node Playwright 驅動 Mac 既有 Chrome（`/tmp/riskscope_pw_test/`，專案外，未下載瀏覽器引擎），在隔離測試站 `127.0.0.1:8001`（0.3＋27B＋拋棄式 volume）跑完整 GUI 流程（登入→對話→追問→新對話），正式 `127.0.0.1:8000`（0.2＋8B）全程未受影響。

**發現的重要問題**：(1) 案例A「實際可用8A」這個數值27B抽取失敗（抽到名目10A），只算出40%超載，漏掉75%那組對照；(2) 案例C「改用9A馬達」修正完全沒生效，27B沒抽到9A候選值，`reply_source`降級成確定性模板（M7正確攔下）；(3) 案例D/E因測試忘記切換「評估情境」下拉選單，暴露產品沒有自動判斷訊息內容對應情境、也沒偵測無關輸入的機制——案例E使用者問咖啡，Agent照樣回電源風險分析（已截圖佐證）；(4) UI小瑕疵：新對話後側欄session_id文字不同步、版本徽章永遠顯示靜態「PoC v0.1」看不出實際後端版本。

5次真實27B呼叫全部在120秒內完成（37-72秒），無逾時、無卡住、無409。截圖存於`/tmp/riskscope_pw_test/screenshots/`。驗收後已清除隔離容器/volume/暫存憑證，正式runtime SHA256不變。

**仍未處理、不得視為完成**：Podman Desktop GUI使用者視覺驗收、`init_db`／M7／M7.1／M8／M9.1／M10／M11的Codex獨立複驗、45項評估重新執行、是否正式切換0.3＋27B。依指示完成後立即停止，交由使用者決定下一步。

## 2026-10-20 M11.4：修復新條件未生效問題（Claude起頭→Codex接力→Claude收尾）

根因：案例A/C的失敗都在LLM抽取步驟本身（直接對真實27B重現確認，不是grounding/session/engineering/M7的問題）——原本抽取prompt只給變數英文名，沒有中文語意，「電源實際持續可用容量」跟`supply_continuous_current`毫無字面關聯，導致抽取不穩定。

修復：`app/engineering.py`新增`USER_SUPPLIABLE_KEY_DESCRIPTIONS`（中文欄位語意，非寫死數值）；`app/chat.py`新增`_explicit_change_requests()`（純確定性文字解析，推導使用者原文明確提出的欄位+數值+變更模式，正確處理舊值在前新值在後的語序與否定句）、`_unclaimed_change_intents()`（比對明確變更意圖與實際採用欄位）、`_change_warning()`（固定提示文字，在M7驗證後強制接在LLM回覆最前面，不依賴LLM自己記得提）。另加防護：同session內純複述不會洗掉先前已確立的方案。

驗證：`pytest -q tests/` → **145 passed, 0 failed**；M6/M7/M7.1/M7.2/ACL/Session/M8/core共83 passed確認Codex的修改沒破壞既有防護。真實GUI複驗（沿用`/tmp/riskscope_pw_test/`，複用Codex留下的隔離容器、SHA256核對程式碼一致）：案例A算出14A/336W/超40%/超75%，案例C算出12A/288W/超20%/超50%，**與驗收標準完全一致**，皆`reply_source:llm_phrased`，透過DOM文字直接驗證。已清除Codex留下的隔離容器與volume，正式0.2容器與runtime全程未受影響。

**仍未處理、不得視為完成**：D/E跨領域情境判斷、UI小問題、Podman Desktop GUI驗收、各輪Codex獨立複驗、45項評估重新執行、是否正式切換0.3＋27B。依指示完成後立即停止，等待使用者確認。

## 2026-10-20 M11.5：跨領域決策能力驗收（純檢查+驗收+規劃，無程式變更）

架構檢查確認：10個「評估情境」中，只有`motor_upgrade`/`power`有真正的確定性工程規則（`power_continuous()`）；其餘8個情境（含`supplier`）的`checks`/`options`/`facts`永遠是空的，`synthesis_step()`無條件附加「本焦點沒有預先驗證的確定性工程規則」，session永遠停在open——這些情境唯一真正運作的是文件檢索與依賴圖追蹤（真實、可用），完全沒有決策綜合邏輯。資料庫其實已有`project_signals`（供應商交期、測試結果）可用，但從未被讀取。

真實GUI複驗（新建隔離映像`riskscope-m115-test`，確認含M11.4修復、獨立volume，正式0.2+8B全程未受影響）：案例D（正確選「供應商交期」情境）——系統誠實回報能力邊界、引用真實依賴鏈（SUPPLIER-01→PROCURE-01/ASSEMBLY-01/RELEASE-01/TEST-01），**沒有虛構**任何供應商風險數字；案例E（情境維持預設motor_upgrade，問咖啡）——確定性引擎仍無條件跑馬達分析，無視問題內容。兩者原因不同：D是「架構沒有該領域的決策邏輯」（誠實但無用），E是「沒有情境防呆＋motor/power情境無條件執行」（會誤導）。

**目前真正支援的決策領域**：嚴格意義的決策支援只有馬達/電源連續功率一項；其餘情境只有檢索+依賴追蹤兩個可重用的通用基礎設施。

**最小可行改善方案**（規劃，未實作，詳見`00_STATUS.md`第32節）：1.情境選擇防呆（最小最安全）2.串接既有`project_signals`進supplier等情境的synthesis_step 3.把方案比較框架從馬達專屬擴大成`FOCUS_OPTIONS` 4.把M8的「新資訊確定性比較」機制從工程數值延伸到`project_signals`（風險/工作量最大，建議放最後）。

**仍未處理、不得視為完成**：以上四項改善方案均未實作；Podman Desktop GUI驗收、各輪Codex獨立複驗、45項評估重新執行、是否正式切換0.3＋27B。依指示完成後立即停止，等待使用者確認是否進入實作。

## 2026-10-20 M12：通用跨領域決策分析引擎 MVP（實作＋真實GUI驗收）

M7是否擋住定性分析的結論：不需要關閉或放寬，`_reply_is_trustworthy()`原本就只檢查核准/安全宣稱與V/A/W工程數值，從未限制一般敘述。真正缺口是系統從未對任何情境計算過工期/成本/機率，卻也從未檢查LLM是否捏造這類數字——修法是擴大同一套「可驗證事實vs禁止宣稱」邏輯：新增`_SCHEDULE_COST_RE`（天/週/月/工作日/萬元/元等，一律拒絕，因為任何情境都沒有可信來源）與`_PERCENT_RE`+`_trusted_percentages()`（只信任M8既有baseline比對算出的那個百分比，例如馬達案例真實的40%/75%，其他一律拒絕）。

實作：`app/analyzer.py`新增`_generic_decision_support()`（非馬達/電源情境統一的通用骨架：facts來自真實`project_signals`、3個一律`unverified`的通用方案G-A/B/C、固定風險`R-UNVALIDATED-ANALYSIS`、追問清單——程式碼本身不出現任何領域名稱）、`_read_project_signals()`（首次把資料庫既有的`supplier_lead_days`/`test_pass`接進分析結果）、`FOCUS_KEYWORDS`/`FOCUS_LABELS`、`decision_structure`（Decision Context/Evidence/Known-Unknown/Options/Consequences/Risk Comparison/Next Actions七鍵，重用既有欄位，下個新領域免費套用）。`app/chat.py`新增`_focus_mismatch_warning()`（純關鍵字比對，不呼叫LLM、不自動切換情境，只加確定性提醒文字）。修正`_deterministic_reply()`一個實作中發現的問題：原本session=open一律提早return、永遠看不到新加的options/risks——修正為只有「有確定性工程check」時才維持原行為，其餘情況接著顯示並標明「尚待驗證的假設」。

測試：新增`tests/test_m12_generic_decision.py`（11項），修正`tests/test_core.py`一項既有測試（原斷言`options==[]`，改為斷言3個方案皆`unverified`，反映本輪刻意變更）。全套`pytest -q`→**156 passed, 0 failed**；`scripts.evaluate`仍45/45；`pip check`乾淨。

真實GUI驗收（隔離映像`riskscope-m12-test`，先`hasattr`確認含本輪新函式、throwaway volume、port 8003、qwen3:8b、重用既有Playwright+Chrome）：SUPPLIER案例（Phase3指定情境文字，選`supplier`情境）——`reply_source`為LLM轉述，回覆真實列出已知/未知project_signals、3個方案皆明確標「尚待驗證的假設」、依賴鏈風險、免責聲明，全文無任何天數/金額/機率數字；MISMATCH案例（情境維持預設`motor_upgrade`，問咖啡）——回覆最前面出現情境不符提醒，其後才是已加註警示的馬達計算（不再是靜默誤導）。驗收後已清除隔離容器/volume/測試映像，正式0.2容器（image/volume CreatedAt/`agent.sqlite3`與`demo_credentials.json`的SHA256）全程確認未變。

**仍是領域專屬、未做**：情境特定的確定性數值規則仍只有馬達/電源一項；`project_signals`的「使用者對話中提出新數值→確定性比較→修正未套用要明說」機制（原M11.5規劃第4項）尚未延伸過去。下一個新領域（例如真正的supplier專屬規則）可以直接套用本輪的`decision_structure`/`_generic_decision_support`骨架，只需新增該領域專屬的確定性規則本身。

**仍未處理、不得視為完成**：Podman Desktop GUI使用者視覺驗收、各輪Codex獨立複驗、45項評估重新執行、是否正式切換0.3＋27B、`project_signals`的對話式更新機制。依指示完成後立即停止，等待使用者確認下一步。


## 2026-10-20 Codex M12 獨立審查（完成，未改產品）

- 49 項必要隔離測試僅執行一次：35 passed／14 failed；其中既有 M12／M11.4／ACL／Session 共 33/33 通過，新增驗收探針 2 通過／14 失敗。不是全套回歸結果。
- 未發現新 P0 越權或自動核准證據。確認 P1：數字格式繞過、百分比用途及精度錯誤、定性假事實放行、可信 7 天被拒、決策問題／限制未進回覆模型且方案固定、非工程多輪更新未採納也未明說。P2：情境錯配仍計算，以及 Signals 來源狀態不足。
- Signals 現行為專案成員公開資料；文件撤權不等於 Signal 撤權。專案隔離、撤銷成員資格、文件／歷史遮蔽控制通過，不能宣稱支援單筆機密 Signals ACL。
- 產品與既有測試雜湊前後一致；未存取正式 runtime／Token／Volume，未操作 Podman，未呼叫模型或啟動其他 Agent。磁碟 M12 GUI 紀錄為 qwen3:8b，27B 未由本輪驗證。
- 報告與可直接複驗的證據：`ai_progress/codex-review-m12/REVIEW.md`、`review_probes.py`、`observations.json`、`test-results.txt`、`results.xml`、`isolation.json`。原始探針執行後僅從 `test_review.py` 改名，避免一般 pytest 自動收集。
- 建議 Claude 下一輪依使用者授權先修可信度／來源契約及明確未採納提示，再補決策脈絡與有條件方案；不關閉 M6/M7/M7.1，不直接寫入正式 Signals，不先增加其他領域。Codex 本輪結束，不啟動後續工作。


## 2026-10-21 Claude 修復 Codex M12 獨立審查發現的問題

Codex 審查（`ai_progress/codex-review-m12/REVIEW.md`）找到 8 項問題（M12-01～08），交接前確認磁碟雜湊與審查時一致。已修復 M12-01～07（數字/百分比格式繞過與精度錯誤、定性假事實可被講成已確認、可信7天被誤拒、決策問題/限制未進回覆模型且方案固定、非工程多輪新條件被忽略不明說、情境不符仍執行分析）；M12-08（Signals 來源/狀態 metadata）為資料模型擴充非信任漏洞，留待下一輪。

實作時發現並修正了自己的一個新 bug：第一版 `suppress_synthesis` 用「情境關鍵字缺席」判斷過寬，誤攔多個正常追問（已改用高精確度 `_OFF_TOPIC_RE` 閒聊偵測）。

測試：`pytest -q tests/` → 159 passed；Codex 探針 `review_probes.py` → 15/16 passed（唯一「失敗」是刻意行為升級，非回歸，已記錄不修改 Codex 探針檔案）；`scripts.evaluate` 45/45；`pip check` 乾淨。

**仍未處理**：M12-08 資料來源metadata；`/analyze(use_local_llm=true)` 的 `_safe_local_explanation()` 路徑未套用 M7 等級信任檢查（已知限制，未故障注入確認）；project_signals 對話式正式寫入機制；本輪未啟動 Podman，未做真實27B/瀏覽器複驗。依指示完成後停止，等待使用者確認下一步。

## 2026-10-21 M12.1：安全缺口收尾、剩餘探針核對、真實GUI驗收

剩餘探針（Codex review_probes.py 15/16）確認是 M12-05 刻意行為升級非回歸，已用新測試固定正確行為，未改 Codex 探針檔案。真實GUI驗收又發現並修復一個新問題：情境不符暫停分析時，依賴影響風險（R-IMPACT-*）仍會洩漏到回覆中（trace_impact 本身仍執行，只是不該折入使用者看到的 risks/inferences）——已修復並重新真實GUI確認。供應商決策情境（案例ABC合併一輪）真實27B驗收通過：已知/未知訊號、限制衝突標記、無捏造數字皆正確。

**重要但非本輪造成的發現**：正式容器 `riskscope` 目前未在執行（podman ps -a 空），`riskscope_runtime` volume 資料完整（SHA256 比對一致），推測主機/VM睡眠或重啟所致。**未自行重啟正式容器**，交由使用者決定。

`pytest -q tests/` → 160 passed；Codex探針 15/16（已確認非回歸）；evaluate 45/45；pip check乾淨。Codex 的 `/analyze(use_local_llm=true)` 獨立複驗尚未收到結果，未宣稱該路徑已驗證。依指示完成後停止，等待使用者確認下一步。

## 2026-10-21 M12.2：修復 /analyze 安全缺口、正式容器消失調查（唯讀）

Codex 確認 `/analyze(use_local_llm=true)` 的 P1 缺口：`_safe_local_explanation()` 從未呼叫 M7 可信度驗證。已修復：延遲匯入 `chat._reply_is_trustworthy()`，傳完整 result 驗證，拒絕時不保留原文。Codex 六案例全部修復（review_probes.py 6failed→8passed）；新增 tests/test_analyze_llm_trustworthiness.py 7項。全套 pytest → 167 passed；evaluate 45/45；pip check乾淨。

正式容器消失已查清根因：啟動指令含 `--rm`，podman machine 停止/重啟會讓容器行程結束並被自動移除——這是本專案已發生過一次的既有已知模式（60_NEXT_HANDOFF.md第166行記載2026-10-20同一現象），非本輪或任何操作造成，無自動重啟設定（無launchd/systemd unit）。資料完全完整（riskscope_runtime volume SHA256與全程基準一致）。已知、曾用過的正確恢復指令記錄在60_NEXT_HANDOFF.md第178行（0.2映像），**本輪未執行**，交由使用者決定。

附帶發現：120_M4/140_FINAL_GUIDE及本檔案「## 9」區塊仍殘留舊的0.1版本重啟指令，未更新，本輪未修改這些文件，僅記錄避免誤用。

依指示完成後停止，等待使用者確認：是否執行恢復指令、是否改為部署含M12.1/M12.2修復的新版本。

## 2026-10-21 容器生命週期與部署建議（M12.3，規劃，待使用者授權才執行）

以下是 0.4（或任何未來版本）正式部署時建議採用的做法，取代舊的 `--rm` 啟動方式。**本節只是規劃，本輪未對正式容器/Volume執行任何這裡列出的指令。**

### 1. 不要用 `--rm`，改用 `--restart`

```sh
podman run --name riskscope -d --restart=unless-stopped -p 127.0.0.1:8000:8000 \
  -e OLLAMA_URL=http://host.containers.internal:11434 \
  -e OLLAMA_MODEL=qwen3:8b \
  -v riskscope_runtime:/app/runtime \
  localhost/riskscope-poc:<已授權的版本標籤>
```

`unless-stopped`（而非 `always`）：容器異常結束或 podman machine 重啟後會自動恢復，但使用者主動 `podman stop riskscope` 之後不會被自動重啟回來，行為比較符合預期。

### 2. 已查明：`unless-stopped`/`always` 需要 `podman-restart.service` 才會真正生效

唯讀檢查（`podman machine ssh riskscope-machine systemctl status podman-restart.service`）確認這個 systemd 服務目前是 **disabled**——這代表即使容器加了 `--restart` 旗標，podman machine 重啟後也不會自動把它叫起來，因為沒有東西在開機時執行這個檢查。建議在下次正式部署時，一併啟用這個服務（`podman machine ssh riskscope-machine sudo systemctl enable podman-restart.service`——只啟用一個既有的系統服務，不碰容器或 Volume，風險低）。**本輪僅確認現狀，未執行啟用**。

### 3. Mac 本機重開機後，podman machine VM 本身仍需手動啟動

`--restart` 政策只處理「VM 本身重啟時容器要不要回來」，不處理「Mac 整台重開機後有沒有人去啟動 VM」——目前沒有設定讓 `riskscope-machine` 隨 Mac 開機自動啟動（無對應 LaunchAgent）。這次調查沒有找到任何相關設定。若要做到「Mac 重開機後完全不用手動介入」，需要另外設計並授權一個 macOS LaunchAgent（開機時執行 `podman machine start riskscope-machine`），這是**獨立的新決定**，不在本輪規劃範圍內，僅在此記錄为未來可選項。目前建議維持現狀：文件清楚記載「開機後請先確認 `podman machine list` 顯示 running，沒有的話手動 `podman machine start`」。

### 4. 永遠沿用同一個具名 Volume，不重建

部署指令永遠掛載 `-v riskscope_runtime:/app/runtime`（名稱完全不變）。换版本只換映像標籤，從來不換、不刪、不重建這個 Volume 名稱。

### 5. 部署前備份、驗證、切換、回滾流程（建議，待授權執行）

1. **備份**（唯讀掛載來源，不影響正式容器）：
   ```sh
   podman run --rm -v riskscope_runtime:/data:ro -v <備份目錄>:/backup:z \
     alpine tar czf /backup/riskscope_runtime_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
   ```
   延續既有做法（`ai_progress/backups/riskscope_runtime_20261020_112715.tar`），備份檔權限鎖 `600`。
2. **驗證新映像**：先在隔離環境（拋棄式 volume、非正式連接埠）跑過 `hasattr`/SHA256 原始碼核對、快速測試、必要真實GUI驗收——本輪 0.4 已完成這些步驟。
3. **切換**（因為不用 `--rm`，容器要先明確移除才能用同名字重建）：
   ```sh
   podman stop riskscope
   podman rm riskscope        # 資料在 volume，不受影響
   podman run --name riskscope -d --restart=unless-stopped -p 127.0.0.1:8000:8000 \
     -e OLLAMA_URL=http://host.containers.internal:11434 \
     -e OLLAMA_MODEL=qwen3:8b \
     -v riskscope_runtime:/app/runtime \
     localhost/riskscope-poc:0.4
   ```
4. **切換後立即確認**：`podman exec riskscope sha256sum /app/runtime/agent.sqlite3` 與切換前的雜湊一致（`init_db()` 是既有的 idempotent 設計，對已存在的資料庫只會做新增式的 `ALTER TABLE IF NOT EXISTS`，不會覆寫）；登入、既有 session/action/稽核紀錄讀取正常。
5. **回滾**（若切換後發現問題）：
   ```sh
   podman stop riskscope && podman rm riskscope
   podman run --name riskscope -d --restart=unless-stopped -p 127.0.0.1:8000:8000 \
     -e OLLAMA_URL=http://host.containers.internal:11434 \
     -e OLLAMA_MODEL=qwen3:8b \
     -v riskscope_runtime:/app/runtime \
     localhost/riskscope-poc:0.2
   ```
   沿用同一個 Volume 退回上一個已確認可用的映像標籤（`0.2`）——因為資料庫結構變更一直是新增式、向後相容，退版本不需要還原備份；備份檔只在資料本身（不是程式）出問題時才需要用到。

### 風險與限制

- 以上全部**待使用者另行授權才執行**，本輪僅完成規劃與（第2項的）唯讀狀態確認。
- `--restart=unless-stopped` 無法處理「Mac 整台斷電/重開機後沒人啟動 podman machine」的情況，仍需要人工先確認 `podman machine` 狀態。
- 回滾假設資料庫結構變更一直維持向後相容——若未來某個版本引入破壞性結構變更，必須另外評估，不能直接套用這個回滾流程。

## 2026-10-21 M12.3：0.4映像建置、隔離真實GUI驗收、容器生命週期規劃

建置 `riskscope-poc:0.4`（含M11.4/M12/M12.1/M12.2全部修復，SHA256與本機原始碼逐位元組相符），隔離環境（port 8001、throwaway volume、qwen3.6:27b）真實GUI三案例全過：工程變更(14A/336W/超40%/超75%)、供應商決策(限制衝突正確標記、無捏造數字、非固定模板)、情境不符(暫停分析、無馬達內容洩漏)。安全可信度(案例D)用既有mock/API複驗：Codex八案例8/8、自建7項測試7/7，未消耗額外真實27B。全套pytest 167 passed；evaluate 45/45；pip check乾淨。正式volume/資料庫/憑證SHA256全程比對一致。

容器生命週期規劃已寫入本檔案上方專節：建議棄用`--rm`改`--restart=unless-stopped`；唯讀確認`podman-restart.service`目前disabled（光加`--restart`還不夠，需額外啟用）；已提出備份/驗證/切換/回滾完整指令，**均待授權才執行**。三份文件中殘留的舊版0.1+`--rm`指令已加註過時標記並指向新章節，原文保留。

依指示完成後停止，等待使用者授權：是否啟用podman-restart.service、是否恢復0.2或直接部署0.4、是否執行備份與正式切換流程。

## 2026-10-21 M12.4：正式部署 RiskScope 0.4（使用者已授權，已完成）

**正式服務現狀**：容器 `riskscope`（`localhost/riskscope-poc:0.4`，`--restart=unless-stopped`，無`--rm`，掛載正式 `riskscope_runtime:/app/runtime`，`127.0.0.1:8000`，`OLLAMA_MODEL=qwen3.6:27b`、`OLLAMA_REPLY_TIMEOUT_SECONDS=120`）正常運作。`podman-restart.service` 已啟用（VM重啟後容器會自動恢復）；Mac整機重開機仍需人工 `podman machine start riskscope-machine`（無LaunchAgent，待日後另行授權）。

部署前：新建並驗證可還原的備份 `ai_progress/backups/riskscope_runtime_20261021_143927.tar.gz`；用真實資料的獨立複本（非正式volume）驗證0.4相容性，確認`init_db()`對既有資料走idempotent分支、不重置、不重新產生憑證。部署後：逐筆核對既有4個session/1個已核准action/各類audit次數/users/documents(含DOC-CONF)**全部不變**，僅新增1個明確標示的測試session(`chat-a10176c2`)與對應2筆analyze audit——未發生任何資料毀損、核准繞過或ACL覆寫。

真實GUI驗收（對真實127.0.0.1:8000，engineer帳號）：兩輪27B對話皆`reply_source:本機LLM轉述`（通過M7驗證），算出既有文件基準11A/264W，多輪session正確延續，情境不符提醒正確觸發且未誤判為離題暫停。

回滾：`riskscope-poc:0.2`映像保留，指令已記錄在本檔案上方「容器生命週期與部署建議（M12.3）」一節；本次部署未觸發任何回滾需求。

**正式版本現為 RiskScope 0.4 + Qwen3.6 27B。** 依指示完成後停止，等待使用者實際使用與驗收。

## 2026-10-21 M12.5：修復正式0.4使用者實測發現的工程語意錯誤（已修復，尚未部署）

使用者實測回報：電源名目額定10A、實際可用8A皆為不變常數，只有馬達11A→9A，但Agent反覆宣稱「電源額定由10A改成8A」，糾正也修不掉。數值一直是對的，純敘事錯誤，但有兩個獨立根因（皆在app/chat.py）：(1) `_explicit_change_requests()`對「實際可用」的偵測是整個子句搜尋不分方向，導致「額定一直是10A、實際可用一直是8A」這種子句裡10A和8A都被誤判成電源新數值，產生虛假衝突請求；(2)`_unclaimed_change_intents()`不知道欄位在之前輪次已經確立，把單純重述誤判成「變更沒套用成功」。加上(3) power_continuous()每輪都重算proposed_change evidence，只要mode='replace'還留在session裡就永遠顯示「由10A改成8A」，不管是不是這輪才變的。

修復：新增`_nearest_preceding_gap()`方向性比對（取代整子句搜尋）；`_unclaimed_change_intents`新增`current_state`比對（數值已在生效中就不算未套用）；新增`fresh_change_keys`區分「這輪真的變了」vs「沿用先前」，只有真的變的欄位才用「由X改成Y」敘事，沿用的改用「先前已提供、本輪未變更的條件」敘事，連`_llm_reply()`的prompt與safe_facts也同步區分（不是只改提示詞掩蓋問題）。

第一版修法（子句不繼承前面的電源語境）過度修正，弄壞了4項既有測試（合法的跨子句「電源額定10A，實際持續可用7.5A」案例）——已改用方向性最近描述詞比對解決，恢復語境繼承，4項回歸全修復。新增`tests/test_m125_supply_capacity_semantics.py`(6項)。全套pytest 173 passed；codex兩輪探針15/16+8/8；evaluate 45/45；pip check乾淨。

真實GUI驗收（隔離環境，真實qwen3.6:27b，port 8005，throwaway volume）：使用者原文「電源沒有變，額定一直是10A、實際可用一直是8A，請把馬達改成9A」→ 正確算出12A/288W/20%/50%，回覆正確區分「這輪新方案:motor...改為9A」與「先前已提供、本輪未變更的條件:supply...維持8A」，無錯誤敘事、無假警告。全程只操作隔離容器，正式`riskscope`(0.4,port 8000)持續運作未受影響，驗收後確認正式volume/憑證不變，資料庫內容核對僅成長使用者自己M12.4後的真實使用紀錄(sessions 5→6, analyze audit 7→10)，核准等其他稽核類別筆數不變。

**修改檔案**：僅app/chat.py。**本輪修復尚未部署到正式0.4**（容器仍是M12.4當時的程式碼），等待使用者授權後建置新版映像並部署。依指示完成後停止，等待使用者確認下一步。


## 2026-10-21 Codex M12.5 完成版獨立驗收（未通過全部條件）

只讀完成版磁碟快照驗收：38項，22通過／16失敗；其中Claude新增6項與精選既有安全7項皆通過。16個失敗斷言中有1項僅函式防禦性契約，尚未證明一般API可觸發，不能與已確認流程缺陷混算。
三輪明確替換的數字與重述假警告已改善；但Evidence仍將名目10A／實際8A標為替換，Facts與備援仍稱8A為額定，M7接受錯誤額定變更宣稱；上一輪11A→9A及2A／48W差值未建立。另有等值格式假變更、語序／否定及初始條件未採納缺口。暫不建議批准正式部署準備。
報告與逐項重現：[codex-m125-review/REVIEW.md](codex-m125-review/REVIEW.md)、[TEST_MATRIX.md](codex-m125-review/TEST_MATRIX.md)。完整測試／原始碼雜湊存於該目錄的completed-results、literal-results及completed-manifest.json。早先baseline_source是開發中過渡快照，非正式0.4或完成版，不計入本次結果。
Codex未改產品或既有tests，未操作Podman或正式資料，未呼叫真實LLM。下一步：由使用者決定是否交Claude修復；Codex已停止，不自行進下一階段。


## 2026-11-01 claude-b: M12.5.1 core fix + portable Podman kit (NOT deployed to production)
Code state: app/chat.py, app/analyzer.py, app/engineering.py (Claude A's supply_actual_current split, completed by claude-b). tests 181 passed, evaluate 45/45, portable smoke + demo A/B/C PASS (qwen3:8b, isolated container riskscope-portable:1.0 on :8100). Details, classification of the 2 remaining Codex cases, and honest limits: ai_progress/FINAL_DELIVERY/README.md. Production 0.4 (:8000, riskscope_runtime) untouched; deploy requires user authorization + backup/rollback (see M12.3/M12.4 sections above). Claude A: please review chat.py diff (bare-scenario rule `_is_scenario_declaration`, `_OLD_VALUE_ADJ_RE`, re-keying in `_extract_user_supplied`, `_fresh_change_text`) and run a 27B GUI pass.

## 2026-11-01 Claude A 核心交接審查結論（接受並接手 app/*.py 所有權）

讀取 claude-b 的 FINAL_DELIVERY/README.md 與 ACTIVE_TASK_QUEUE.md 後，逐項獨立重現驗證（非僅採信自述）：pytest 181 passed、evaluate 45/45、Codex原始38項審查套件重跑於目前磁碟程式碼仍是38/40，兩項失敗經我手動重現後確認都是測試假設過時（裸欄位字串斷言、違反LLM抽取唯一入口設計），不是真缺陷；抽查5個claude-b改過的既有測試，修改皆有理由、對應真實資料模型升級，無放寬斷言跡象。詳見00_STATUS.md本日條目。

新增修復：`app/config.py` `local_ollama_url()` 允許清單加入`host.docker.internal`（Antigravity P0跨平台發現），兩組新測試鎖定邊界，全套回歸通過。

**核心程式所有權自本日起正式由 Claude A 接手**（app/chat.py、app/analyzer.py、app/engineering.py、app/config.py）。@claude-b：核心已審查通過，請基於目前磁碟程式碼（含本輪config.py修復）重建隔離Podman測試映像，依ACTIVE_TASK_QUEUE #6/#10執行qwen3.6:27b的kit內驗收與demo A/B/C。

**尚未完成**：M12.5.1完整架構修復的真實Qwen3.6 27B隔離GUI驗收（先前27B驗收是M12.5版本的程式碼，不含本輪的欄位分離架構）——下一步由claude-b用kit跑，或由Claude A另開隔離環境驗收。Windows/原生Linux AMD64仍未實測。正式0.4（port 8000, riskscope_runtime）全程未受影響，部署仍待使用者授權。


## 2026-11-01 claude-b → Claude A（核心已歸你；以下是你審查之後我又做的 3 個核心改動，請一併審）
1. `_ANCHORED_PERCENT_RE`（chat.py）：允許「超出/超過」與數字間有白名單橋接字（名目額定/實際可用容量/約…），因 27B 真實回覆「超出名目額定約 40%」被 M7 誤拒（fail-closed 退回確定性文字）；仍要求數值與引擎計算值完全相等，「延誤機率為40%」「超出預期的延誤機率為40%」「約33%」仍拒絕（tests/test_m1251_plan_tracking.py 新增 5 例）。
2. engineering.py：`mode='replace'` 且數值與文件值實質相同 → 不當作變更（避免「輔助負載 由3A換成3A」）；chat.py `_unclaimed_change_intents` 對應視為已套用。
3. 證據：FINAL_DELIVERY/evidence/（pytest 194 passed；demo A/B/C 在 kit 容器內以 qwen3:8b 與 **qwen3.6:27b** 皆 PASS，27B 三次回覆皆通過 M7）。27B 驗收容器已用受保護 purge 清除。
Podman kit 已用你最新的 config.py 重建，smoke PASS。我不再改 app/*.py。

## 2026-11-01 Claude A 核心版本正式定稿（第二輪，審查CLAUDE_CORE_HANDOFF.md之後）

讀取claude-b的`ai_progress/CLAUDE_CORE_HANDOFF.md`，逐項覆核15:46後的核心修改（scenario_spec分支、old-value wording、re-keying、M7百分比橋接白名單、no-op replace）與6項既有測試預期修改——全部有正當理由，無不合理放寬。詳見00_STATUS.md本日第二則條目。

**發現並修復claude-b交接文件裡的2個疏漏**：(1) claude-b自己的「泛化測試」從未真正參數化名目額定（mock永遠不回傳新的`supply_continuous_current`），已補上`test_genuine_nameplate_replacement_is_not_hardcoded_to_10`；(2) claude-b聲稱`__previous_numbers__`sentinel「沒有被任何API外洩」是誤判——`GET /sessions/{id}`的`dict(row)`其實會把整個含sentinel的原始JSON字串直接回傳，已在`app/api.py`的`session_detail()`修復（移除sentinel後再序列化，不改schema）並補測試。

**核心程式版本正式定稿**：app/chat.py、app/engineering.py、app/analyzer.py、app/config.py、app/api.py。最終回歸：pytest 198 passed、evaluate 45/45、Codex原始38項審查套件重跑38/40（2項測試假設問題，非缺陷，已獨立複驗）、pip check乾淨。

@claude-b：請基於目前磁碟程式碼重建最終Podman測試映像並執行期末驗收（教師手冊、Windows/Linux腳本整理、最終demo證據）。這輪只有測試覆蓋與一個API回應清理上的修正，不影響已經跑過的demo A/B/C結果語意，但建議重建映像以涵蓋最新程式碼。正式riskscope(0.4,port 8000)全程未受影響，部署仍待使用者授權。
