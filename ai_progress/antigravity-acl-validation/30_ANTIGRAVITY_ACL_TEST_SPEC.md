# RiskScope v0.1 ACL 回歸測試規範與基準驗證紀錄

- **文件路徑**: `ai_progress/antigravity-acl-validation/30_ANTIGRAVITY_ACL_TEST_SPEC.md`
- **負責代理**: Antigravity (副手 AI)
- **更新時間**: 2026-10-18 21:04 (Local Time)
- **專案位置**: `/Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent`

---

## 一、背景與接管狀態

依據使用者緊急接管指令：
1. **Codex** 額度耗盡暫停，原有測試腳本與技術報告保留。
2. **Claude** 接管核心程式碼修復 (`app/api.py` 與 `app/events.py`)。
3. **Antigravity** 負責獨立測試、測試案例補強與品質把關，嚴格恪守不修改 `app/` 代碼。

---

## 二、全面補強之回歸測試清單 (`tests/test_acl_regression.py`)

測試套件已擴充為包含 6 個針對性案例，涵蓋細粒度權限邊界：

| 測試案例名稱 | 驗證場景與安全邊界 | 未修復基準表現 | 預期修復後驗收標準 |
|---|---|---|---|
| `test_stored_analysis_detail_and_list_blocked_on_fact_evidence_revocation` | **缺口 A (規格證據)**：額外文件將 `DOC-PS` 擠出 top-8 檢索後，撤銷 `DOC-PS` 權限。驗證 `GET /analyses/{id}` 回傳 403 且不洩漏規格與數值（240 W, 10 A）；驗證 `GET /analyses` 列表排除此分析。 | ❌ FAILED (回傳 200 並洩漏 DOC-PS 與衍生數值) | ✅ HTTP 403 Forbidden，列表排除此 ID |
| `test_stored_analysis_detail_blocked_on_impact_path_evidence_revocation` | **缺口 A (影響路徑)**：供應商分析無 `checks`，僅依賴路徑帶有 `DOC-PLAN`。撤銷 `DOC-PLAN` 權限後，驗證詳情端點拒絕存取（403），防止路徑洩漏。 | ❌ FAILED (回傳 200 並洩漏 DOC-PLAN) | ✅ HTTP 403 Forbidden，不洩漏 DOC-PLAN |
| `test_alerts_endpoint_respects_acl_when_revoked_after_event_creation` | **缺口 B (先建後撤)**：事件先由 Manager 觸發並持久化提醒，之後撤銷工程師供應鏈文件權限。驗證工程師 `GET /alerts` 不洩漏 `PROCURE-01`, `ASSEMBLY-01` 等受保護衍生節點。 | ❌ FAILED (提醒內容洩漏 PROCURE-01) | ✅ 提醒內容過濾受保護節點或安全隱藏 |
| `test_alerts_endpoint_respects_acl_when_revoked_before_event_creation` | **缺口 B (先撤後建)**：工程師供應鏈權限先被撤銷，Manager 隨後觸發事件。驗證工程師 `GET /alerts` 不洩漏受保護衍生節點。 | ❌ FAILED (提醒內容洩漏 PROCURE-01) | ✅ 提醒內容過濾受保護節點或安全隱藏 |
| `test_manager_retains_full_legitimate_access_to_all_features` | **守護性測試 (Manager 權限)**：驗證修復不會過度封鎖管理者。Manager 存取分析詳情、列表及包含衍生節點之完整提醒皆正常 (200 OK)。 | ✅ PASSED (未修復即具備合法存取) | ✅ 保持 PASSED (功能不受破壞) |
| `test_legitimate_authorized_engineer_features_unimpaired` | **守護性測試 (合法工程師)**：驗證工程師對具備權限之文件執行分析、重讀分析及讀取列表功能正常，無誤殺。 | ✅ PASSED (合法工作流程順暢) | ✅ 保持 PASSED (功能不受破壞) |

---

## 三、未修復前之基準執行紀錄

執行命令：
```bash
.venv/bin/pytest tests/test_acl_regression.py
```

執行結果摘要：
- **Total collected**: 6 items
- **Passed**: 2 passed (Manager 與合法工程師基準通過)
- **Failed**: 4 failed (4 項安全缺口精確被斷言攔截)
- **詳細執行 Log**: 已完整記錄於 `ai_progress/antigravity-acl-validation/baseline-test-run.log`

---

## 四、交接給 Claude 與後續驗收準備

1. **已就緒資源**：
   - `tests/test_acl_regression.py` 可直接作為 Claude 修復時之本地 TDD 驗證依據。
   - `tests/test_core.py` 37 項既有測試作為無破壞性回歸基準。
2. **待 Claude 完成修復後之驗收流程**：
   - Antigravity 將第一時間執行：
     ```bash
     .venv/bin/pytest tests/test_core.py tests/test_acl_regression.py
     python -m scripts.evaluate
     ```
   - 驗收標準：43 項測試全數通過（37 existing + 6 new regression），12 案評估維持 45/45。
