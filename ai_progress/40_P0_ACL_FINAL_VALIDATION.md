# RiskScope v0.1 — P0 ACL 安全修復獨立驗收報告

- **驗收代理**: Antigravity (副手工程師)
- **實施修復代理**: Claude (主力工程師)
- **驗收時間**: 2026-10-18 21:10 (Local Time)
- **專案路徑**: `/Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent`

---

## 一、驗收結論：✅ P0 ACL 安全漏洞全數修復通過

在未更動任何核心業務代碼的情況下，Antigravity 對 Claude 提交的修改進行了全覆蓋、多環境、端對端的獨立驗收。
結果確認：
1. **未修復前基準測試**：4 failed, 2 passed。
2. **修復後執行結果**：**6 passed, 0 failed**（`tests/test_acl_regression.py`）。
3. **既有核心測試**：**37 passed, 0 failed**（`tests/test_core.py`）。
4. **全套 pytest**：**43 passed in 0.53s**。
5. **固定 12 案基準評估**：多層路徑 **45/45 通過**（Recall 100%, Precision 100%）。
6. **Codex 邊界探測驗證**：4 大情境之 `finding_reproduced` 全數由 `true` 轉為 **`false`**。

---

## 二、修復細部驗證矩陣

| 驗證項目 | 測試案例 / 驗證指令 | 驗收結果 | 證據說明 |
|---|---|---|---|
| **缺口 A: 規格證據撤權** | `test_stored_analysis_detail_and_list_blocked_on_fact_evidence_revocation` | ✅ PASSED | `DOC-PS` 遭撤權後，`GET /analyses/{id}` 嚴格回傳 403 Forbidden；回傳內容不包含 `DOC-PS`、`240 W`、`10 A` 等機密數值；`GET /analyses` 列表自動排除此紀錄。 |
| **缺口 A: 影響路徑撤權** | `test_stored_analysis_detail_blocked_on_impact_path_evidence_revocation` | ✅ PASSED | 純影響路徑依賴（無 checks）情境下，`DOC-PLAN` 遭撤權後詳情端點嚴格拒絕存取（403 Forbidden）。 |
| **缺口 B: 先建提醒後撤權** | `test_alerts_endpoint_respects_acl_when_revoked_after_event_creation` | ✅ PASSED | 建立事件後撤銷工程師權限，工程師 `GET /alerts` 不洩漏 `PROCURE-01`、`ASSEMBLY-01` 等衍生受保護節點。 |
| **缺口 B: 先撤權後建提醒** | `test_alerts_endpoint_respects_acl_when_revoked_before_event_creation` | ✅ PASSED | 撤權後 Manager 建立的新事件，工程師查詢提醒同樣安全過濾。 |
| **Manager 正向權限** | `test_manager_retains_full_legitimate_access_to_all_features` | ✅ PASSED | 管理者保留全部合法存取權限（分析詳情、完整提醒節點清單正常），無誤殺。 |
| **合法工程師功能** | `test_legitimate_authorized_engineer_features_unimpaired` | ✅ PASSED | 具備合法授權之工程師進行分析、重讀與列表查詢均正常 (200 OK)。 |
| **既有功能與確定性檢核** | `tests/test_core.py` (37 案) | ✅ PASSED | 數值計算（11 A/264 W fail）、人工核准、冪等性、審計日誌完全正常。 |
| **合成圖遍歷評估** | `python -m scripts.evaluate` | ✅ PASSED | T01~T12 12 個固定案例多層遍歷 Precision/Recall 維持 100% (45/45)。 |
| **LangGraph 執行路徑** | API `/analyze` live probe | ✅ PASSED | 回傳 `orchestration="langgraph"`，未退化為 sequential fallback。 |

---

## 三、P0 未完成項目誠實登錄

- **Mac Podman 部署**：
  - 本機 macOS 環境目前缺少 `podman`、`docker` 與 `brew` 容器管理工具。
  - 恪守使用者指令，**未經授權不執行 sudo 安裝軟體或建立 VM**。
  - 此項維持獨立 P0 待辦，待使用者回機後評估授權。
