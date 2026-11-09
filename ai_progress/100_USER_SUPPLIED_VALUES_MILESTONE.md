# 下一階段里程碑 — 對話中補充的工程數值可用於分析(M2)

執行者：Claude。時間：2026-10-19 00:30(Asia/Taipei)。
授權依據:使用者「RiskScope｜無人值守持續開發授權」訊息,明確指示評估四項已知限制的優先序,挑一個「能明顯改善實際使用體驗、且可獨立驗證」的功能做下一個里程碑,並以**單人完成、尚待獨立審查**的狀態交付。

## 1. 優先序評估(為什麼選這一項)

使用者列出四項限制:
1. 自由文字無法完整判斷分析目標(`focus`)。
2. **使用者在聊天中補充的工程數值,無法直接用於後續分析。**
3. LLM 主要負責轉述確定性結果。
4. 對話尚未使用 LangGraph interrupt/resume。

選擇 **#2** 作為本次里程碑,理由:
- 使用者自己舉的優先方向範例(「目前 500W、目標 800W、電源最大 1000W」)就是在描述這個限制,代表這是他最在意的實際使用體驗缺口。
- 可以在不新增工程領域資料的前提下,用現有 `power_continuous` 規則完整端到端驗證,風險與範圍都可控。
- #1(自由文字判斷 focus)如果做錯,後果是「把分析導到錯誤的固定根節點」,風險比較不可控,且目前用下拉選單/參數指定已經夠用,优先度較低。
- #3 是本次的自然副產品(LLM 現在除了轉述,也多了一個「有界限的欄位抽取」任務,但一樣不計算、不下結論)。
- #4(LangGraph interrupt/resume)在 P1 階段就已經評估過,目前的確定性 session 機制已經滿足真正的需求(見 `ai_progress/50_P1_IMPLEMENTATION.md` 第 1 節),沒有新增急迫性,維持原判斷。

## 2. 跟使用者範例的關係(誠實對照,不假裝完全重現)

使用者的例子是「加熱功率:目前 500W / 目標 800W / 電源最大 1000W」。這個場景**目前的工程規則模組沒有建模**——`app/engineering.py` 只有 `power_continuous`(電壓/電流,馬達升級情境),整個合成專案的文件、依賴圖、事實資料都是圍繞 PS-01/M-02 這個馬達案例設計的,沒有「加熱裝置」這個領域的文件或事實。要做出一個新的加熱功率檢核,需要新增新的合成文件、事實鍵與可能的依賴邊,這已經超出「最小可行、不要大規模重構與目標無關的系統」的範圍。

**因此本次用現有、真實建模的領域(電源/馬達電壓電流)完整實作同一個機制**,概念上完全對應使用者要的流程(自然語言補充數值 → Agent 理解並驗證 → 用於本次分析 → 不自行只憑單一數字判斷安全),只是數字範例換成專案既有的 `supply_voltage`/`supply_continuous_current`/`motor_voltage`/`motor_continuous_current`/`aux_continuous_current` 五個欄位。這個對照關係在這裡明確寫出來,不宣稱已經支援任意工程領域。

## 3. 機制設計

1. **封閉欄位清單**:`app/engineering.py` 新增 `USER_SUPPLIABLE_KEYS = {fact_key: dimension}`,只有這 5 個 `power_continuous` 需要的欄位,LLM 不能自己發明新欄位。
2. **LLM 只做「比對抽取」,不做計算或判斷**:`app/chat.py` 的 `_extract_user_supplied()` 把使用者訊息丟給本機 LLM,要求「只能比對這個固定清單,沒提到的欄位絕對不要出現」,輸出 JSON。
3. **確定性二次驗證(防禦性,不信任上游)**:
   - `chat.py` 收到 LLM 輸出後,先用 `engineering.convert()` 驗證每一項的單位/數值格式。
   - `engineering.power_continuous()` **自己也再驗證一次**(不信任呼叫端),格式不對的候選值會被忽略,不會拋例外、也不會悄悄被接受。
4. **Session 暫存,不寫入正式規格**:驗證通過的候選值存進 `sessions.user_supplied_json`(新欄位),同一個對話之後的回合會自動沿用,不用使用者重複輸入;**完全不寫入 `facts` 資料表**。
5. **只填補缺口,正式文件永遠優先**:`power_continuous()` 只在文件事實是 `missing`/`stale`/`unauthorized` 時才套用使用者補充值;一旦文件重新授權/更新,文件的事實值自動蓋回來,使用者之前打的數字不會變成永久的替代品(已用真實請求驗證,見第 6 節)。
6. **證據來源清楚標示**:每一筆 `evidence` 現在有 `origin`(`document` 或 `user_supplied_this_turn`)與 `verified`(`true`/`false`),文件來源才有 `source_id`——這個設計同時確保既有的 ACL 重驗證(`_result_source_ids`)不會把假的 `source_id` 當成文件來源去檢查權限。
7. **不是只看單一數字就判斷安全**:沿用既有 `power_continuous` 的規則(電流總和 vs 額定、電壓是否相容),結果一律附帶 `limitations`/`assumptions`/`questions_to_manager`(啟動電流、降額、散熱等仍標示待驗證),使用者補充值介入計算時還會額外加一條「本次計算包含尚未經管理者正式確認的數值」的提醒。這對應使用者強調的「不得只因 800W 小於 1000W 就判定安全」。

## 4. 實際變更的檔案

| 檔案 | 變更 |
|---|---|
| `app/db.py` | `sessions` 表新增 `user_supplied_json` 欄位 + 既有 DB 的 `ALTER TABLE` 遷移。 |
| `app/engineering.py` | 新增 `USER_SUPPLIABLE_KEYS`;`power_continuous()` 新增 `user_supplied` 參數,內建二次驗證、填補缺口、標示來源與揭露聲明。 |
| `app/analyzer.py` | `analyze()` 新增 `user_supplied` 參數,傳遞給 `rule_step`;`_open_session` 的 INSERT 配合新欄位調整。 |
| `app/chat.py` | 新增 `_extract_user_supplied()`(LLM 抽取 + 確定性驗證)、`_load_user_supplied()`/`_save_user_supplied()`(session 暫存讀寫);`chat_turn()` 整合抽取、合併、傳入分析、回覆文字告知使用者「記錄了什麼/忽略了什麼」。 |
| `app/static/app.js` | 對話頁面提示文字更新,告知可以直接在對話裡提供數值,以及這不會變成正式規格。 |

未修改:`app/actions.py`、`app/events.py`、`app/impact.py`、`app/retrieval.py`、`app/security.py`——人工核准、ACL、文件版本機制完全沒動。

## 5. 測試證據

```sh
.venv/bin/python -m pytest -q
→ 67 passed, 0 failed（60 既有 + 7 項新增 tests/test_user_supplied_values.py）
.venv/bin/python -m scripts.evaluate → 12 案 45/45 不變
.venv/bin/python -m pip check → 乾淨
```

`tests/test_user_supplied_values.py` 涵蓋:填補缺口並正確標示來源、絕不寫入 `facts` 表、格式錯誤的候選值被忽略而非悄悄套用、透過真實 `/chat` 路徑的 session 暫存與合併、文件權限恢復後文件事實自動取代暫存值、封閉欄位清單不可被擴充、以及一項機會性真實呼叫本機 LLM 的抽取測試。

## 6. 真實端到端手動驗證(本機確有 Ollama `qwen3:8b`,逐字保留)

1. 撤銷 `DOC-MOTOR`(同時影響 `motor_voltage` 與 `motor_continuous_current`)。
2. Engineer 發訊息:「我想評估馬達升級方案,目前量到的馬達連續電流大約是 8A」。
   → LLM 正確從自然語句抽取出 `motor_continuous_current=8A`(不是制式格式,是口語描述),通過確定性驗證並套用;`motor_voltage` 仍因撤權而缺漏,整體 `status` 仍是 `unknown`,`unusable_facts` 正確只剩 `motor_voltage`。
3. 管理者恢復 `DOC-MOTOR` 權限,同一 session 繼續:「文件權限已經恢復了,請繼續分析」。
   → `user_supplied_fact_keys` 變成空清單(文件事實重新生效,自動蓋過暫存值),最終算出 `11A/264W`,`status:fail`,與專案既有已知範例完全一致,session 正確關閉。

完整請求/回應細節因包含較長逐字內容,保留在執行紀錄中;數字與行為皆與上方自動測試一致。

## 7. 已知限制(誠實記錄)

- **只支援既有 `power_continuous` 的 5 個欄位**,不是任意工程領域的通用數值抽取機制;使用者的加熱功率範例需要新建一個領域模組才能真正重現(見第 2 節)。
- **兩次 LLM 呼叫(抽取 + 轉述)會疊加延遲**:真實測試中一輪對話視模型負載可能需要 20–35 秒,比單純轉述(P1.1)慢;沒有做任何快取或並行優化。
- **沒有 UI 層的「查看目前 session 暫存了哪些使用者補充值」介面**,只能從回覆文字或 API 回應間接得知。
- **沒有使用 LangGraph interrupt/resume**,維持既有決定。
- **本次修改為單人完成,尚待獨立審查**:Antigravity、Codex 目前都因額度限制無法參與,Copilot 這次環境持續回報無法讀寫專案檔案。所有程式碼變更、測試與本手動驗證都只有 Claude 一人執行,請在額度/環境恢復後安排複核,不要預設一定正確。
- 沒有展開 P2–P5 以外的範圍;Podman 仍未安裝、未授權;沒有刪除或重置 `runtime/`;沒有使用付費 API。
