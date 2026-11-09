# RiskScope v0.1 — Claude ACL 缺口修正報告

執行者：Claude。日期：2026-10-18（Asia/Taipei）。授權：使用者直接指令,接管兩項已確認的 ACL 漏洞修正(Codex 額度耗盡期間)。
共用專案：`/Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent`

根因分析見 `ai_progress/claude-p0/11_CLAUDE_ACL_REVIEW.md`(修正前的獨立複核)。本報告記錄實際程式修改、測試證據與驗收結果。

## 1. 變更清單

| 檔案 | 變更內容 |
|---|---|
| `app/api.py` | `_analysis_access` 新增 `_result_source_ids()` helper,改為收集 `documents`、`sources`、`checks[].evidence[].source_id`、`impacts[].paths[].evidence[].source_id` 全部來源,任何一個被撤權就整筆 403。新增 `_alert_view()`,`/alerts` 改為逐筆依讀者目前權限重新過濾受影響節點後才回傳。 |
| `app/impact.py` | 新增 `node_source_requirements(impact)`:將 `trace_impact` 的 `paths` 依終點節點分組,存成「每個節點的多組(OR)、組內多個 source_id(AND)」需求快照,供建立時間點與讀取時間點共用同一套「全有或全無」判斷邏輯。 |
| `app/events.py` | `simulate_event` 不再把受影響節點名稱直接拼進 `alerts.body` 的靜態文字;改成呼叫 `node_source_requirements()` 存進新欄位 `node_sources_json`,`body` 只保留不含節點名稱的事件描述。 |
| `app/db.py` | `alerts` 表新增欄位 `node_sources_json TEXT NOT NULL DEFAULT '{}'`;`init_db` 增加 `ALTER TABLE ... ADD COLUMN`(包 try/except `sqlite3.OperationalError`)確保既有 runtime 資料庫也能拿到這個欄位,不需手動重置。 |

未修改:`app/analyzer.py`、`app/engineering.py`、`app/retrieval.py`、`app/security.py`、`app/actions.py`、前端靜態檔案。沒有做無關的架構重構,兩項修正都只動了必要的讀取路徑。

## 2. 任務 A:歷史分析 ACL — 修正後行為

- `_analysis_access` 現在對每筆分析收集全部來源(含工具證據、影響路徑證據),任一來源被撤權即整筆拒絕(403),不會嘗試移除個別欄位後假裝安全(避免殘留衍生數值,如 10 A/240 W)。
- `GET /analyses/{id}` 與 `GET /analyses`(列表)共用同一個檢查函式;列表遇到被撤權的分析會直接從清單剔除,不會洩漏其存在。
- `document_permitted` 本身對 manager/engineer 一視同仁(依 `document_access` 表逐使用者判斷),與既有 `retrieval.py`/`engineering.py`/`impact.py` 的 ACL 語意完全一致,不會意外放寬或收緊 manager 的既有權限。

## 3. 任務 B:提醒事件 ACL — 修正後行為

- 受影響節點不再於**建立事件時**用創建者(通常是 manager)的 ACL 視角算完就寫死成文字;改成存「每個節點需要哪些來源文件授權才算驗證」的快照(`node_sources_json`)。
- `GET /alerts` 讀取時,對每筆提醒,用**當前讀者**現在的 `document_permitted` 結果重新過濾快照,只顯示讀者目前仍有權限的節點;被隱藏的節點數量會標註(不是完全消音,也不是假裝沒有風險)。
- 這個設計不依賴即時依賴圖重算(避免歷史結果因依賴圖之後變動而改變,保留稽核一致性),也不套用 `_analysis_access` 的「只有本人或 manager 能讀」限制(否則工程師會連自己本來有權限看的提醒都看不到)。
- 沒有快照(`node_sources_json` 為空,例如升級前就存在的舊提醒,或該次分析本身沒有任何依賴節點)時,採保守處理:不額外顯示任何節點清單,只保留原始事件描述(signal_key/數值變化),不會把舊資料當作「已驗證可顯示」而外露。
- Manager 仍可看到完整節點清單(因為 manager 對 DOC-SUPPLIER/DOC-PLAN 等文件預設有權限,`document_permitted` 對它們回傳 true),既有合法使用情境不受影響。

## 4. 測試證據

```sh
.venv/bin/python -m pip check                        # No broken requirements found.
.venv/bin/python -m pytest -q                         # 43 passed(37 既有 + 6 項 Antigravity 的 ACL 回歸測試)
.venv/bin/python -B ai_progress/codex-p0/verify_application.py ai_progress/claude-acl-fix
```

- `pytest -q`:**43 passed**,無新增失敗、無被跳過的測試。既有 37 項與 `tests/test_acl_regression.py` 的 6 項(涵蓋:fact evidence 撤權 403+不洩漏數值、impact path evidence 撤權 403、提醒先建立後撤權、提醒先撤權後建立、manager 完整視角不受影響、授權 engineer 正常功能不受影響)全部通過。
- 重跑 Codex 原始重現腳本 `codex-p0/verify_application.py`(輸出導向 `ai_progress/claude-acl-fix/`,不覆寫 Codex/我自己先前的紀錄):
  - `stored_analysis_acl_gap.finding_reproduced`:**true → false**;`stored_analysis_http_status` 從 200 變成 **403**。
  - `alert_acl_gap.finding_reproduced`:**true → false**;engineer 讀到的 alert body 變成「可能受影響節點：因目前來源權限不足無法顯示。」,不再出現 `PROCURE-01` 等受保護節點。
  - 完整輸出見本目錄 `application-probes.json`、`evaluation.json`(12 案仍 45/45,LangGraph 路徑未受影響)。

## 5. P0 驗收標準對照(使用者第八節要求)

| 項目 | 狀態 |
|---|---|
| 既有 37 項測試全部通過 | ✅ |
| 新增的 ACL 回歸測試全部通過 | ✅(Antigravity 的 6 項) |
| 原先兩項漏洞都不能再重現 | ✅(`finding_reproduced` 均為 false) |
| 歷史分析不會洩漏已撤權來源及衍生資訊 | ✅(整筆 403,不殘留數值) |
| 提醒事件不會讓使用者看到未授權資訊 | ✅(讀取時依目前 ACL 重過濾節點) |
| 正常授權的使用者仍能使用原有功能 | ✅(`test_manager_retains_full_legitimate_access_to_all_features`、`test_legitimate_authorized_engineer_features_unimpaired` 通過) |
| LangGraph 執行路徑未被破壞 | ✅(`orchestration=langgraph`、12 案 45/45 不變) |
| 每項修正有程式碼、測試結果及交接紀錄 | ✅(本報告 + 證據檔) |

Podman 部署仍未授權安裝,維持獨立待辦,未在本次變更範圍內觸碰任何系統層級操作。

## 6. 尚未處理的邊界(明確標註,不誇大完成度)

- ~~若有「升級前」就已存在、且 body 文字裡已經寫死受保護節點名稱的舊提醒資料…~~ **已於 2026-10-18 22:40 補上修正**,見 `ai_progress/50_P1_IMPLEMENTATION.md` 的「舊提醒安全收尾」一節與 `app/api.py` 的 `_LEGACY_NODE_CLAUSE`:讀取時偵測 `body` 是否含有只有修正前程式碼才會寫入的「可能受影響節點」字樣,且沒有 `node_sources_json` 快照可供重驗,一律遮蔽該段落,不碰資料庫本身。新增回歸測試 `tests/test_legacy_alert_safety.py`(2 項,皆通過)。
- 本次修正只涵蓋目前程式碼已知的四個來源管道(documents/sources/checks.evidence/impacts.paths.evidence);若未來新增其他會攜帶 source_id 的欄位,需要一併加入 `_result_source_ids()` 與 `node_source_requirements()` 的收集範圍。

## 7. 下一步

- 已請 Antigravity 用她自己持有的 `tests/test_acl_regression.py` 獨立重新驗收(本報告中的測試執行是我自己跑的,仍需要 Antigravity 從她的角度重新確認,避免自己寫、自己驗收就宣稱完成)。
- Codex 恢復額度後,請先讀本報告與 `ai_progress/codex-acl-design/` 的既有分析,再視情況做交叉審查,不需要重做。
