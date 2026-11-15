# Agent 執行追蹤：完整流程（Claude A，2026-11-15，純文件整理）

來源：正式機 `riskscope-machine` 上的 `riskscope-portable` 容器（埠 8100）內的
`agent.sqlite3`，2026-11-15 由使用者授權啟動後以 `podman cp` 唯讀複製到 `/tmp` 讀取，讀完立即
刪除副本，過程未對系統送出任何新的分析請求。

**這筆紀錄的性質**：輸入文字與 `ai_progress/ASSIGNMENT2/evidence/demo_scenarios_run_20261109.txt`
裡 2026-11-09 的 Demo A1 完全相同，但這是 **2026-11-01T11:30:37+00:00 容器
`riskscope-portable` 上的另一次真實執行**，不是 Demo A1 本身——執行時間早於本 repo 的 git 歷史
起點（`027a458`，2026-11-09 Initial commit），因此無法以某個 commit 精確對應當時的程式版本。
`analyses.id = b1a8efd9-699c-4798-befd-f3b5ee424cbe`，`session_id = chat-af9db95f`，
`user_id = engineer`。以下把這一輪拆成六個階段，每段皆引用資料庫原文並標明表／欄位／ID；
Token、密碼、憑證一律以 `***` 遮蔽（本次紀錄本身未出現任何此類值）。

## 階段 1：User Input

`analyses.question`（id `b1a8efd9…`，`created_at = 2026-11-01T11:30:37+00:00`，全文）：

> 電源24V，名目額定10A，實際可用8A，馬達11A，輔助3A，電流夠嗎？

以 `engineer` 身分呼叫 `POST /api/projects/demo-chamber/chat`，`session_id = chat-af9db95f`，
`focus = motor_upgrade`，`mode = dialogue`，`project_revision = 1`（`analyses` 表對應欄位）。

## 階段 2：Agent Decision（第一次：決定走哪個分析流程）

資料庫的 `analyses`／`tool_calls` 表沒有記錄「為什麼走這條流程」的欄位，此階段仍以程式碼
（`app/analyzer.py`）說明：`focus='motor_upgrade'` 落在 `FOCUS_ROOTS` 內，`app/analyzer.py:320-324`
的 `rule_step` 因此會呼叫 `check_constraints`（否則會是空列表 `[]`，走 generic 範本路徑）。整條
流程的步驟順序是**程式碼寫死的確定性 workflow**，不是 LLM 自己決定要不要呼叫、呼叫哪個工具：
`app/analyzer.py:440-457` 顯示若環境裝有 LangGraph 就編譯 `get_context → check_constraints →
trace_impact → synthesis` 四個順序節點（`graph_mode='langgraph'`）；沒裝的話用
`sequential_fallback` 依序呼叫同樣四個函式。這一步的「決策」屬於**確定性 orchestration**，
不是 LLM 自主決策——這筆紀錄的 `analyses.result_json.orchestration = "langgraph"` 證實當時走的
是前者。

## 階段 3：Tool Call

**資料庫真實紀錄**（`tool_calls` 表，`analysis_id = b1a8efd9…`，四筆 `created_at` 皆為
`2026-11-01T11:30:37+00:00`）：

| `tool_calls.id` | `tool_name` | `arguments_json`（原文） |
|---|---|---|
| 335 | `get_context` | `{"focus": "motor_upgrade", "question": "電源24V，名目額定10A，實際可用8A，馬達11A，輔助3A，電流夠嗎？"}` |
| 336 | `check_constraints` | `{"rule_id": "continuous_power", "simultaneous": true}` |
| 337 | `trace_impact` | `{"root": "M-02"}` |
| 338 | `trace_impact` | `{"root": "PS-01"}` |

呼叫順序與階段 2 的程式碼描述一致（`get_context → check_constraints → trace_impact`，
`trace_impact` 對兩個 root 各呼叫一次）。`check_constraints` 本身的參數沒有帶使用者數值
（`rule_id`／`simultaneous` 是唯二欄位）；使用者數值是透過 `app/chat.py` 的
`_extract_user_supplied`（`app/chat.py:1123`，呼叫於 `:1177`）解析後，以 `power_continuous()`
的 `user_supplied` 參數傳入，不出現在 `tool_calls.arguments_json` 裡——這點與 `TOOL_SPEC.md`
標註的「待確認」一致，本文件同樣未深入核對該解析邏輯本身。

## 階段 4：Observation

**資料庫真實紀錄**（`tool_calls.result_json`，id 335–338）：

- **id 335 `get_context`**（已截斷，只列文件 ID 與標題，略去各筆 `excerpt`）：回傳 5 份文件——
  `DOC-MOTOR`（M-02 馬達候選規格）、`DOC-PS`（PS-01 電源規格）、`DOC-AUX`（其他系統負載）、
  `DOC-PLAN`（整合研發依賴與驗證任務）、`DOC-SUPPLIER`（合成供應商與需求修訂）；每筆皆
  `truncated: false`、`version: 1`。
- **id 336 `check_constraints`**（`numbers`、`status`、`reason`、`user_supplied_fact_keys` 為
  原文；`evidence`／`baseline` 已截斷為摘要）：
  ```json
  {"rule": "continuous_power", "status": "fail", "reason": "持續電流需求超過電源連續額定值",
   "numbers": {"total_current_a": "14", "total_power_w": "336",
               "nameplate_limit_current_a": "10", "nameplate_limit_power_w": "240",
               "actual_limit_current_a": "8", "actual_limit_power_w": "192",
               "motor_current_a": "11", "motor_voltage_v": "24", "other_current_a": "3",
               "over_current_a": "6", "supply_voltage_v": "24"},
   "formula": "I_total = I_motor + I_other；P = V × I",
   "user_supplied_fact_keys": ["motor_continuous_current", "supply_actual_current"]}
  ```
  `evidence` 裡 `motor_continuous_current` 的來源是 `origin: "proposed_change"`、
  `change_mode: "replace"`、`baseline_value: "8"`（文件 `DOC-MOTOR` 原值）→`value: "11"`
  （使用者本輪聲明，`verified: false`）；`supply_actual_current` 是
  `origin: "user_supplied_this_turn"`、`value: "8"`、`verified: false`。其餘三個欄位
  （`supply_voltage`／`supply_continuous_current`／`aux_continuous_current`）仍是
  `origin: "document"`、`verified: true`。**與先前版本的差異**：`user_supplied_fact_keys`
  非空，代表使用者在訊息裡聲明的「馬達 11A、電源實際可用 8A」這兩個值**確實被套用**到這次
  計算，14A／336W 是把這兩個使用者數值代入後的結果，而不是單純的文件數值（8A／10A 會得到
  11A／264W，如 `result.baseline` 欄位所記錄的未覆寫版本）。
- **id 337 `trace_impact`（root `M-02`）**（`paths` 已截斷，8 條只列數量）：
  `affected_nodes = ["DRIVER-01","FIRMWARE-01","MECH-01","RELEASE-01","TEST-01","THERMAL-01"]`，
  `path_count = 8`，`suppressed = {"cycle":0,"depth_limit":0,"stale":0,"unauthorized":0}`，
  `truncated = false`。
- **id 338 `trace_impact`（root `PS-01`）**（`paths` 已截斷，4 條只列數量）：
  `affected_nodes = ["ASSEMBLY-01","RELEASE-01","TEST-01","WIRING-01"]`，`path_count = 4`，
  `suppressed` 四項皆 0，`truncated = false`。

## 階段 5：Agent Decision（第二次：決定最終回覆要不要採用 LLM 轉述）

資料庫沒有單獨記錄這一步的中間過程，只記錄最終結果（`reply_source`，見階段 6）。這一步混合了
兩種不同性質的決策，須分開誠實標示：

- **由 LLM 決定的部分**：產生「怎麼用自然語言敘述上述數字」的候選文字（`_llm_reply()`，
  `app/chat.py:1403`），實際呼叫本機 Ollama。
- **由確定性程式邏輯決定的部分（非 LLM 自主決策）**：是否**採用**這段 LLM 文字作為使用者最終
  看到的回覆，是 `_reply_is_trustworthy()`（M7，`app/chat.py:914`）逐項核對該文字裡出現的每個
  數字/百分比是否都能在 `check_constraints`／`trace_impact` 的結構化結果裡找到依據，核對通過才
  會採用，否則退回確定性範本（`_deterministic_reply()`）。這筆紀錄的
  `analyses.result_json.reply_source = "llm_phrased"`，代表 LLM 被呼叫且其文字通過了 M7。

**這一步的「決策」（該不該用這段 LLM 文字）是確定性程式邏輯做的，不能說成是 LLM 自主決策**；
LLM 只負責生成候選敘述內容本身。

## 階段 6：Final Result

**資料庫真實紀錄**（`analyses.result_json`，id `b1a8efd9…`）：

- `reply_source = "llm_phrased"`、`orchestration = "langgraph"`、
  `decision_status = "requires_human_review"`、`session.status = "closed"`（`turn: 1`）。
- 系統最終回覆（`result_json.reply`，全文，未截斷）：

  > 已記錄您這一輪提供的數值（尚未經管理者正式確認，僅供本次對話試算）：電源電壓為24V，電源
  > 名目額定電流為10A，電源實際可用容量為8A，馬達連續電流為11A，輔助負載電流為3A。
  >
  > 已完成本輪分析：
  > - 您這輪提出的新方案（尚未經管理者正式確認，僅供本次試算比較）：將馬達連續電流由文件
  >   DOC-MOTOR 中的8A 更換為11A。
  > - 您這輪補充的條件（尚未經管理者正式確認，屬於本次分析的假設）：電源實際可用容量為8A。
  > - 已確認工程條件：持續電流需求超過電源連續額定值。
  > - 計算結果：總電流為14A、總功率為336W。
  > - 電源名目額定電流為10A（對應功率為240W），實際電流需求為14A，超出名目額定40%。
  > - 電源實際可用容量為8A（對應功率為192W），實際電流需求為14A，超出實際可用容量75%。
  > - 分析依據：指定工況電流合計為14A，電源名目額定為10A，電源實際可用容量為8A（採較小者作為
  >   約束）；對應功率為336W，名目額定功率為240W，實際可用容量功率為192W。
  > - 主要風險：R-POWER（在已知同時持續負載條件下，不符合目前電源連續容量／電壓限制）；
  >   R-IMPACT-M-02（M-02 的變更需檢視下游依賴）；R-IMPACT-PS-01（PS-01 的變更需檢視下游依賴）。
  > - 尚未確定的條件：超額不等於必然跳脫或損壞；未取得啟動電流、電源降額、驅動器/散熱/線材驗證；
  >   本次計算包含使用者在對話中提供、尚未經管理者正式確認的數值（見 evidence 的 verified:false
  >   項目）；結果僅供本次對話參考，不可視為已確認規格。
  > - 方案狀態：A（僅更換馬達）：blocked；B（馬達與電源一併調整）：unverified；C（調整負載分配／
  >   控制）：unverified。
  > - 建議下一步：請確認馬達啟動電流及驅動器允許峰值是多少？電源的降額與熱條件是否滿足？新馬達
  >   尺寸、配線與散熱空間是否已驗證？採購與回歸測試工期及交期緩衝是多少？
  >
  > 任何變更仍需人工審核後才能執行；本回覆僅轉述下方確定性分析結果，不代表最終核准。

  回覆中的數字（14A／10A／8A／336W／40%／75%）與階段 4 的 `check_constraints` 回傳值一致，且
  正確使用了使用者本輪聲明的馬達 11A、實際可用容量 8A，不是單純的文件數值。

同一 session（`chat-af9db95f`）後續還有兩輪真實對話（A2「只將馬達改成9A，其餘完全不變。」、
A3「電源額定一直是10A，實際可用一直是8A，我只修改馬達。」），結果為 12A／288W，形式上等同
Demo A1→A2→A3 的延續追問；本文件不展開，只以此說明該 session 不是單輪即結束。

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
