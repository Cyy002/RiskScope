# RiskScope 現有風險分析架構（Claude A，任務A1，唯讀調查，2026-11-01）

調查方法：逐一閱讀 `app/analyzer.py`（決策核心）、`app/engineering.py`（唯一的確定性工程計算）、
`app/retrieval.py`（文件檢索）、`app/chat.py`（LLM轉述與M7可信度驗證）、`app/impact.py`（影響追蹤）。
本文件只描述「現在實際存在的程式邏輯」，不是理想中的設計，每項結論皆附檔案與行號可追溯。

## 一、一句話結論

**RiskScope 只有「馬達／電源連續功率」這一個領域擁有真正的確定性工程計算與數值推理；
除此之外的每一個焦點（供應商、品質、專案管理、商業決策、跨領域……）全部共用同一套
固定三選項模板（`_generic_decision_support`），沒有任何因果鏈分析、風險權重計算、方案
比較演算法，或衝突偵測邏輯——衝突偵測甚至只認得兩句完全寫死的中文片語。** LLM在任何
路徑上都不被允許自己做數學或發明結論，只能轉述系統已經算好／已經知道的內容，這是一個
刻意的安全設計（防止LLM捏造），但副作用是：在沒有確定性計算的領域，LLM即使自己想得到
正確答案，也會被 M7（`_reply_is_trustworthy`）擋下來，因為那個答案不在「系統信任的數字
集合」裡——最終使用者看到的會是毫無計算內容的確定性範本。

## 二、兩層架構：唯一的真計算 vs. 其餘領域的固定模板

### 2.1 真計算路徑（僅 `focus in ('motor_upgrade', 'power')`）

- `app/analyzer.py:276-280`（`rule_step`）：只有這兩個focus才會呼叫
  `engineering.power_continuous()`；其餘focus，`checks` 永遠是空列表 `[]`。
- `app/engineering.py` 的 `power_continuous()`：真正讀取 `facts` 表（電源電壓/電流、馬達電壓/
  電流、輔助負載電流，必要時+使用者補充的「實際可用容量」），做電流加總、取
  `min(名目額定, 實際可用容量)`為約束、算出總功率、超出百分比、以及（M12.5.1新增）
  與上一輪方案的差值（`delta_current_a`/`delta_power_w`）。這是整個專案裡**唯一**一處
  真正的數值工程計算。
- M7（`app/chat.py` 的 `_reply_is_trustworthy`/`_trusted_numbers_by_dimension`）只信任這個
  計算結果（加上`baseline`與`delta`）裡出現過的數字——這是專案刻意的安全邊界，不是缺陷。

### 2.2 其餘一切領域：`_generic_decision_support()`（`app/analyzer.py:139-183`）

- 固定輸出三個選項，**不管使用者問的是供應鏈、專案管理、品質、商業決策還是任何新領域**：
  - G-A「維持原計畫，承擔目前已知的下游風險」
  - G-B「調整受影響節點的時程或範圍以降低風險」
  - G-C「尋找替代資源或路徑，避開目前的限制」
  三者的 `hard_constraint` 預設都是字串 `'unverified'`。
- `facts` 的唯一來源是逐筆把 `project_signals` 表的 key=value 直接轉成「已知專案訊號：{key} =
  {value}」這句話（`analyzer.py:155-158`）——沒有任何推理，純粹是資料表的文字化。
  沒有任何 signal 時，`facts` 就是空的。
- `unknowns` 只是「哪個 signal 的值是 `'unknown'`」的列舉，不是風險分析得出的資訊缺口。
- `risks` 永遠只有一條固定訊息：「本焦點沒有預先驗證的確定性工程規則，以上方案與後果推論
  僅供參考」（`R-UNVALIDATED-ANALYSIS`，`analyzer.py:180-182`）——**這是對所有generic焦點
  唯一會出現的風險項目**，不會因為問題內容而產生第二條、第三條風險、也不會有嚴重度計算。
- **沒有風險優先順序計算**：`priority` 參數（預設 `['品質','交期','成本']`）被整個 `analyze()`
  原封不動收下，但唯一的用途是塞進回傳的 `decision_structure.decision_context.priorities`
  （`analyzer.py:263`, `376`）供顯示——**沒有任何地方用它去排序風險或方案**。
- **沒有嚴重度（severity）計算**：每個 risk 的 `severity` 是寫在程式碼裡的固定字串
  （`'high'`、`'unrated'`），不是依可能性×影響程度算出來的分數，不是FMEA的RPN，也不是任何
  排序依據。
- **「衝突限制偵測」只認得兩句完全寫死的中文片語**（`analyzer.py:123-128`）：
  ```
  G-B: 交期不能延後 / 交期絕不能延後 / 不能延後交期 / 交期不可延後 / 不可延後交期
  G-C: 禁止替代供應商 / 禁止更換供應商 / 不得更換供應商 / 禁止未驗證替代件 / 不能更換供應商 / 不得替代
  ```
  任何其他措辭（例如「45天內必須到貨」「依法規72小時內須完成部署」「60天認證下限無例外」）
  **完全不會被偵測到**，三個選項仍然全部顯示 `'unverified'`，不會變成
  `'conflicts_with_stated_constraint'`。這等同於承認：目前沒有任何通用的「從文字或文件抽取
  硬性限制」機制，只是把M12當時的供應商測試案例原文寫死進規則裡。

### 2.3 LLM 在整條流程裡被允許做什麼

- `app/chat.py` 的 `_llm_reply()`：prompt 明確禁止LLM「自己發明工期天數、機率、成本或金額」，
  只能轉述 `safe_facts`（已經是上面兩條路徑算出來的結構化資料）。
- `_reply_is_trustworthy()`（M7）事後逐項核對：任何數字／百分比／工期／金額，如果不在
  `_trusted_numbers_by_dimension`／`_trusted_schedule_cost_values`／`_trusted_percentages`
  裡，整段回覆直接被丟棄，退回確定性模板。
- **結果**：對於「焦點 = motor_upgrade/power」的問題，LLM轉述的是真計算，會通過M7；
  對於其餘任何領域的問題，就算LLM自己正確算出了（例如）電池熱降額的14A缺口，這個數字
  **不存在於任何結構化結果裡**，M7會判定「提到的數值…與確定性計算結果不一致」而拒絕，
  最終顯示的是 `_deterministic_reply()` 產出的、完全沒有該計算內容的確定性範本。
  這是本次Holdout測試（尤其HA01/HA06/HA08，三題都需要領域計算但都不是
  motor_upgrade/power焦點）預期會直接暴露的架構缺口。

## 三、文件檢索：純關鍵詞比對，不是語意/向量檢索

`app/retrieval.py::get_context()`：
1. 先用 `visible_documents()` 做ACL過濾（這一步是正確、必要的安全設計，先過濾再評分）。
2. 對過濾後的文件，用簡單的中英文/數字token集合（`re.findall(r'[a-zA-Z]+[-\d]*|\d+|[一-鿿]{1,3}', ...)`）
   做字面比對計分：token出現在標題給3分，出現在正文給1分，純粹是出現次數加權，**不是語意
   相似度、不是向量檢索、不考慮同義詞或改寫**。
3. 依分數排序、截斷到 `MAX_CONTEXT_CHARS`（8000字）。

`read_facts()`（被`power_continuous`呼叫）則是乾淨的確定性查表，區分
`missing`/`stale`/`unauthorized`/`ok` 四種狀態，這部分設計良好、與LLM無關。

## 四、安全與流程控制層：是真的，而且是本專案最成熟的部分

以下機制是**確定性的、不依賴LLM**，經過多輪Codex獨立審查與Claude修復，目前判斷是可靠的：
- M6/_grounded_in_message：LLM抽取的數值必須逐字出現在使用者訊息裡才會被採用。
- M7/_reply_is_trustworthy：核准聲稱、安全聲稱、數字、百分比、工期/金額聲稱逐項核對。
- M7.1/_approved_action_for_this_conversation：核准必須綁定同一session與訊息中明確提到的task_id。
- M8：`mode='replace'/'add'` 的使用者假設情境機制，與`engineering.py`的baseline/overridden比較。
- ACL：`document_access`/`require_role`/`visible_documents`，讀取前就過濾，未授權文件不會進
  context也不會進facts。
- `_is_repeat_question`（`analyzer.py:186-200`）：純文字逐字比對，用於session continuity的
  reopen邏輯，不涉及任何內容理解。

這些機制保證了「系統不會說謊、不會洩密、不會被話術繞過核准」，但**不等於系統真的懂得
風險推理**——它們是圍繞著一個目前幾乎是空的決策核心（generic三選項模板）所建立的
誠實性護欄。

## 五、直接回答使用者的問題

| 使用者問的能力 | 現況 |
|---|---|
| 辨識問題核心 | 無獨立機制；只有`focus`選擇（人工指定）與`_focus_mismatch_warning`的關鍵字比對（`app/chat.py`），沒有問題分類/意圖理解邏輯 |
| 已知/未知事實 | 僅motor/power焦點有真正依據（facts表）；其餘焦點=`project_signals`逐筆文字化，不是從文件/問題中萃取 |
| 風險重要性排序 | 不存在；severity是寫死字串，沒有排序演算法 |
| 風險因果鏈（如何產生、傳遞、擴大） | 不存在；`trace_impact`只回傳下游節點id列表（見`app/impact.py`），不產生因果敘事，敘事完全交給LLM自由發揮且不受M7檢查內容合理性（M7只查數字/聲稱類型，不查因果邏輯是否成立） |
| 條件互相衝突偵測 | 僅2句寫死片語（供應商交期/替代供應商），任何其他措辭或文件內隱含的衝突完全偵測不到 |
| 方案可行性比較 | 固定3選項模板，`hard_constraint`只有`unverified`/`blocked`/`conflicts_with_stated_constraint`三種狀態，沒有多維度（成本/時程/品質/風險）比較 |
| 專業計算或驗證依據 | 僅motor/power一種計算；其餘領域的任何計算（熱降額、模具壽命、SLA百分比…）系統本身無法產生，若LLM自己算了也會被M7攔下 |
| 多輪情境更新 | motor/power領域有`__previous_numbers__`機制做到正確的上一輪對比；其餘領域的多輪更新完全依賴LLM記憶/自由發揮，沒有確定性重算 |

## 六、本文件的限制

- 本次調查為唯讀（遵守本機總指揮「本任務期間app/*.py由總指揮獨占修改、請勿編輯」的要求），
  未執行任何測試、未呼叫模型；所有結論皆為直接閱讀程式碼得出，可用檔案行號複核。
- 未深入調查`app/impact.py`、`app/llm_client.py`、`app/security.py`的每一行；上方引用已足以
  支持本文件結論，若後續改善階段需要更細節，屆時再補。
