# 互動式 AI Agent 里程碑 — 第一個最小可操作版本

執行者：Claude。時間：2026-10-18 23:40(Asia/Taipei)。
授權依據:使用者「RiskScope 互動式 AI Agent — 多輪對話、主動追問與恢復分析」指令,明確要求區分「原本的確定性 Session 狀態追蹤」(P1,已於 `ai_progress/70_P1_FINAL_ACCEPTANCE.md` 驗收)與「真正 LLM 驅動的互動式 Agent」(本次新範圍)。

## 1. 這個里程碑解決什麼問題,以及它跟 P1 的差別

**P1(已完成)**:`/analyze` 接受 `session_id`,系統用確定性比對記住「上一輪缺什麼、這一輪解決了沒」。輸入輸出都是結構化 JSON,沒有自然語言對話層,也沒有任何 LLM 參與。

**本次(P1.1 / 互動式 Agent 第一個里程碑)**:在 P1 的確定性 session 之上,新增一層**真正用自然語言對話**的介面:
- 使用者用自然語言打字(不是填結構化表單),Agent 用自然語言回覆。
- Agent 主動追問時,是用本機 LLM(若可用)把確定性算出的缺漏資訊,轉述成自然口語,而不是只回傳固定模板字串。
- 但 LLM **只負責轉述語氣**,不負責計算、授權、判斷或執行——這條界線用程式碼結構強制:LLM 的函式只接收已經算好的安全摘要欄位(`unknowns`/`questions_to_manager`/`session`/`risks`/`decision_status`),完全不碰文件原文、不碰授權邏輯、也不會被呼叫去觸發任何 `app/actions.py` 的寫入。如果 LLM 不可用或逾時,直接退回確定性模板,兩種情況都會在回應裡明確標示 `reply_source`(`llm_phrased` 或 `deterministic_template`),不會偽稱用了 LLM。

這個界線直接對應使用者說的「必須區分原本的確定性 Session 狀態追蹤與真正 LLM 驅動的互動式 Agent,不能混為一談」——做法是讓 LLM 變成一個可插拔、會失敗會降級、而且完全不被信任去做決策的「轉述層」,底下的確定性引擎(P1 session + 原有的 analyze/engineering/impact/actions)完全不知道上面有沒有 LLM。

## 2. 實際新增的程式

| 檔案 | 內容 |
|---|---|
| `app/chat.py`(新檔案) | `chat_turn()`:呼叫既有 `analyze()`(帶入 `session_id`,完全重用 P1 的確定性邏輯),再疊加 `_llm_reply()`(本機 Ollama,失敗則回 `None`)或 `_deterministic_reply()`(模板)產生 `reply`;把 `reply`/`reply_source` 併回該筆分析的 `result_json`。 |
| `app/api.py` | 新增 `ChatInput` 與 `POST /api/projects/{project}/chat`;擴充 `GET /sessions/{session_id}` 的 `turns`,加入 `reply`/`reply_source`(只回傳這兩個欄位,不回傳完整 `result_json`,避免繞開 `_analysis_access` 的 ACL 重驗證)。 |
| `app/static/index.html`、`app/static/app.js`、`app/static/app.css` | 新增「對話式 Agent」頁面:輸入訊息 → 送出 → 顯示對話紀錄(含每輪的 `reply_source` 標示與 session 狀態)。純前端新增,沒有改動既有頁面邏輯。 |

未修改:`app/analyzer.py`、`app/actions.py`、`app/events.py`、`app/impact.py`、`app/engineering.py`、`app/security.py`——確定性層完全沒動,P0/P1 的保護原封不動延用。

## 3. LLM 使用方式與安全界線(對照企劃「不用 LLM 進行數學、授權、機密分類或直接執行修改」)

- `app/chat.py` 的 `_llm_reply()` 只餵入五個已經是「安全摘要」的欄位,不餵入文件原文、不餵入使用者 token、不餵入任何可執行指令。Prompt 明確要求「只能轉述、不能新增任何數字、授權或結論」,並附上確定性版本當對照(與既有 `app/analyzer.py:_safe_local_explanation` 的既有安全模式一致)。
- LLM 完全沒有被呼叫的機會去碰 `app/actions.py`——`chat_turn()` 的程式碼裡沒有任何路徑會呼叫 `request_action`/`review_action`/`execute_action`。使用者在對話裡打「請直接核准並執行」這種話,也只會被當成 `analyze()` 的 `question` 文字(純粹影響檢索關鍵字比對),不會觸發任何核准或寫入——已用 `tests/test_chat_agent.py::test_chat_cannot_bypass_acl_or_approval` 驗證。
- `app/config.py` 既有的 loopback-only guard(`local_ollama_url()`)原封不動沿用,本次沒有新增任何可以指向雲端或付費端點的設定——**沒有使用任何付費 API**,符合使用者「禁止擅自使用付費 API」的要求。

## 4. 真實端到端驗證(不是只靠自動測試宣稱)

本機剛好已經跑著 Ollama(`qwen3:8b`,與專案預設模型一致),所以除了自動測試,也手動跑了一次完整流程並留存紀錄:

1. 撤銷 engineer 對 `DOC-PS` 的存取權 → `POST /chat`(訊息:「我想評估把馬達升級,但目前資料夠嗎？」)→ **`reply_source: "llm_phrased"`**,LLM 真的用自然語言轉述了「連續功率檢核」缺漏與四個建議追問,內容與確定性欄位一致,沒有自己發明新數字。
2. 管理者恢復 `DOC-PS` 存取權 → 同一個 `session_id` 再送一則訊息(「管理者已經恢復授權了,請繼續分析」)→ session 正確轉為 `closed`,`now_resolved` 正確列出「連續功率檢核」。
3. `GET /sessions/{id}` 正確回傳兩輪對話紀錄,各自標示 `reply_source`。

完整請求/回應細節見本文件第 6 節。

## 5. 自動測試證據

```sh
.venv/bin/python -m pytest -q
→ 60 passed, 0 failed
   新增 tests/test_chat_agent.py: 5/5
     - 真實缺漏時主動追問(deterministic_template 路徑,不依賴外部 LLM)
     - 補充授權後在同一 session 恢復並解決
     - GET /sessions/{id} 只回傳 reply 摘要,不回傳完整 result_json(避免繞開 ACL 重驗證)
     - 對話訊息無法繞過 ACL 或人工核准
     - 機會性驗證:本機若真的有可用的 Ollama,_llm_reply() 會被實際呼叫並驗證回傳的文字確實圍繞給定事實(本機確認為真實執行,非 skip)
.venv/bin/python -m scripts.evaluate → 12 案 45/45 不變
.venv/bin/python -m pip check → 乾淨
```

既有 37 核心 + 6 ACL + 6 session continuity + 2 legacy alert + 4 P1 multi-turn 測試全部維持通過,確定性層與 ACL/核准邊界沒有任何退化。

## 6. 真實手動驗證的完整紀錄(逐字保留,供稽核)

**第 1 輪**(`session_id=manual-verify-2`,`reply_source=llm_phrased`):
```
使用者：我想評估把馬達升級，但目前資料夠嗎？
session: {turn:1, previously_unresolved:[], now_resolved:[], still_unknown:['連續功率檢核'], status:'open'}
Agent（LLM 轉述）：
目前仍需管理者確認以下資訊才能繼續：
- 連續功率檢核因缺少授權或過期規格無法進行
建議補充：馬達啟動電流與驅動器峰值、電源降額與熱條件、新馬達尺寸與散熱空間驗證、採購與測試工期緩衝。
（請用相同session_id重新提交後續問題）
```

**第 2 輪**(同一 `session_id`,管理者已恢復授權,`reply_source=deterministic_template`,因為這次剛好沒有重新帶入允許使用本機 LLM 的旗標,展示了兩種來源都能正確運作):
```
使用者：管理者已經恢復授權了，請繼續分析
session: {turn:2, previously_unresolved:['連續功率檢核'], now_resolved:['連續功率檢核'], still_unknown:[], status:'closed'}
Agent（確定性模板）：
已確認解決：連續功率檢核。
已取得足夠且目前有效的授權資料完成本輪分析，詳見風險與方案；任何變更仍需人工審核後才能執行。
```

## 7. 已知限制(誠實記錄,不誇大完成度)

- **NLU 仍非常有限**:`focus`(要分析哪個固定根節點)目前還是由前端下拉選單或呼叫端直接指定,LLM 不負責把自由文字映射到正確的 `focus`。這是刻意的範圍控制(映射到固定根節點集合如果交給 LLM 判斷,等於讓 LLM 間接影響分析走哪條確定性路徑,风险超出這次最小里程碑想承擔的範圍),留給下一個里程碑討論是否要做、以及怎麼做才安全(例如:限制 LLM 只能從 `FOCUS_ROOTS` 這個封閉集合裡選,而不是自由生成)。
- **使用者在對話裡提供的「補充數值」本身不會被系統吸收**:如果使用者在聊天框打「啟動電流大概 15A」,這段話只會被當作下一輪 `analyze()` 的 `question` 文字(影響檢索關鍵字),**不會**被寫進 `facts` 表或改變任何確定性計算——必須由管理者透過既有的 `PATCH /facts/{key}` 或文件更新端點正式登錄後,才算數。這是刻意維持「LLM 不做授權、不做數學」的結果,不是疏漏。
- **沒有使用 LangGraph 的 `interrupt/resume`**:原因與 P1 相同(見 `ai_progress/50_P1_IMPLEMENTATION.md` 第 1 節),這次也沒有改變這個決定。
- **LLM 回覆品質未經系統性評估**:只做了端到端的「有沒有真的執行、有沒有維持語意一致」驗證,沒有對 `qwen3:8b` 的轉述品質做大規模評測,維持原專案一貫的保守用詞(README 已多次聲明 LLM 文字為「未驗證文字」)。
- 沒有展開 P2–P5,沒有新增與本次授權無關的架構;Podman 仍未安裝、未授權,維持獨立待辦。

## 8. 下一步建議(給使用者參考,非已核准計畫)

1. 若要讓 Agent 真的能聽懂自由文字決定分析哪個 `focus`,建議先做「LLM 只能從 `FOCUS_ROOTS` 封閉集合選一個」這種受限版本,而不是開放式生成。
2. 考慮讓管理者能在聊天介面裡,對 Agent 提出的追問直接完成文件/事實的核准動作(目前仍需切換到既有的「資料與證據」頁面操作)。
3. 需要時可以對 `qwen3:8b` 的轉述品質做更系統性的人工評測。
