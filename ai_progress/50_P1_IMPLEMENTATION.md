# P1 第一個里程碑 — 可持續上下文的多輪分析與補問(最小可驗證版本)

執行者：Claude。時間：2026-10-18 22:10(Asia/Taipei)。
範圍：僅完成使用者指定的「P1 第一個最小可驗證版本」,未觸碰 P2–P5,未對 LangGraph StateGraph 本身或人工核准流程做任何修改。

## 1. 設計決策與為什麼這樣做

重新讀過 `app/analyzer.py`、`app/api.py`、`app/db.py` 後,決定**不**把多輪對話做成 LangGraph 的 `interrupt/resume`,原因:

- 使用者明確要求「不要為了加入多輪功能而大幅重構整個專案」「最多完成一個可獨立測試的里程碑」。
- 現有 `analyze()` 的 LangGraph 圖是**四個確定性節點的單一工作流**(get_context → check_constraints → trace_impact → synthesis),不是角色互辯或需要人工介入的多步驟圖;把「多輪對話」塞進同一個 StateGraph 的 interrupt 機制,等於要重新設計這個圖的拓撲,風險和工作量都遠超「最小可驗證版本」。
- 真正需要的能力是「記得上一輪問了什麼、這一輪有沒有解決」,這是**跨多次獨立 analyze() 呼叫**的持久化問題,不是單次呼叫內部要不要暫停的問題。所以選擇在 `analyze()` 外面加一層輕量的 session 記錄,圖本身完全不動。

## 2. 實際完成的功能

**Session 識別與延續**:呼叫端(如同既有 `actions` 的 `idempotency_key` 模式)自行提供一個 `session_id` 字串給 `POST /api/projects/{project}/analyze`:

- 第一次使用該 `session_id` 時自動建立一筆 `sessions` 紀錄(`open`)。
- 之後每次用同一個 `session_id` 呼叫 `/analyze`,系統會:
  1. 驗證這個 session 屬於同一個使用者、且尚未關閉(否則 403／409)。
  2. 取出上一輪分析的 `unknowns`,與本輪算出的 `unknowns` 比對,算出「這次解決了什麼(`now_resolved`)」「還有什麼沒解決(`still_unknown`)」。
  3. 把這份比對結果放進回應的 `session` 欄位,並寫回 `sessions.status`(全部解決就 `closed`,否則維持 `open`)。
- 新增 `GET /api/projects/{project}/sessions/{session_id}`,列出這個對話目前狀態與每一輪的分析紀錄(供人工或前端檢視對話歷史)。
- 不提供 `session_id` 時,行為與修正前完全一致(`result` 不會多出 `session` 欄位),對既有呼叫端零影響。

**保留工程工具呼叫與來源紀錄**:每一輪仍然是一次完整、獨立、可追溯的 `analyze()`(呼叫既有 `get_context`/`check_constraints`/`trace_impact`),`tool_calls` 表照舊逐輪紀錄,沒有任何快取或跳過工具呼叫的邏輯——**不會**為了「接續對話」而讓後面幾輪少跑確定性檢核。

**資料版本不會被無條件沿用**:因為每一輪都是全新呼叫 `analyze()`,各自讀取當下的 `project.data_revision` 並在送出時重新比對(既有的樂觀鎖機制),所以同一個 session 的後面幾輪不可能用到已經過期的資料 — 這點**沿用既有設計**,沒有新增例外。

**人工核准流程完全不受影響**:`session_id` 只存在於 `analyze()`/`/analyze` 這條只讀分析路徑;`request_action`／`review_action`／`execute_action`(`app/actions.py`)完全沒有被碰,也沒有任何新程式碼呼叫它們。`tests/test_session_continuity.py::test_approval_pipeline_unreachable_from_analyze_or_session` 直接用現有的 `POST /actions` → `POST /actions/{id}/review` → `POST /actions/{id}/execute` 三段式流程驗證:engineer 不能自我核准(403)、未核准不能執行(409)、核准後才能執行(200)。

## 3. 實際變更的檔案

| 檔案 | 變更 |
|---|---|
| `app/db.py` | 新增 `sessions` 表;`analyses` 新增 `session_id` 欄位(含既有 DB 的 `ALTER TABLE` 遷移)。 |
| `app/analyzer.py` | 新增 `_open_session()`;`analyze()` 新增可選參數 `session_id`,計算並寫入 `result['session']`,寫入 `sessions.status`。 |
| `app/api.py` | `AnalysisInput` 新增可選欄位 `session_id`;新增 `GET /api/projects/{project}/sessions/{session_id}`。 |

未修改:`app/events.py`、`app/actions.py`、`app/impact.py`、`app/engineering.py`、`app/retrieval.py`、`app/security.py`、LangGraph 圖的拓撲本身一個節點都沒動。

## 4. 測試證據

```sh
.venv/bin/python -m pytest -q tests/test_session_continuity.py   # 5 passed(Claude 自己寫的針對性測試)
.venv/bin/python -m pytest -q                                     # 49 passed, 3 failed(見第 5 節說明)
.venv/bin/python -m scripts.evaluate                               # 12 案維持 45/45
.venv/bin/python -m pip check                                      # No broken requirements found
```

`tests/test_session_continuity.py` 的 5 項測試涵蓋:(1) 真正缺資料(撤權,不是硬湊字串)時進入 `open` 狀態並提出追問;(2) 恢復權限後用同一個 `session_id` 接續,確認 `now_resolved`/`still_unknown` 正確、session 轉為 `closed`;(3) 無任何 unknown 的一開始就直接 `closed`;(4) 別人不能頂用他人的 `session_id`(403),已關閉的 session 不能再續(409);(5) 不帶 `session_id` 時行為與修正前一致;(6) 核准管線完全不受影響。

## 5. 與 Antigravity `tests/test_p1_multi_turn.py` 的技術分歧(明確記錄,不要默默蓋過去)

這是她在我開發期間獨立寫好的 P1 前置測試規格。跑起來 3 個失敗、1 個通過,逐一說明,**不是我用降低測試強度的方式讓它通過,而是先確認每個失敗背後的原因**:

- `test_p1_facts_inferences_assumptions_unknowns_quad_separation`:**通過**。這個驗證既有的事實/推論/假設/未知四分法,修正前就已經成立,確認我的改動沒有破壞這個既有不變量。

- `test_p1_session_identifies_missing_data_and_asks_followup`:**失敗,但原因不是我的功能有問題**。這個測試用預設種子資料下的一般問題(「評估更換高轉速主軸馬達之可行性」),斷言 `unknowns` 清單裡必須出現「連續功率」「啟動」或「規格」字樣。但預設種子資料的 5 個規格事實(電源電壓/電流、馬達電壓/電流、其他負載電流)全部存在且 engineer 預設有權限,所以 `check_constraints` 會正確算出 `pass`/`fail`,不是 `unknown`——這是**對的**,系統不應該在明明算得出結果時卻說「不知道」。啟動電流這類系統本來就沒有建模、無法確定性驗證的項目,既有設計是放進 `questions_to_manager`(這個測試的斷言 1 其實已經通過,因為 `questions_to_manager` 裡本來就有「馬達啟動電流及驅動器允許峰值是多少？」),而不是灌進 `unknowns`——把它硬塞進 `unknowns` 會混淆「我確定性地不知道」跟「這個規則本來就沒做」兩件事,是在扭曲既有語意讓測試通過,所以沒有這樣做。真正會讓這個場景產生 `unknowns` 的方式(撤權或缺少事實)已經在我自己的 `test_session_continuity.py` 裡驗證。
- `test_p1_stale_data_revision_blocks_stale_session_execution`、`test_p1_strict_human_approval_enforced_no_auto_execution`:**失敗,因為測試假設了一個不存在的 Actions API**(`POST /actions` 用 `title`/`task_key`/`delta` 欄位、`PATCH /actions/{id}` 搭配 `{"status":"approved"}`)。實際上 `app/actions.py`/`app/api.py` 現有且已被 `tests/test_core.py`、`tests/test_session_continuity.py` 驗證多次的介面是 `POST /actions`(`analysis_id`/`task_id`/`new_state`/`idempotency_key`)+ `POST /actions/{id}/review`(`{"approve":bool}`)+ `POST /actions/{id}/execute`。這兩項測試描述的是一個**還沒被決定、也不在這次授權範圍內**的新 API 設計,不是我這次里程碑該碰的東西——擅自新增一套平行的 PATCH 式 Actions API 來讓它通過,正是使用者明確禁止的「大幅重構」。已經在 `ai_progress/claude-p1/` 留這份說明,等 Antigravity 或 Codex 確認這兩項測試原意(是打算重新設計 Actions API,還是測試本身要修正成既有介面)。

## 6. 補充(2026-10-18 22:45)— 舊提醒安全收尾 + 6 項使用者查核清單

使用者在授權處理 3 項測試分歧的同一則訊息裡,特別要求確認「修復前已存在的舊提醒是否仍可能在新讀取端點洩漏」。已處理,不是用刪除或重置 `runtime/` 資料庫掩蓋:

- `app/api.py` 的 `_alert_view` 新增偵測:修正後的程式碼**絕不會**把「可能受影響節點」這段文字寫進資料庫的 `body` 欄位(現在只在讀取時、通過當下讀者 ACL 檢查後才動態組出來)。所以只要讀到 `node_sources_json` 是空的**而且**資料庫裡的 `body` 原文仍含有這段字樣,就一定是修正前的舊程式碼寫的、裡面的節點名稱已經無法重新驗證授權——這種情況一律遮蔽成「此提醒建立於 ACL 安全修正前…已遮蔽」,對所有讀者(含 manager)一視同仁,不碰原始資料列。
- 新增 `tests/test_legacy_alert_safety.py`(直接寫入一筆模擬舊資料的 DB row,因為修正後的寫入路徑已經不可能再產生這種 row):確認舊資料裡的節點名稱不會外洩,同時確認「從來沒提過節點名稱」的舊資料(例如分析失敗分支)不會被誤遮蔽。2 項測試皆通過。

使用者同時列了 6 項要 Claude 自查的項目,逐項對照既有測試證據:

| # | 項目 | 狀態 | 證據 |
|---|---|---|---|
| 1 | Session 確實保存與恢復前一輪狀態 | ✅ | `test_session_open_on_genuinely_missing_fact_then_resolves_after_access_restored` |
| 2 | 能根據真正缺少的資料提出追問 | ✅ | 同上(用撤權製造真實缺漏,不是硬湊字串) |
| 3 | 補充資料後會繼續前一輪分析 | ✅ | 同上,`now_resolved`/`still_unknown` 正確區分 |
| 4 | Session 受使用者與專案權限限制 | ✅ | `test_session_cannot_be_hijacked_or_continued_after_close`(他人頂用 403,已關閉續接 409) |
| 5 | 資料版本或 ACL 變動時會重新驗證來源 | ✅ | 新增 `test_session_turn_detects_document_revision_change_not_cached_result`:同一個仍開啟的對話裡,中途改版的文件在下一輪立刻被判定 `stale`,不會沿用第一輪算好的數字;另外「已關閉的 session 拒絕續接、必須開新對話」本身就是對「資料已經變了就不能默默接龍」的保守處理,不是漏洞。 |
| 6 | 工程檢核與重要寫入仍由確定性程式與人工核准控制 | ✅ | `test_approval_pipeline_unreachable_from_analyze_or_session`:未核准不能執行(409)、engineer 不能自我核准(403)、核准後才能執行(200);全程沒有新增任何會自動寫入 `simulated_tasks` 的路徑。 |

全套 `pytest -q` 現況(2026-10-18 22:50):**52 passed, 3 failed**(失敗項目同第 5 節,待 Antigravity/Copilot 確認 Actions API 分歧)。

## 7. 補充(2026-10-18 23:05)— Antigravity/Copilot 無法接手,Claude 依使用者授權直接完成第 5 節分歧

Antigravity 在處理第 5 節的分歧前觸及使用額度上限(重置還需 165 小時),Copilot 這次執行環境持續回報無法寫入專案檔案。使用者確認狀況後直接訊息「大家用量都見底了,後續你接著繼續完成」,明確授權由 Claude 一人完成剩下的工作,**不是 Claude 自行決定取代其他人**。

處理方式與第 5 節原本的技術判斷完全一致,沒有改變結論,只是由 Claude 親自動手把 `tests/test_p1_multi_turn.py` 改掉(她的檔案,但她已無法動作):

- 情境 1:加一步 `PATCH /documents/DOC-PS/access` 撤銷 engineer 權限,製造真實缺漏;原斷言不變。
- 情境 2、3:改用真實 Actions 契約(`POST /actions` + `POST /actions/{id}/review` + `POST /actions/{id}/execute`),驗證同樣的安全需求(未核准不能執行、過期資料擋下、engineer 不能自我核准),沒有新增平行 API。

**全套結果:`pytest -q` → 55 passed, 0 failed。** 完整驗收紀錄另見 `ai_progress/70_P1_FINAL_ACCEPTANCE.md`。等 Antigravity 額度恢復、Copilot 權限問題解決後,請兩位回頭複核這次測試修正是否合理,不要預設一定正確。

## 8. 已知限制(不誇大完成度)

- 這是「記住上一輪缺什麼、這輪解決了沒有」的最小版本,**不是**自然語言自由對話;使用者仍需要用同一個 `session_id` 重新呼叫 `/analyze`,系統不會自己主動發訊息追問。
- 沒有使用 LangGraph 的 `interrupt/resume`;原因見第 1 節。如果之後要往那個方向做,會是下一個里程碑,不在本次範圍。
- `questions_to_manager` 目前仍是每輪重新產生的固定清單(不會因為上一輪已經問過而省略),只有 `unknowns` 有做「有沒有解決」的比對。
