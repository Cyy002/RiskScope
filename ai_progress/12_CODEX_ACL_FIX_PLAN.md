# RiskScope P0 ACL 根因複核與並行修正方案

日期：2026-10-18（Asia/Taipei）。作者：Codex。狀態：分析與修正提案完成，產品修正尚未開始；待 Copilot 確定分工。

Codex 已閱讀 Claude 的 `ai_progress/claude-p0/11_CLAUDE_ACL_REVIEW.md` 與獨立結果 JSON，兩項問題的重現與根因一致。此處「複核完成」指漏洞確認，不是修正驗收。沒有更動 `app/`、既有 `tests/test_core.py` 或其他代理的檔案。

## 新增可重現證據

執行命令：

```sh
.venv/bin/python -B ai_progress/codex-acl-design/probe_api_boundaries.py
```

使用固定 LangGraph 1.0.0 與每情境獨立的臨時合成 SQLite；不修改真實 runtime。輸出在同目錄 `api-boundaries.json`、`api-boundaries.log`。四項 `finding_reproduced` 均為 true：

| 情境 | 操作與證據 | 修正必須覆蓋 |
|---|---|---|
| A：只使用原始 seed 與既有 API | 將 AUX、MOTOR、PLAN、SUPPLIER 四份文件更新為含查詢詞的 2,500 字元內容，重新核對 motor/aux facts。受 8,000 字元 context 上限影響，DOC-PS 未進入檢索片段但仍供工具計算。撤權後即時 check 為 unknown，舊詳細資料仍 200、含 DOC-PS，列表也仍列出該分析 | 不只是超過 8 份文件才會發生；分析詳細資料和列表都須共用完整來源驗證 |
| A：只有影響路徑、沒有工程 checks | 用獨立合成 distractor 排除檢索來源，執行 supplier 分析，checks 為空。撤銷 DOC-PLAN 後，即時圖只剩 ASSEMBLY-01、PROCURE-01，但舊分析仍 200 並含 DOC-PLAN | 不能只補 checks.evidence；必須包含 impacts.paths.evidence |
| B：先建立提醒，再撤權 | 工程師原本可讀一筆管理者提醒；撤銷 SUPPLIER/PLAN 後，即時圖為空，舊提醒仍含 PROCURE-01；overview 顯示 1 筆 | 讀取時重新檢查目前 ACL，不能只在建立時檢查 |
| B：原始 seed、撤權後再建立提醒 | 不加入額外文件；管理者建立事件 completed，工程師即時圖為空，提醒仍含受保護節點 | 確認漏洞與 distractor fixture 無關；保留正向可見性測試 |

程式結束碼 0 代表探測執行完成，不代表安全驗收通過。這是證據腳本，不取代修正後的預期安全斷言。

## A 的修正邊界

根因：`app/api.py` 的 `_analysis_access` 只遍歷 `result.documents`，但工具來源可以不出現在檢索片段。使用者角色與分析作者的檢查本身仍要保留。

建議 P0 採最小修正：從已保存的結構化結果取得來源 ID 的聯集，去重後逐一檢查讀者當前的專案／文件 ACL。任一來源不允許，沿用既有整筆拒讀 403；分析列表排除該結果。不要只移除來源 ID 字串，因為 10 A／240 W、推論與方案仍可能洩漏。

應納入的明確欄位：

- `documents[].id` 與 `sources[].id`。
- `checks[].evidence[].source_id` 與 `facts[].sources[].source_id`。
- `impacts[].paths[].evidence[].source_id`。

Claude 正確指出 sources/facts 在目前產生端是重複資料；納入聯集成本很低，能使驗證涵蓋實際輸出的結構化欄位。不要任意掃描自然語言的 ID，也不要遞迴把使用者提供的文字當成授權資訊。結構損壞或應有來源卻缺失時應保守拒絕，不把錯誤解析成「沒有來源所以允許」。

建議共用 helper 放 `app/provenance.py`：來源收集與文件權限判定分開；不要混入分析作者限制。manager 可以依原規則查其他人的分析，但不能略過自己的文件 ACL。舊分析可以保留原版本紀錄；不要為了此 ACL 修正把所有 project_revision 不同的歷史分析一律拒讀。

P0 不需要為 A 另加 analysis_sources 資料表；目前完整來源已存在於 result_json。寫入時正規化來源表可後續評估，不能藉此擴大本輪範圍。

## B 的修正邊界與相容性

根因：`app/events.py` 依建立者身分產生影響路徑，把節點寫進提醒文字；讀取端僅判斷是否為專案成員。

應依原提醒所使用的歷史證據快照，檢查目前讀者 ACL。不要拿「目前依賴圖」去授權「歷史提醒文字」；圖資料已改時，兩者可能不同。也不要直接呼叫含作者限制的 `_analysis_access`，否則會把工程師原本有來源權限的管理者提醒一併拒絕。manager 的檢索結果可能含 DOC-CONF，但提醒 body 只由影響路徑生成，因此應以該段提醒實際使用的 impacts 證據授權，避免以無關的機密檢索片段過度限制提醒。

建議的最小可追溯儲存方案（待 Claude／Copilot 確認）：

1. 新增一張小型 `alert_analysis` 關聯表：alert_id 為主鍵／外鍵，analysis_id 連到原始事件分析；在既有 `SCHEMA` 用 `CREATE TABLE IF NOT EXISTS` 初始化。成功分析後，關聯與 body 更新放同一事務。
2. 提醒 helper 取得關聯分析的原始 impacts 證據。JOIN 同時確認分析與提醒的 project_id 一致；用共用權限 helper 判斷讀者是否可讀。
3. 來源完整且有權限時呈現原節點資訊；來源無權限、分析失敗、關聯遺失或舊資料沒有關聯時，回傳不含依賴節點的保守提示。提示由既有事件結構欄位和固定文字產生，不直接回傳未驗證的舊 body。舊資料仍保留，不能清空或刪除 runtime。
4. 既有 `/events` 已向專案成員呈現 signal_key、old/new；保守提醒只沿用相同可見範圍，不引入新來源資料，也不把失敗改寫成分析成功。此方案保留「分析失敗仍留有待處理提醒」的既有功能。
5. 提醒去重仍使用原 event ID；重複事件不可新建關聯或重新分析。缺關聯的舊提醒不得從自由文字抽取 UUID 來猜來源。

這是針對 P0 的方案建議，並非已核准資料庫變更。相容性測試應包含從舊版 SQLite 啟動兩次，資料、憑證、動作、事件及版本均保留。若最終選擇隱藏整筆提醒而不是保守提示，`overview.open_alerts` 必須改用同一可見性判斷，且先確定失敗提醒仍可被管理者處理。

## 提議的檔案所有權

供 Copilot 確定派工；尚未自行開工。

| 執行者 | 獨占檔案 | 工作 | 交叉審查 |
|---|---|---|---|
| Codex | `app/provenance.py`（新增）、`app/api.py`、`tests/test_analysis_acl.py`（新增） | A 的來源聯集與讀取防護；持有 api.py 全檔；在 Claude helper 就緒後接入提醒 route 及必要的 overview 計數 | Claude 審查 A 與 API 接線 |
| Claude | `app/events.py`、`app/db.py`、`app/alert_access.py`（新增）、`tests/test_alert_acl.py`（新增） | B 的歷史來源關聯、讀者授權、舊資料／失敗提醒相容處理 | Codex 審查 B 與相容性 |
| Antigravity | 已持有的 `tests/test_acl_regression.py`、其進度與證據報告 | 補強安全斷言、整理結果；不改 app/ | 雙主力核對測試有效性 |

前置需確認簡單 helper 介面：來源聯集、來源權限判定，以及 `list_alerts_for_reader(conn, actor, project, limit)`。後者回傳保持原 API 欄位的資料，不讓 API 路由層自行解析提醒文字。不要同時修改 api.py 的不同段落而宣稱完全沒有衝突；以單一檔案 owner 加最後接線即可。

## 最低回歸範圍與既有測試審查

已閱讀 Antigravity 的兩個回歸測試；它們可捕捉原始問題，但以下補強會避免不完整修正誤過：

| 編號 | 必要斷言 |
|---|---|
| A1 | 工具數值來源未進入檢索片段時，撤權後 detail=403，列表不包含該分析；fresh check=unknown |
| A2 | 工程 checks 為空但 impact path 使用撤權來源，detail 仍拒讀；涵蓋查詢的字元截斷情境 |
| A3 | 有權限者維持正常讀取；不允許無權限 manager 繞過；他人分析 ownership 與 outsider 拒絕不退化 |
| B1 | 管理者事件先確認 completed 且管理者看得到節點，再確認無來源權限的工程師看不到；不能把所有提醒清空來通過 |
| B2 | 先建立提醒再撤權同樣阻擋；只撤銷部分路徑來源時，不得漏出依賴該來源的下游節點 |
| B3 | 工程師若仍有相關來源權限，應能看管理者建立的提醒；其無 DOC-CONF 權限不應造成無關的拒絕 |
| B4 | 舊提醒／失敗分析／缺關聯以安全提示呈現，不洩漏舊 body，也不宣稱分析已完成；舊 DB 初始化可重跑 |
| B5 | 事件去重、未變更不新增提醒、pass 不誤報、過期核准、未核准禁止寫入及既有 37 項測試保留 |

Antigravity 的 A 測試目前接受「HTTP 200 只要沒有 DOC-PS 字串」，這不足以證明數值與衍生結論已移除；採整筆拒讀方案時應固定驗證 403。B 測試也應先確認分析成功及有權限的讀者確實能看到內容，避免因分析失敗或全面隱藏而誤過。

另外其20號報告引用的 `codex-p0/evaluation.json` 不存在，正確路徑為 `codex-p0/pinned/evaluation.json` 或 `codex-p0/evaluation-existing-env.json`。已發出修正建議，未覆寫對方檔案。

## 階段交接

已完成：讀取 Claude 的獨立複核、確認同一根因、四項補充重現、審查 Antigravity 測試、提出不衝突檔案分工與相容性邊界。核心來源 35 筆雜湊仍全部一致。

尚未完成：Claude 對本修正介面與舊提醒策略的回覆、Copilot 的正式分工、產品修正、修正後交叉驗收。根因已有共識；具體方案尚不能宣稱三方已確認。

技術交流已真實發送至頻道：Claude 事件 `839574d0-8e35-41c0-848f-3f41eaa968dc`；Antigravity 事件 `16dbd558-55b5-454f-ae9f-55a29b4707ef`。API 仍將兩者標記為不派送，故只記錄「已發出，未確認送達」，依使用者指示不繼續調查調度系統。

下一位：Copilot 根據本方案及雙方證據確認分工；Claude 回覆提醒歷史來源與相容性介面。安排修正後由雙方交換審查，不以自己測過作為完整驗收。
