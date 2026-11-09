# RiskScope v0.1 P0 應用驗證紀錄

日期：2026-10-18（Asia/Taipei）。執行者：Codex。

結論：已在本機重現全部 37 項既有測試、LangGraph 真正執行及 12 個固定合成評估案例；另外重現兩項既有測試未涵蓋的 ACL 缺口。P0 不可宣稱全面通過，兩項缺口尚未修正、尚待 Claude 獨立複核；Podman 部署另由 Claude／Antigravity 回報環境缺少容器工具。

## 1. 範圍與來源

- 共用實體路徑：`/Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent`。
- ZIP：`/Users/haochenglin/Downloads/RiskScope_CrossDomain_Agent_PoC_v0.1.zip`。
- ZIP SHA-256：`d283346f7c4c219217aa5641aec3e9874980988a85b0f2ba036f00ba4d89408f`。
- 已閱讀 README、ARCHITECTURE_AND_HANDOFF、VALIDATION_SUMMARY、完整 Word 工程交接文字、原始企劃書文字，以及核心 Python 模組、測試、前端 JavaScript、容器設定。Word 以 macOS textutil 取得內容，未做文件版面驗收。
- `shasum -a 256 -c FILE_SHA256SUMS.txt`：35 筆全部 OK，exit 0。產品程式碼與既有測試未修改。
- 僅新增本報告及 `ai_progress/codex-p0/` 的重現腳本、JSON 與紀錄；未修改其他 AI 的進度檔案。
- 驗證使用獨立臨時合成 SQLite 資料庫；未讀出／上傳正式 runtime 憑證，未呼叫 LLM 或付費 API。

## 2. 實測環境與結果

| 項目 | 專案固定版本環境 | 原本既有環境（補充相容性檢查） |
|---|---|---|
| Python | 3.12.15 | 3.12.15 |
| FastAPI | 0.128.2 | 0.143.3 |
| Pydantic | 2.13.5 | 2.14.1 |
| Uvicorn | 0.48.0 | 0.54.0 |
| HTTPX | 0.28.1 | 0.28.1 |
| pytest | 9.0.2 | 9.1.1 |
| LangGraph | 1.0.0 | 1.2.16 |
| 既有測試 | 37 passed, 2 warnings, 0.43s | 37 passed, 0.77s |
| `pip check` | No broken requirements found | 未執行 |
| 真正分析工作流 | `orchestration=langgraph` | `orchestration=langgraph` |

兩個環境均確認：分析 API 回傳 HTTP 200；指定工況為 11 A／264 W；方案 A 為 blocked；決策狀態為 requires_human_review；LLM 關閉；資料庫保存的工具順序為 get_context、check_constraints、trace_impact、trace_impact。臨時憑證檔權限為 0600。

固定 12 案：直接依賴 11/45，召回率 24.44%；多層路徑 45/45，召回率與精確率均 100%。這是合成圖遍歷結果，不是 LLM 或真實企業推理評分。

固定環境兩條警告為 Starlette 使用 AnyIO 的棄用別名，以及 LangChain serializer 的未來預設值變更；未造成測試失敗。

Claude 另在聊天室回報安裝 LangGraph 前的 fallback 37/37 與 Uvicorn 真實 HTTP 分析驗證。Codex 的獨立驗證確認了固定環境與 LangGraph 路徑；本報告不將未親自執行的 fallback／實體網頁流程列為 Codex 實測。

## 3. 發現 A：撤權後仍可讀到未列入檢索片段的工具證據

位置：`app/api.py:134` 的 `_analysis_access`，尤其第 140 行只遍歷 `result.documents`；`app/analyzer.py:64` 將檢索限制為 8 筆，但工具證據有自己的來源。

重現方式：在臨時資料庫加入 8 份合法授權的合成文件，讓查詢 `targettopic` 的前 8 筆全是這些文件；工程師執行 motor_upgrade 分析，工具仍讀取 DOC-PS、DOC-MOTOR、DOC-AUX。管理者撤銷工程師的 DOC-PS 權限後，新 `/check` 正確回 unknown，但舊 `/analyses/{id}` 仍 HTTP 200 並回傳 DOC-PS 的工具證據。

預期：撤權後，舊分析應拒絕讀取，或完整移除所有依賴該來源的內容。這個案例需要額外合成文件觸發 top-8 邊界，並非聲稱原本六份 seed 文件的既有測試會失敗。

建議：統一收集並保存分析的所有來源依賴（文件、規格 evidence、影響路徑 evidence），在詳細資料與列表的讀取邊界驗證全部來源。只補查 `documents` 或僅查使用者角色不足。新增回歸案例涵蓋來源未出現在 top-8 的情況。

## 4. 發現 B：內部提醒繞過來源 ACL，暴露依賴衍生節點

位置：`app/events.py:69` 把建立者可見的影響節點寫入提醒；`app/api.py:208` 的 alerts endpoint 只檢查專案角色，回傳整個專案提醒。

重現方式：管理者撤銷工程師的 DOC-SUPPLIER 與 DOC-PLAN 權限；工程師查 `/impact/SUPPLIER-01` 得到空清單。管理者送出供應商交期 7 → 18 的合成事件後，工程師仍可從 `/alerts` 讀到 ASSEMBLY-01、PROCURE-01、RELEASE-01、TEST-01。

該提醒缺口依賴的是既有 seed 文件與 API；重現不需要新增文件。驗證腳本在同一個臨時資料庫接著測試，但前一案例新增的 distractor 不影響這些依賴關係。

預期：受保護來源推導出的節點應在提醒讀取時遵守目前讀者的 ACL，包含建立提醒後才撤權的情況。

建議：為提醒保存來源依賴，讀取時做授權檢查與必要的隱藏／拒絕。若短期採 manager-only 邊界，須由團隊明確決定產品權限政策；不能把所有工程師應見提醒無意間一律移除。應加入「管理者建提醒，工程師無來源權限」與「建立後撤權」回歸測試。

## 5. 可查核命令與證據

在共用專案根目錄執行：

```sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -B ai_progress/codex-p0/verify_application.py /tmp/riskscope-independent-review
shasum -a 256 -c FILE_SHA256SUMS.txt
```

重現腳本預設僅將紀錄寫入指定輸出目錄，業務資料使用 TemporaryDirectory；參數可指定各審查者自己的結果位置，避免覆寫 Codex 紀錄。腳本 exit 0 表示執行完畢，**不表示 ACL 通過**：請查看 JSON 的 `finding_reproduced`。本次兩項均為 true。

主要證據：

- `codex-p0/environment.json`、`pytest-existing-env.log`：既有環境與測試結果。
- `codex-p0/application-probes.json`、`evaluation-existing-env.json`：LangGraph 1.2.16 的應用與評估。
- `codex-p0/pinned/environment.json`、`pip-check.log`、`pytest.log`：專案指定環境與 37 測試。
- `codex-p0/pinned/application-probes.json`、`application-probes.log`、`evaluation.json`：LangGraph 1.0.0 的相同結果。
- `codex-p0/source-integrity.log`：35 個既有檔案雜湊核對。
- `codex-p0/verify_application.py`：重現腳本。

## 6. 交叉檢查、未完成項目與下一位

Codex 已閱讀 Claude 的固定依賴／LangGraph 回報並獨立重跑，結果一致。尚未收到 Claude 對上述兩項 ACL 缺口的獨立複核，不能宣稱已交叉驗收。

2026-10-18 實際發送的頻道交接事件 `45cc3a9b-1b58-41d5-b6c2-40a01b6bd21b` 以 `@claude` 開頭；POST 結果及後續歷史查詢都顯示 `metadata.target_agents=["__no_response__"]`。Antigravity 給 Copilot 的交接事件也有相同標記。這支持「平台未將這些 AI 提及派送」的觀察，但尚未定位原因；不應把尚未接到任務誤稱為拒絕配合，也不能宣稱派送機制已修復。

下一步負責人：Claude 獨立複核兩項缺口；Copilot 整合證據並安排修正與再次交叉驗收。本階段僅驗證，尚無產品修正。

P0 尚未完成：兩項 ACL 問題複核及修正；Mac Podman 實際 build/run；實際 UI 瀏覽器驗收。本次未驗證 Ollama／Qwen3。P1 多輪狀態、人工 interrupt/resume 未開發；P2–P5 未開發。
