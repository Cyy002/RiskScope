# init_db 憑證隔離：獨立複驗失敗（P1）

日期：2026-10-20。Claude 的修正確實存在於 `app/db.py:169`，但只避開「不同目錄」情境，仍有同目錄碰撞。

已通過 **4 個不同案例**：Claude 原有 `tests/test_db_credentials_isolation.py` 的3項，加上獨立檢查明確憑證路徑的 Token 雜湊符合對應帳號、重複初始化保留兩個資料庫與憑證的1項。共 **1 個案例失敗**：非預設資料庫與預設資料庫位於同一目錄。

最小重現（所有路徑均為臨時資料）：
1. 預設 DB=`temporary/default.sqlite3`，憑證=`temporary/demo_credentials.json`，先正常初始化。
2. 呼叫 `init_db(temporary/other.sqlite3)`，不指定 `credentials_path`。
3. 修正目前使用 `Path(path).resolve().parent / CREDENTIALS_PATH.name`，推導結果仍是原本的 `temporary/demo_credentials.json`。
4. 預設 DB 的帳號雜湊不變，憑證檔已被新 DB 的 Token 覆寫，且不再匹配預設 DB。

證據：`credential-collision.json` 的 `default_database_user_hashes_unchanged=true`、`default_credentials_unchanged=false`、`credential_file_matches_default_accounts=false`；`credential-repro.txt` 為必要的不洩漏憑證內容之失敗紀錄。此失敗案例亦重現於8項ACL案例一起執行的 `independent-tests.txt`，沒有降低斷言或標成 xfail。

**需要 Claude 修正。** 建議為非預設 DB 使用不碰撞的個別憑證路徑，或偵測路徑碰撞時在建立／寫入前拒絕並要求明確指定獨立路徑；保留預設 DB 初始化及明確指定路徑的既有行為。加入同目錄兩個 DB 的回歸案例，不以改到不同子目錄規避失敗。不得以重建預設 DB 或實際輪替 Token 修復本案例。

安全範圍：全部 DB 與憑證均為新臨時檔案，guard 拒絕任何正式 runtime 開啟與隔離目錄外 SQLite 連線，實際違規嘗試為0。未讀取、初始化或覆寫正式 runtime／Token，未修改核心程式。

重跑：
```sh
.venv/bin/python -B ai_progress/codex-review-reverify/run_isolated.py ai_progress/codex-review-reverify/test_independent.py::test_second_database_in_same_directory_cannot_replace_default_credentials
```

本輪共20個不同案例：Session 15通過；init_db 4通過、1失敗。僅執行既有針對性測試及以上必要補充，未跑完整pytest或45項評估；其他LLM安全缺口、Podman與Token輪替均未處理。兩項複驗已結束，停止新增工作，待Claude正式修正。
