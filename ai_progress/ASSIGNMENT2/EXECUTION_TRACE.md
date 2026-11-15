# Agent 執行追蹤：Demo A1 完整流程（Claude A，2026-11-15，純文件整理）

來源：`ai_progress/ASSIGNMENT2/evidence/demo_scenarios_run_20261109.txt`（真實執行輸出，
2026-11-09 於真實運行中的容器、真實本機 Ollama `qwen3:8b` 上產生，非範例文字）與
`scripts/demo_scenarios.py`（產生該次執行的來源腳本）。以下把 Demo A1 這一輪拆成六個階段；
每段皆引用原始內容並標明來源。原始輸出沒有涵蓋的階段，直接標示「此階段原始紀錄中無對應輸出」，
不補寫、不推測內容。

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

## Agent 架構說明

**Model**：本機 Ollama，預設 `qwen3:8b`（`README.md` 第 2 節 `OLLAMA_MODEL=qwen3:8b`；本次
Demo 執行使用真實該模型，非 mock）。LLM 只用於「轉述」，不被允許自行做數學、授權判斷或決定控制
流程（`ai_progress/RISK_INTELLIGENCE_EVALUATION/CURRENT_ARCHITECTURE.md` 第 62-74 行）。

**Tools**：`get_context`／`check_constraints`／`trace_impact`（詳見本次新增的
`ai_progress/ASSIGNMENT2/TOOL_SPEC.md`）。三者的呼叫與否、呼叫順序、傳入參數完全由
`app/analyzer.py` 的固定邏輯決定，**LLM 不參與「要不要呼叫工具」或「呼叫哪個工具」的決策**。

**Orchestration**：`app/analyzer.py:440-457`——若環境安裝了 LangGraph，用
`StateGraph` 編譯四個順序節點（`get_context→check_constraints→trace_impact→synthesis`）；
未安裝則用程式明示的 `sequential_fallback` 依序呼叫同樣四個函式。回傳結果裡的
`orchestration` 欄位會誠實標示實際走的是 `'langgraph'` 還是 `'sequential_fallback'`，
不會偽稱已使用 LangGraph（`README.md` 第 2 節「本地 LangGraph」一段）。

**是否採用 ReAct**：**未採用**。依據：
1. `ARCHITECTURE_AND_HANDOFF.md`「實際資料流」一節明確寫出固定的
   `Workflow [get_context -> check_constraints -> trace_impact -> synthesis]`，並在該段結尾
   說明「這是刻意設計的單一工作流，不是角色互辯設計」。
2. `CURRENT_ARCHITECTURE.md` 第 62-74 行（「2.3 LLM 在整條流程裡被允許做什麼」）明確指出 LLM
   只能轉述系統已經算好的內容，任何不在「系統信任的數字集合」裡的轉述都會被 M7 擋下退回確定性
   範本——LLM 沒有機會依據自己的觀察去決定下一步該呼叫哪個工具或改變流程走向，而 ReAct 模式的
   核心正是「LLM 依據上一步的 Observation 自主決定下一個 Action」。本專案的工具呼叫序列與參數
   完全不受 LLM 輸出影響，因此架構上不符合 ReAct 的定義。

**待使用者補充**：上述兩點是從現有程式碼與架構文件的「實際行為」反推「這不是 ReAct」，但 repo
裡沒有找到一份文件明確寫出「團隊曾經比較過 ReAct 並決定不採用，原因是 XYZ」這種決策記錄。如果
作業要求的是當初選型時的主觀決策理由（而不是對現有架構的事後描述），這部分需要你本人補充。
