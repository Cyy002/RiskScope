# Agent 執行追蹤：Demo A1 完整流程（Claude A，2026-11-15，純文件整理）

來源：`ai_progress/ASSIGNMENT2/evidence/demo_scenarios_run_20261109.txt`（真實執行輸出，
2026-11-09 於真實運行中的容器、真實本機 Ollama `qwen3:8b` 上產生，非範例文字）與
`scripts/demo_scenarios.py`（產生該次執行的來源腳本）。以下把 Demo A1 這一輪拆成六個階段；
每段皆引用原始內容並標明來源。原始輸出沒有涵蓋的階段，直接標示「此階段原始紀錄中無對應輸出」，
不補寫、不推測內容。

### 關於「資料庫真實紀錄」區塊（2026-11-15 補充）

註：此為 2026-10-20 舊版程式的真實紀錄；該版本未使用使用者提供的數值（user_supplied_fact_keys
為空），此缺陷已於後續版本處理（找不到單獨的修正 commit：本 repo 的 git 歷史從 `027a458`
（2026-11-09，Initial commit）開始，該 commit 的 `app/engineering.py` 已包含處理機制——M8 的
`mode='replace'/'add'` 與 M12.5.1 的 `supply_actual_current`，見 `power_continuous` docstring；
同類輸入在 2026-11-09 的 Demo A1 已正確使用使用者數值，見階段 4 的 14A／336W。但 10/20 這句
訊息本身沒有在現行版本重跑，針對這一句是否已修正待確認）。

Demo A1 那次執行寫入的 `analyses`／`tool_calls` 紀錄存在測試 VM
（`riskscope-codex-apple-20261107`）的容器 volume 內。2026-11-15 兩次檢查時，正式機
`riskscope-machine` 與兩台測試 VM 皆未運作（`podman ps -a` 無法連線，8100／8110／8130 皆未
監聽），依指示不啟動，因此**沒有取得 Demo A1 本身、也沒有取得任何 11/09 之後的資料庫紀錄**。
本機 `runtime/agent.sqlite3` 的 `analyses` 與 `tool_calls` 皆為 0 筆。

以下各階段標示「資料庫真實紀錄」的區塊，取自**另一次真實執行**——目前能讀到的、與 Demo A1
最接近的一次完整分析（同為 `focus='motor_upgrade'` 的馬達/電源問題）：

- 來源檔：本機備份 `ai_progress/backups/riskscope_runtime_20261021_143927.tar.gz` 內的
  `agent.sqlite3`（該目錄被 `.gitignore` 排除，不在 repo 內）。只把資料庫檔解到 `/tmp` 的副本
  讀取，未開啟或寫入原檔，未解出憑證檔。
- 紀錄：`analyses.id = 460db3dc-f083-44ab-aea3-17d8af966fb3`，
  `created_at = 2026-10-20T05:42:25+00:00`，`session_id = chat-99eef80c`，`user_id = manager`，
  `project_revision = 4`；對應 `tool_calls.id = 13–16`。
- **這不是 Demo A1**：時間早於 Demo A1（2026-11-09）約三週，當時的程式版本較舊，輸入訊息與
  計算結果（11A／264W）都與 Demo A1（14A／336W）不同，兩者不可混為同一次執行。

## 階段 1：User Input

原始終端輸出（`demo_scenarios_run_20261109.txt`）本身只印出斷言結果，不包含逐字的使用者輸入
文字；該文字來自**產生這次執行的固定腳本原始碼**（不是本文件事後編造）：

> 來源：`scripts/demo_scenarios.py:35`
> ```python
> a = chat('電源24V，名目額定10A，實際可用8A，馬達11A，輔助3A，電流夠嗎？', sid + 'a')
> ```
> `chat()`（`scripts/demo_scenarios.py:19-22`）會以 `engineer` 身分呼叫
> `POST /api/projects/demo-chamber/chat`，body 為 `{message, session_id, use_local_llm: true}`，
> 未指定 `focus`，故採用 API 層預設值 `focus='motor_upgrade'`（`app/api.py:180`）。

**資料庫真實紀錄（非 Demo A1；`analyses.question`，id `460db3dc…`，2026-10-20T05:42:25Z）：**

> 我準備把馬達更換成 24V、11A 的型號，但目前電源最大只能提供 8A，而且專案交期不能延後。請分析
> 直接更換的風險，並比較升級電源、降低馬達負載兩種替代方案。哪些條件還需要確認？

同一 session（`sessions.id = chat-99eef80c`）的 `user_supplied_json` 記錄了從這句話抽出的數值：
`motor_continuous_current=11A`、`motor_voltage=24V`、`supply_continuous_current=8A`、
`supply_voltage=24V`。

## 階段 2：Agent Decision（第一次：決定走哪個分析流程）

**此階段原始紀錄中無對應輸出**——`demo_scenarios_run_20261109.txt` 不會印出內部流程決策。
以下描述依據程式碼邏輯（`app/analyzer.py`），而非執行輸出文字：

`focus='motor_upgrade'` 落在 `FOCUS_ROOTS` 內，`app/analyzer.py:320-324` 的 `rule_step` 因此
會呼叫 `check_constraints`（否則會是空列表 `[]`，走 generic 範本路徑）。整條流程的步驟順序是
**程式碼寫死的確定性 workflow**，不是 LLM 自己決定要不要呼叫、呼叫哪個工具：
`app/analyzer.py:440-457` 顯示若環境裝有 LangGraph 就編譯 `get_context → check_constraints →
trace_impact → synthesis` 四個順序節點（`graph_mode='langgraph'`）；沒裝的話用
`sequential_fallback` 依序呼叫同樣四個函式。這一步的「決策」屬於**確定性 orchestration**，
不是 LLM 自主決策。

## 階段 3：Tool Call

同樣**此階段原始紀錄中無逐筆工具呼叫的日誌輸出**（`tool_calls` 表會記錄每次呼叫，但這次執行的
原始 txt 檔沒有把該表內容印出來）；可確認「確實被呼叫」是依據下一階段（階段 4）輸出的計算結果
反推（`14A/336W` 等數字只可能來自 `check_constraints` 的真實計算，不可能是 LLM 捏造，因為
`app/engineering.py` 是本專案唯一做這個計算的地方）。依程式碼，本輪依序呼叫：

1. `get_context`（`app/analyzer.py:317-319`）：輸入 `question`（即階段 1 的訊息全文）與
   `focus='motor_upgrade'`。
2. `check_constraints`（`app/analyzer.py:320-324`，實際函式 `power_continuous`）：輸入包含
   `simultaneous=True` 與使用者在訊息裡聲明的六個數值（24V／10A／8A／11A／3A）。**待確認**：
   這些數值如何從自然語言訊息被解析成 `user_supplied` 參數，是 `app/chat.py` 的
   `_extract_user_supplied`（`app/chat.py:1123`）的職責，本文件未深入核對該解析邏輯本身。
3. `trace_impact`（`app/analyzer.py:325-328`）：對 `focus='motor_upgrade'` 對應的
   `FOCUS_ROOTS` 逐一呼叫。

**資料庫真實紀錄（非 Demo A1；`tool_calls` 表，`analysis_id = 460db3dc…`，四筆的
`created_at` 皆為 `2026-10-20T05:42:25+00:00`）：**

| `tool_calls.id` | `tool_name` | `arguments_json`（原文） |
|---|---|---|
| 13 | `get_context` | `{"focus": "motor_upgrade", "question": "我準備把馬達更換成 24V、11A 的型號，但目前電源最大只能提供 8A…（已截斷，全文同階段 1）"}` |
| 14 | `check_constraints` | `{"rule_id": "continuous_power", "simultaneous": true}` |
| 15 | `trace_impact` | `{"root": "M-02"}` |
| 16 | `trace_impact` | `{"root": "PS-01"}` |

呼叫順序與上述程式碼描述一致（`get_context → check_constraints → trace_impact`，
`trace_impact` 對兩個 root 各呼叫一次）。

## 階段 4：Observation

以下直接引用 `demo_scenarios_run_20261109.txt` 的實際輸出行（真實執行結果）：

```
PASS A1 14A/336W ('14', '336')
PASS A1 nameplate 10A, usable 8A kept separate
PASS A1 structured: +40% over nameplate / +75% over usable
   (info) percentages also in LLM wording: True
PASS A1 never narrates nameplate 10A->8A
```

對照 `scripts/demo_scenarios.py:36-43` 的斷言邏輯，這代表 `check_constraints` 回傳的
`numbers['total_current_a']=='14'`、`numbers['total_power_w']=='336'`、
`numbers['nameplate_limit_current_a']=='10'`、`numbers['actual_limit_current_a']=='8'`，
且超額百分比計算（`+40%`／`+75%`）正確、額定與實際可用容量沒有被互相覆蓋或混淆敘述。

**資料庫真實紀錄（非 Demo A1；`tool_calls.result_json`，id 13–16）：**

- **id 13 `get_context`**（已截斷，只列文件 ID 與標題，略去各筆 `excerpt`）：回傳 6 份文件——
  `DOC-PS`（PS-01 電源規格）、`DOC-AUX`（其他系統負載）、`DOC-MOTOR`（M-02 馬達候選規格）、
  `DOC-PLAN`（整合研發依賴與驗證任務）、`DOC-CONF`（機密：內部成本假設，`classification:
  confidential`；本次呼叫者為 `manager`，有權限）、`DOC-SUPPLIER`（合成供應商與需求修訂）；
  每筆皆 `truncated: false`、`version: 1`。
- **id 14 `check_constraints`**（`numbers`、`status`、`reason` 為原文；`evidence` 已截斷為摘要）：
  ```json
  {"rule": "continuous_power", "status": "fail", "reason": "持續電流需求超過電源連續額定值",
   "numbers": {"limit_current_a": "10", "limit_power_w": "240", "motor_current_a": "8",
               "motor_voltage_v": "24", "other_current_a": "3", "over_current_a": "1",
               "supply_voltage_v": "24", "total_current_a": "11", "total_power_w": "264"},
   "formula": "I_total = I_motor + I_other；P = V × I",
   "user_supplied_fact_keys": []}
  ```
  `evidence` 五筆皆為 `origin: "document"`、`verified: true`（`DOC-PS` 24V／10A、`DOC-MOTOR`
  24V／8A、`DOC-AUX` 3A）。**須誠實說明**：這次計算用的是文件數值（馬達 8A、電源 10A），
  `user_supplied_fact_keys` 為空——使用者在訊息裡說的「馬達 11A、電源只能提供 8A」**沒有**被
  套用到這次檢核。這是 2026-10-20 當時程式版本的行為，與 Demo A1（2026-11-09）得到 14A／336W
  的行為不同。
- **id 15 `trace_impact`（root `M-02`）**（`paths` 已截斷，8 條只列數量）：
  `affected_nodes = ["DRIVER-01","FIRMWARE-01","MECH-01","RELEASE-01","TEST-01","THERMAL-01"]`，
  `path_count = 8`，`suppressed = {"cycle":0,"depth_limit":0,"stale":0,"unauthorized":0}`，
  `truncated = false`。
- **id 16 `trace_impact`（root `PS-01`）**（`paths` 已截斷，4 條只列數量）：
  `affected_nodes = ["ASSEMBLY-01","RELEASE-01","TEST-01","WIRING-01"]`，`path_count = 4`，
  `suppressed` 四項皆 0，`truncated = false`。

## 階段 5：Agent Decision（第二次：決定最終回覆要不要採用 LLM 轉述）

原始輸出中這一行是直接證據：

```
   LLM A1: ACCEPTED
```

這一步混合了兩種不同性質的決策，須分開誠實標示：

- **由 LLM 決定的部分**：產生「怎麼用自然語言敘述上述數字」的候選文字（`_llm_reply()`，
  `app/chat.py:1403`），實際呼叫本機 Ollama `qwen3:8b`。
- **由確定性程式邏輯決定的部分（非 LLM 自主決策）**：是否**採用**這段 LLM 文字作為使用者最終
  看到的回覆，是 `_reply_is_trustworthy()`（M7，`app/chat.py:914`）逐項核對該文字裡出現的每個
  數字/百分比是否都能在 `check_constraints`／`trace_impact` 的結構化結果裡找到依據，核對通過才
  會採用，否則退回確定性範本（`_deterministic_reply()`）。`llm_state()`
  （`scripts/demo_scenarios.py:24-31`）把這個結果分類為 `ACCEPTED`／`M7-REJECTED`／
  `NOT-CALLED/FAILED`；本輪原始輸出印出 `ACCEPTED`，代表 LLM 被呼叫且其文字通過了 M7。

**這一步的「決策」（該不該用這段 LLM 文字）是確定性程式邏輯做的，不能說成是 LLM 自主決策**；
LLM 只負責生成候選敘述內容本身。

## 階段 6：Final Result

原始輸出未印出完整的最終回覆文字本身（只印出通過的斷言與 `LLM A1: ACCEPTED`），**此處不補寫
或推測回覆全文**。可從原始輸出確認的事實：
- `reply_source` 為 `'llm_phrased'`（依 `llm_state()` 定義：`ACCEPTED` 等同於
  `r.get('reply_source') == 'llm_phrased'`，`scripts/demo_scenarios.py:30`）。
- 使用者最終看到的文字確實包含 `40%` 與 `75%`（`(info) percentages also in LLM wording: True`），
  且不包含會混淆額定與實際可用容量的敘述（`A1 never narrates nameplate 10A->8A` PASS）。

**資料庫真實紀錄（非 Demo A1；`analyses.result_json`，id `460db3dc…`，2026-10-20T05:42:25Z）：**

- `reply_source = "llm_phrased"`、`orchestration = "langgraph"`、
  `decision_status = "requires_human_review"`、`session.status = "closed"`（`turn: 1`）。
- 系統最終回覆（`result_json.reply`，全文，未截斷）：

  > 已記錄您這一輪提供的數值（尚未經管理者正式確認，僅供本次對話試算）：supply_voltage=24V；
  > supply_continuous_current=8A；motor_voltage=24V；motor_continuous_current=11A
  >
  > 已完成本輪分析：
  > - 已確認工程條件：持續電流需求超過電源連續額定值
  > - 計算結果：總電流 11A（電源額定 10A）、總功率 264W（額定上限 240W）
  > - 分析依據：指定工況電流合計 11A；電源額定 10A；對應功率 264W；額定上限 240W
  > - 主要風險：R-POWER：在已知同時持續負載條件下，不符合目前電源連續容量／電壓限制；
  >   R-IMPACT-M-02：M-02 的變更需檢視下游依賴；R-IMPACT-PS-01：PS-01 的變更需檢視下游依賴
  > - 尚未確定的條件：超額不等於必然跳脫或損壞；未取得啟動電流、電源降額、驅動器/散熱/線材驗證
  > - 方案狀態：A（僅更換馬達）：blocked；B（馬達與電源一併調整）：unverified；
  >   C（調整負載分配／控制）：unverified
  > - 建議下一步：馬達啟動電流及驅動器允許峰值是多少？；電源的降額與熱條件是否滿足？；
  >   新馬達尺寸、配線與散熱空間是否已驗證？；採購與回歸測試工期及交期緩衝是多少？
  >
  > 任何變更仍需人工審核後才能執行；本回覆僅轉述下方確定性分析結果，不代表最終核准。

  回覆中的數字（11A／10A／264W／240W）與階段 4 的 `check_constraints` 回傳值一致。如階段 4
  所述，這些是文件數值算出的結果，不是使用者聲明的 11A／8A 情境。

## Agent 架構說明

**Model**：本機 Ollama，預設 `qwen3:8b`（`README.md` 第 2 節 `OLLAMA_MODEL=qwen3:8b`；本次
Demo 執行使用真實該模型，非 mock）。依現行程式碼，LLM 只在四個地方被呼叫（`call_ollama`），
每一處的輸出都要先通過確定性檢查才會被採用：

1. **抽取使用者訊息中的數值**（`app/chat.py:1123` `_extract_user_supplied`，呼叫於 `:1177`；
   僅 `focus='motor_upgrade'`）：LLM 只能對固定的 `USER_SUPPLIABLE_KEYS` 提出候選值，每個候選值
   還要通過 `convert()` 的單位維度檢查，且數值＋單位必須逐字出現在使用者訊息裡
   （`_grounded_in_message`）才會被採用——模組 docstring 的原話是「propose (never decide)」。
2. **轉述確定性計算結果**（`app/chat.py:1403` `_llm_reply`，呼叫於 `:1476`）：有確定性檢核的
   焦點（`chat_turn` 的 `if check:` 分支，`app/chat.py:1693`，Demo A1 走這條），LLM 只把已算好的
   結果改寫成自然語言，再由 M7（`_reply_is_trustworthy`，`app/chat.py:914`）核對，不通過就退回
   確定性範本。
3. **無確定性規則的焦點做自由形式的風險分析**（`app/chat.py:1488` `_generic_free_form_reply`，
   呼叫於 `:1552`；`chat_turn` 的 `app/chat.py:1654`、`:1709` 分支，例如 Demo B 的供應商決策）：
   這條路徑上 LLM 確實自己做推理並寫出分析文字，不只是轉述。但文字同樣要過 M7——核准／安全等
   聲稱類檢查維持硬性拒絕，數字類改為附註提醒（`strict_numeric=False`，`app/chat.py:1720`）；
   排程總工期由程式重算。這段文字只成為回覆內容，不會改寫 `facts`／`options`／`risks`。
4. **`/analyze` 的選用說明文字**（`app/analyzer.py:60` `_safe_local_explanation`，呼叫於 `:86`）：
   同樣經 M7 檢查，不通過即不保留。

四處都不涉及選擇工具、決定流程走向、核准或寫入。註：`CURRENT_ARCHITECTURE.md`（2026-11-01）
寫的「LLM 只能轉述」早於第 3 點的 2026-11-04 架構修訂，以上以現行程式碼為準。

**Tools**：`get_context`／`check_constraints`／`trace_impact`（詳見本次新增的
`ai_progress/ASSIGNMENT2/TOOL_SPEC.md`）。三者的呼叫與否、呼叫順序、傳入參數完全由
`app/analyzer.py` 的固定邏輯決定，**LLM 不參與「要不要呼叫工具」或「呼叫哪個工具」的決策**。

**Orchestration**：`app/analyzer.py:440-457`——若環境安裝了 LangGraph，用
`StateGraph` 編譯四個順序節點（`get_context→check_constraints→trace_impact→synthesis`）；
未安裝則用程式明示的 `sequential_fallback` 依序呼叫同樣四個函式。回傳結果裡的
`orchestration` 欄位會誠實標示實際走的是 `'langgraph'` 還是 `'sequential_fallback'`，
不會偽稱已使用 LangGraph（`README.md` 第 2 節「本地 LangGraph」一段）。容器映像有安裝
LangGraph（`Containerfile:7` 安裝 `requirements-langgraph.txt`，內容為 `langgraph==1.0.0`）；
上方 10/20 的資料庫紀錄也記錄了 `orchestration = "langgraph"`。這裡的 LangGraph 只用來串接
四個固定順序的節點，沒有條件分支，也沒有讓 LLM 選擇節點。

**是否採用 ReAct**：**未採用**。依據：
1. `ARCHITECTURE_AND_HANDOFF.md`「實際資料流」一節明確寫出固定的
   `Workflow [get_context -> check_constraints -> trace_impact -> synthesis]`，並在該段結尾
   說明「這是刻意設計的單一工作流，不是角色互辯設計」。
2. 程式碼：`app/analyzer.py:440-457` 的四個節點是固定順序，`app/chat.py` 的 `chat_turn`
   （`:1582`）先跑完 `analyze()`（`:1638`）才呼叫 LLM 產生回覆文字。LLM 的輸出不會回頭觸發
   任何工具呼叫，也不會改變流程走向；而 ReAct 模式的核心正是「LLM 依據上一步的 Observation
   自主決定下一個 Action」。唯一會影響工具輸入的 LLM 輸出是上方第 1 點的數值抽取，它只提供
   `check_constraints` 的候選參數，且須先通過確定性驗證。因此架構上不符合 ReAct 的定義。

本系統未採用 ReAct，而是採用 Model／Tools／Orchestration 三層、由程式控制的確定性工作流。理由：(1) 數值、單位與規格比較屬於可驗證事實，應由確定性工具計算，不交給 LLM 自行決定是否、何時呼叫工具；(2) 涉及核准與變更的動作必須經過固定的權限與人工核准關卡，流程需可預測、可稽核；(3) 本地 Qwen3:8b 在自由選擇工具與多步推理時穩定性不足，固定流程可降低錯誤呼叫與無限迴圈風險。LLM 負責三件事：從使用者訊息抽取候選數值、把確定性工具的結果轉述為自然語言、以及在沒有確定性規則的焦點撰寫風險分析文字；三者的輸出都須通過確定性檢查才會被採用，LLM 不參與數值計算、工具選擇、流程控制與核准。
