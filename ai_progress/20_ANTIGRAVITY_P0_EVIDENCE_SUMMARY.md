# RiskScope v0.1 P0 驗證證據彙整與回歸測試準備報告

- **文件路徑**: `ai_progress/20_ANTIGRAVITY_P0_EVIDENCE_SUMMARY.md`
- **彙整代理**: Antigravity (副手 AI)
- **更新時間**: 2026-10-18 20:56 (Local Time)
- **專案路徑**: `/Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent`

---

## 一、雙主力 AI 驗證證據彙整矩陣

| 驗證項目 | Codex 實測結論與證據 | Claude 實測結論與證據 | 綜合評估 |
|---|---|---|---|
| **既有核心測試** | 37 passed (`pytest -q`)<br>證據: `codex-p0/pytest-existing-env.log` | 37 passed<br>證據: 聊天室實時回報與 probes | ✅ 通過 (未改核心代碼) |
| **LangGraph 執行路徑** | 真正執行 `orchestration="langgraph"`<br>指定工況 11 A / 264 W, 方案 A blocked<br>證據: `codex-p0/application-probes.json` | 真正執行 `orchestration="langgraph"`<br>相同工況與決策狀態<br>證據: `claude-p0/application-probes.json` | ✅ 通過 (非 sequential_fallback) |
| **固定 12 案基準評估** | 多層路徑 45/45 (Recall 100%, Precision 100%)<br>證據: `codex-p0/evaluation.json` | 45/45 (Recall 100%, Precision 100%)<br>證據: `claude-p0/evaluation.json` | ✅ 通過 (符合原合成圖評估標準) |
| **Mac Podman 部署** | 指出環境缺乏 Podman<br>報告於 `10_CODEX_P0_APPLICATION.md` | 指出 Mac 缺少 Podman/Docker/Homebrew，等待使用者授權<br>聊天室明確回報 | ⚠️ 阻擋 (等待環境準備/授權) |
| **缺口 A: 歷史分析 ACL** | **獨立重現成功** (`finding_reproduced=true`)<br>證據: `codex-p0/application-probes.json` | **獨立重現成功** (`finding_reproduced=true`)<br>證據: `claude-p0/application-probes.json` | 🔴 確認漏洞 (未涵蓋在原 37 測試中) |
| **缺口 B: 提醒事件 ACL** | **獨立重現成功** (`finding_reproduced=true`)<br>證據: `codex-p0/application-probes.json` | **獨立重現成功** (`finding_reproduced=true`)<br>證據: `claude-p0/application-probes.json` | 🔴 確認漏洞 (未涵蓋在原 37 測試中) |

---

## 二、兩項 ACL 漏洞之技術成因剖析

### 1. 缺口 A：歷史分析紀錄讀取時未檢核非 top-8 檢索之工具證據來源 (`stored_analysis_acl_gap`)
- **漏洞位置**: `app/api.py:134-143` (`_analysis_access`)
- **根因分析**: 
  - `_analysis_access` 僅走訪 `result.get('documents', [])` 比對 `document_permitted`。
  - 當系統存在超過 8 份文件時，檢索模組 (`app/analyzer.py:64`) 僅取前 8 筆放入 `result['documents']`。
  - 確定性工具所使用之來源（如 `DOC-PS`）雖未列入 top-8 `documents`，但其數據被寫入 `checks[].evidence` 與 `tool_calls`。
  - 當管理者撤銷工程師對 `DOC-PS` 授權後，新分析與即時 check 皆回傳 `unknown`，但舊分析之 `GET /analyses/{id}` 卻因 `DOC-PS` 不在 `result['documents']` 而判定通過（HTTP 200），洩漏機密規格。

### 2. 缺口 B：專案提醒 API 未依讀者權限過濾事件影響衍生節點 (`alert_acl_gap`)
- **漏洞位置**: `app/api.py:208-212` (`alerts`) 與 `app/events.py:69`
- **根因分析**:
  - `alerts` endpoint 僅呼叫 `require_role(c, actor, project)` 檢驗專案角色，即無條件回傳全專案所有提醒內容。
  - 管理者觸發變更事件（如供應商交期變更）時，提醒內容包含由 `DOC-SUPPLIER` 與 `DOC-PLAN` 推導之受影響節點（如 `PROCURE-01`, `ASSEMBLY-01`）。
  - 已被撤銷供應鏈文件權限之工程師，雖查詢 `/impact/SUPPLIER-01` 為空，但透過 `GET /alerts` 仍可直接讀取受保護衍生節點名稱與關聯細節。

---

## 三、回歸測試套件準備實施情況

副手 AI 已在不更動核心業務代碼 (`app/`) 的前提下，建構標準化自動化回歸測試檔：
- **檔案路徑**: `tests/test_acl_regression.py`
- **包含測試案例**:
  1. `test_stored_analysis_acl_must_check_tool_evidence_sources`
  2. `test_alerts_endpoint_must_respect_reader_document_acl`
- **實測執行命令與現況**:
  ```bash
  .venv/bin/pytest tests/test_acl_regression.py
  ```
  - 執行結果：`2 failed in 0.15s`
  - 驗證說明：測試案例完全重現兩個安全斷言失敗，確認測試標的之有效性；待雙主力完成修正後，將以此測試作為最終綠燈驗收標準。
- **既有測試回歸確認**:
  ```bash
  .venv/bin/pytest tests/test_core.py
  ```
  - 執行結果：`37 passed, 2 warnings in 0.47s`（原功能完全不受干擾）。

---

## 四、互不衝突之並行修正任務拆分建議（供 Copilot 派工）

依據使用者「雙主力互助、避免修改相同檔案」之原則，建議分工如下：

1. **模組一（歷史分析來源鑑別）**：分配給 **Codex**
   - **負責檔案**: `app/api.py` 的 `_analysis_access` 函數（第 134-143 行）
   - **目標**: 遍歷 `result` 中所有的依賴來源（包含 `result.get('documents')`、`checks` 內所有 `evidence.source_id` 及 `tool_calls` Provenance），只要任一來源已遭撤權即拒絕讀取（HTTP 403）或精確脫敏。
2. **模組二（提醒事件讀取授權過濾）**：分配給 **Claude**
   - **負責檔案**: `app/api.py` 的 `alerts` endpoint（第 208-212 行）與 `app/events.py`
   - **目標**: 為提醒紀錄綁定來源檔案關聯或在讀取端依當前使用者之文件 ACL 動態過濾衍生節點字串，防止跨權限洩漏。
3. **交叉驗收與最終回歸**：
   - Claude 審查 Codex 對 `_analysis_access` 之修正；
   - Codex 審查 Claude 對 `alerts` 之修正；
   - 由 Antigravity 執行完整回歸測試：
     ```bash
     .venv/bin/pytest tests/test_core.py tests/test_acl_regression.py
     ```
