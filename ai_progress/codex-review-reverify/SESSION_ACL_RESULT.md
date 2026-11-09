# Session 歷史 ACL：獨立複驗通過

日期：2026-10-20。範圍為目前磁碟程式碼與隔離測試，不代表已部署容器已更新。

- 已確認 `app/api.py:137` 的 Session 讀取逐輪透過 `_result_source_ids()` 與當前 `document_permitted()` 重檢來源；撤權回覆為 `reply=null`、`reply_source=null`、`redacted=true`。`app/static/app.js:69` 已顯示遮蔽訊息。
- 重跑既有 `tests/test_session_continuity.py`：**7 通過**。包含撤 DOC-PS 後分析 403、歷史遮蔽、manager 正常可讀，以及缺資訊後恢復授權、同 Session 接續、來源版本變更與人工核准保護。
- 新增獨立 **8 通過**：確定性摘要／mocked Ollama 回覆 × DOC-PS／DOC-MOTOR／DOC-AUX／DOC-PLAN；用既有 distractor fixture 把來源排除在檢索前八筆之外，驗證工程與依賴路徑證據均受到保護。撤銷任一來源即遮蔽，整份歷史 JSON 不含原回覆或264；manager 可讀、outsider 403、恢復授權後可重新讀取。
- 共 **15 個不同案例通過**；未在本輪測試範圍發現殘留歷史回覆外洩。LLM 文字使用 HTTP mock，這次驗證的是歷史 ACL，不重測模型生成品質。
- SQLite 連線有臨時目錄防護；對專案正式 runtime 的檔案開啟會直接拒絕，實際嘗試數為 0。無正式 Token 輸出或讀取，無核心修改。

證據：`existing-tests.txt`、`independent-tests.txt`、`isolation-existing.json` 與 `test_independent.py`（同目錄）。目前本項不需 Claude 再修改。

重跑：
```sh
.venv/bin/python -B ai_progress/codex-review-reverify/run_isolated.py tests/test_session_continuity.py
.venv/bin/python -B ai_progress/codex-review-reverify/run_isolated.py ai_progress/codex-review-reverify/test_independent.py -k history
```
