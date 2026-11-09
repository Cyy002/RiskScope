# P1 第一個里程碑 — 最終驗收紀錄

執行者：Claude。時間：2026-10-18 23:05(Asia/Taipei)。

**為什麼由 Claude 一人完成驗收,不是三方分開驗收**:使用者本來指派 Antigravity 修測試、Copilot 整合驗收。但 Antigravity 在處理前觸及使用額度上限(重置還需 165 小時),Copilot 這次執行環境持續無法寫入專案檔案(多次回報「遭權限拒絕」)。使用者在確認這個狀況後直接訊息「大家用量都見底了,後續你接著繼續完成」,明確授權 Claude 接手剩下的工作,不是 Claude 自行決定跳過其他人的角色。

## 1. 驗收標準逐項對照(使用者「P1 驗收分歧處理與安全性收尾指令」第四節)

| 標準 | 結果 | 證據 |
|---|---|---|
| 所有既有測試維持通過 | ✅ | `tests/test_core.py` 37/37、`tests/test_acl_regression.py` 6/6 |
| 三項 P1 失敗測試經過需求核對後合理修正 | ✅ | 見第 2 節,改的是測試的場景/API 用法,不是放寬斷言 |
| 全套 pytest 達到 0 failed | ✅ | **55 passed, 0 failed** |
| 真正執行 Session 多輪流程,確認狀態能延續 | ✅ | `tests/test_session_continuity.py` 6/6 + `tests/test_p1_multi_turn.py` 情境 1 |
| 新舊 ACL 權限防護不得退化 | ✅ | `tests/test_acl_regression.py` 6/6 + `tests/test_legacy_alert_safety.py` 2/2(舊提醒收尾) |
| 人工核准和 Actions 流程不得被繞過 | ✅ | `tests/test_p1_multi_turn.py` 情境 2、3 改用真實 Actions 契約驗證,並與 `tests/test_session_continuity.py` 的核准測試交叉確認 |
| 記錄實際執行命令、測試輸出及未解決限制 | ✅ | 本文件第 3、4 節 |

## 2. 三項分歧的實際處理方式(不是降低測試強度換來的 0 failed)

### 情境 1 — 場景沒有真正造成資料缺漏

原測試對預設種子資料(5 個規格事實全部存在且 engineer 有權限)問一個一般問題,卻斷言 `unknowns` 必須出現特定字樣。預設資料下系統正確算出確定的 pass/fail,不應該謊稱「不知道」。**修正方式**:在呼叫 `/analyze` 前先用 `PATCH /documents/DOC-PS/access` 撤銷 engineer 的存取權,製造真實的資料缺漏,其餘斷言不變。這樣測試驗證的是系統「真的缺資料時會不會誠實回報」,而不是「能不能被誘導講出特定字串」。

### 情境 2、3 — 假設了不存在的 Actions API

原測試假設 `PATCH /actions/{id}` 搭配 `{"status":"approved"}`、`POST /actions` 搭配 `title`/`task_key`/`delta` 欄位。核對 `app/actions.py`/`app/api.py` 後確認:這套 API 從未存在,真正的、已經被 `tests/test_core.py` 多次驗證的契約是:

```
POST /actions          {analysis_id, task_id, new_state, idempotency_key}  -> 建立 pending
POST /actions/{id}/review   {approve: bool}                                -> manager 專屬
POST /actions/{id}/execute                                                 -> manager 專屬
```

「未授權操作不得執行」(engineer 自我核准要擋、未核准不能執行)和「資料版本過期要擋下」(審核/執行時重新比對 `project_revision`,過期轉 `stale`)**都是已經存在且已測試的功能**,不是產品缺口。**修正方式**:把兩個情境改寫成呼叫真實的三段式 API,並加上 `session_id` 讓它們同時驗證「P1 的多輪對話脈絡裡,核准流程依然不能被跳過」這個使用者原本想測的重點。沒有在 `app/` 新增任何平行的 Actions 介面。

## 3. 最終執行證據

```sh
.venv/bin/python -m pytest -q
→ 55 passed, 0 failed
   tests/test_core.py                 37/37
   tests/test_acl_regression.py        6/6
   tests/test_session_continuity.py    6/6
   tests/test_legacy_alert_safety.py   2/2
   tests/test_p1_multi_turn.py         4/4

.venv/bin/python -m scripts.evaluate   → 12 案 45/45(不變)
.venv/bin/python -m pip check           → No broken requirements found
```

## 4. 未解決限制(誠實記錄,不誇大)

- **Podman 部署**:本機沒有 `podman`/`docker`/`brew`,未經授權不會安裝,維持獨立 P0 待辦。
- **Antigravity 的獨立複核缺席**:這次 `tests/test_p1_multi_turn.py` 的修正是 Claude 自己做的,原本該由 Antigravity 獨立處理測試、Copilot 整合驗收的分工沒有真正發生——是在兩人都無法動作、使用者直接授權後才由 Claude 一人完成。等 Antigravity 額度恢復、Copilot 環境權限問題解決後,建議兩人回頭讀本文件 + `tests/test_p1_multi_turn.py` 開頭的修改說明,複核這次的測試修正是否合理,而不是預設它一定正確。
- **P1 範圍本身的既有限制**(非本輪新增):多輪延續是「記住上一輪缺什麼、這輪解決了沒有」的最小版本,不是自由對話;沒有使用 LangGraph `interrupt/resume`;`questions_to_manager` 目前仍每輪重新產生,沒有跨輪去重。詳見 `ai_progress/50_P1_IMPLEMENTATION.md` 第 7 節。
- 沒有展開 P2–P5,沒有新增與本次授權無關的架構。
