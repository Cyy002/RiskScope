# M12.1：/analyze 本機模型輸出獨立安全複驗

2026-10-21，Codex。僅審查這一條路徑；未修改產品或既有測試，未重新審查 M12 其他修復。

**結論：確認 P1 文字可信度缺口，需要 Claude 修復。** `/analyze(use_local_llm=true)` 不呼叫 M7 或等效驗證；以 `generated_unverified` 加警告後，仍回傳並保存無依據文字。相同文字在目前 `/chat` 會被 M7 拒絕。這不是已證實的 ACL 洩漏或實際核准／執行權限繞過。

## 實際路徑與受影響範圍

- `app/api.py:132` 的 `analyze_route` 將旗標傳給 `analyze()`。
- `app/analyzer.py:376` 呼叫 `_safe_local_explanation()`；`:59–75` 只呼叫模型、截取 1800 字及加警告，沒有可信度驗證。
- 結果中的 `local_llm.text` 寫入 `analyses.result_json`，呼叫者能從分析詳情 API 再次取得原文。
- 對照 `app/chat.py:888` 明確呼叫 `_reply_is_trustworthy()`，拒絕後回退確定性模板。
- 現有前端 `renderAnalysis` 未直接渲染 `local_llm.text`；匯出分析 JSON 會序列化整個結果（靜態讀碼）。本輪**沒有 GUI 實測，不能宣稱畫面已展示假核准**。

## 最小重現

使用 `tests/conftest.py` 的臨時 DB／臨時帳號，mock `app.llm_client.call_ollama` 回覆 `TEST-01 已核准，可以立即執行。`，設定本機端點閘門但禁止實際連線。

```json
POST /api/projects/demo-chamber/analyze
{
  "question": "請分析供應商交期與品質驗證風險。",
  "focus": "supplier",
  "session_id": "approval-analyze",
  "use_local_llm": true
}
```

隔離帳號正常認證後，回 HTTP 200：

```json
{
  "local_llm": {
    "status": "generated_unverified",
    "text": "TEST-01 已核准，可以立即執行。",
    "warning": "模型文字僅供參考，不作為規格事實或批准依據"
  }
}
```

M7 spy 呼叫次數為 0；GET 分析詳情仍含此原文。相同 mock 用於 `/chat` 時，M7 呼叫 1 次、診斷為 `rejected_inconsistent`，回覆使用 `deterministic_template`。

## 單次測試結果

| 模型故障注入 | /analyze | /chat |
|---|---|---|
| TEST-01 已核准，可以立即執行 | 原文回傳與保存 | 拒絕 |
| 供應商將延誤12天（既有公開訊號為7） | 原文回傳與保存 | 拒絕 |
| 新增成本5000元 | 原文回傳與保存 | 拒絕 |
| 延誤機率30% | 原文回傳與保存 | 拒絕 |
| 品質驗證已完成（test_pass=unknown） | 原文回傳與保存 | 拒絕 |
| 99A／24W（與確定性計算矛盾） | 原文回傳與保存 | 拒絕 |

**8 項：6 failed、2 passed、0 errors，pytest 0.40 秒；僅執行一次。** 六個 failed 是「不應輸出無依據文字」的驗收斷言，對照 API、資料不變及 /chat 拒絕斷言都已通過。不是六個不同根因，也不是全套測試結果。

兩個控制案例通過：

1. 有來源的 7 天可輸出；同一 Session 第二輪正常延續，`turn=2`。
2. outsider 在模型呼叫前得到 403；私有 DOC-CONF 不進工程師 Prompt；他人不能沿用 Session；文件撤權後舊分析詳情 403、歷史遮蔽、新分析排除對應文件及依賴；成員資格撤銷後新分析與歷史均 403。

六種注入下，啟用／停用模型的 facts、checks、options、unknowns、impacts、decision_status 一致。臨時 DB 的 facts、project_signals、actions、simulated_tasks 前後一致；沒有因模型文字而實際核准、執行或回寫正式事實。模型原文只污染可讀分析紀錄的文字欄位。

## 給 Claude 的最小修復建議

1. 在 `analyze()` 取得模型文字後、放入結果及保存前，**重用同一個** `_reply_is_trustworthy(text, full_result, conn, project, session_id, question)`。必須傳完整 checks／facts 等資料；現在的 `known` 子集合沒有 checks，不能直接拿它當完整驗證上下文。
2. 拒絕時移除不可信 `text`，回明確的 rejection 狀態／非敏感原因，保留既有確定性分析。不要將被拒原文寫進 result_json；不要僅加第二段警告。
3. 模組目前 `chat` 匯入 `analyzer`，避免新增頂層循環匯入。最小方案可在執行點局部匯入同一驗證器；若抽出共用模組，應僅搬移既有規則，避免建立第二套驗證邏輯或大型重構。
4. 缺少 session 時，核准宣稱應維持 fail-closed；有 session 時仍沿用 M7.1 的 session＋task 關聯，不因 `/analyze` 而放寬。
5. 既有生成成功狀態也不得暗示新推論已驗證。處理來源格式／量值的品質仍取決於共用 M7 本身；本輪不擴張重查其全部規則。

可先原樣重跑本次六個負例、7天正例及 ACL／Session 控制，再補「無 session 假核准拒絕」「合法有依據工程數值放行」「模型不可用保留確定性結果」的小型修復回歸。這三項為後續建議，非本輪已執行結果。

## 證據與重跑方式

```sh
.venv/bin/python ai_progress/codex-review-m121-analyze/run_isolated.py \
  ai_progress/codex-review-m121-analyze/review_probes.py
```

- `review_probes.py`：可獨立重現，未修改前輪 `codex-review-m12` 證據；不以 test_ 命名，避免一般 pytest 自動收集審查探針。
- `observations.json`：兩條 API 的輸出、診斷、M7 次數與資料不變比較。
- `test-results.txt`／`results.xml`：本次原始結果。
- `isolation.json`：8 個臨時 DB；正式 runtime／隔離區外 SQLite／實際網路存取攔截嘗試皆為 0；受檢產品與 fixture 雜湊前後不變。

此命令會更新同目錄測試輸出；原始證據已打包保存，修復後建議另存輸出以保留前後對照。

沒有讀取正式 Token、資料庫或 Volume，沒有操作 Podman，沒有呼叫真實模型，也沒有修改共用 `00_STATUS.md`／`60_NEXT_HANDOFF.md`，避免與 Claude 同時整合；請 Claude 將本結論併入 M12.1 最終交接。**Codex 指定複驗已完成，保存後停止；產品修復與真實 27B GUI 驗收由 Claude 負責。**
