# 接手其他 AI 的完整工程交接紀錄

## 目標、規格與必須守住的原則

此程式是從使用者的 **9 頁企劃書** 落實第一版「跨領域 AI 專業決策與風險分析輔助系統」，依本學期 PoC 的 A 核心為主，B（依賴追蹤）與 C（合成事件監測）各做了初版。不得因擴充 AI 功能而移除來源授權、硬限制可驗證檢核、版本衝突檢查、人工核准、無資料時 `unknown` 等保護。

1. 研究價值：管理者在決策前提早發現跨電氣/韌體/機構/採購/測試的相依風險。
2. 不用 LLM 進行數學、授權、機密分類或直接執行修改。
3. 本版本使用合成資料，任何測試分數不能宣稱反映真實企業節省成本或降低事故。
4. 原企劃第 10 節要求本學期 **單一 Agent**，不需要自行多 Agent 化（除非使用者之後重新要求）。
5. 原始材料不是本專案 README 的延伸需求來源；如有疑問請以使用者上傳的企劃書核對。

## 實際資料流

```text
Web UI / REST requests
  -> Bearer token 驗證
  -> 專案角色檢查 + 文件 ACL（先過濾後檢索）
  -> Workflow [get_context -> check_constraints -> trace_impact -> synthesis]
      -> 可追溯資料與版本、Tool inputs/outputs
      -> 事實 / 推論 / 假設 / 未知、風險 / 方案 / 追問
  -> SQLite analyses + tool_calls + audit
  -> 行動申請 (pending) -> manager 核准 (approved)
      -> 再驗證資料版次 -> 模擬任務寫入 (executed)

人工合成事件
  -> 唯一來源事件 ID / 白名單欄位
  -> 資料版本更新 -> 同一分析流程
  -> 本機 alerts / events；沒有外部通知
```

`app/analyzer.py` 會嘗試匯入 `langgraph.graph.StateGraph`，找到就編譯四個順序節點；若沒有安裝就用明示的 `sequential_fallback`。這是刻意設計的單一工作流，不是角色互辯設計。

## 重要資料表

- `users`：Token 的 SHA-256 雜湊和啟用狀態。Token 本體只在首次初始化時保存到 `runtime/demo_credentials.json` (600)。
- `project_members`：user/project/role/active。
- `documents` / `document_revisions`：目前文件與不可覆蓋的版本快照；`document_access`：每個來源的讀取允許狀態。
- `facts`：人工核對後的定量規格及其來源文件 ID 與版本。文件更新後，來源版次不符的 fact 會被標示為 stale；需人工再次確認。
- `dependencies`：上游→下游，每一條邊包含 document/version provenance。
- `analyses` + `tool_calls`：每一次分析結果與工具輸入輸出。
- `actions`：模擬動作申請/核准/執行、project_revision/idempotency_key。
- `simulated_tasks`：唯一可被動作執行端修改的工作清單；無真實企業 API。
- `events` / `project_signals` / `alerts`：模擬訊號狀態與事件去重。
- `audit`：操作紀錄（仍是可被本機資料庫管理員修改的 PoC 審計，不具有不可竄改保證）。

## 業務規則的重要測試點

- 合成電源例：電源 24 V / 10 A；M-02 8 A；其他負載 3 A。`check_constraints` 得到 11 A / 264 W，判斷 fail。**不能說必然跳脫**；缺啟動電流等資料時仍追問。
- 任意來源文檔只會以「文件片段」身分進入模型提示，不執行其中的指令。所有規則由 deterministic tools 給結論。
- 測試 `test_revoke_immediately_invalidates_context_and_old_analysis` 確保**撤銷 ACL 後，過去已保存的分析也不可再把相關受保護內容交給被撤權使用者**。
- 測試 `test_stale_approval_after_event` 與 `test_stale_execute_after_approval` 確保資料更新前的審核不能偷偷執行。
- `trace_impact` 根據 ACL + provenance 逐邊判斷，不猜不存在的依賴；循環路徑禁止重複經過同節點。
- `scripts/evaluate.py` 測 T01–T12 靜態標註；基本直接連結 vs 多層追蹤分開統計，不能用 Agent 產出作 gold label。

## 下一階段的高優先序待辦（建議先後）

**P0｜驗證環境與交付品質**：在使用者的 Mac Podman machine 上實際建立 image 並執行；安裝 `langgraph==1.0.0` 後跑全套測試；如有 Ollama 再加 local LLM 模型的回覆評估。這些目前因本環境無外部套件索引/LLM server 而未驗證，不可宣稱已完成。

**P1｜完整多輪 Agent**：LangGraph StateGraph 狀態持續化、`interrupt/resume` 的人工補問／審核（目前人工核准是持久化的 API 狀態機，非 LangGraph interrupt）；對含糊提問自動判斷焦點而非依賴使用者選單。語意層與決策層分離，保留完整 Tool observation trace。

**P2｜文件/資料管線**：新增真實的本機 PDF/DOCX/CSV 匯入、引用段落定位與人工審核，版本化 RAG；先進行文件分類與權限同步，不能把原始企業資料任意上傳公有雲。擴充規格資料模型和型別邊界，而不是僅以內文字串代表工程證據。

**P3｜更多可信工具**：電源的峰值/降額、驅動器電流限制、機構間隙、熱預算、甘特圖/關鍵路徑（只有在工期與依賴資料完整時才估天數），每個領域附確定性測試和人工驗證來源。

**P4｜企業級防護**：SSO/RBAC、靜態與傳輸加密、備份、保留政策、來源權限同步、機密分類、審計不可竄改、細粒度場域政策、分散式事務與憑證輪替。當前的 Demo Token + SQLite 只能跑在本機受控環境，不能對外當正式產品。

**P5｜進一步系統整合**：授權的事件系統（Webhook/polling），事件故障補償、去重保留與通知條件，再串專案工具；所有寫入操作仍要人工核准。

## 開發環境下完成之驗證

- Python 3.13.x + FastAPI 0.128.2 + Pydantic 2.13.5 + HTTPX 0.28.1 + pytest 9.0.2。
- `pytest -q` 的 API 整合、權限與驗收測試已通過，測試不需網路/LLM。
- LangGraph 1.0.0 僅寫入可選依賴/Containerfile，**未完成安裝驗證**；本地 Ollama 不可用；Podman image **未完成建置驗證**。
- README 列出可複製的啟動/測試命令，經驗收即可傳接後續 AI 做優化。
