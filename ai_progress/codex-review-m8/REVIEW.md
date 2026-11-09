# M8 小範圍獨立審查 — 2026-10-20

結論：**部分完成，尚未通過 M8。** 只執行一次既有 M8 測試：**4 passed、2 failed**。未修改核心或既有測試，未讀取正式 Token，未操作正式 runtime、Podman 或模型。

## 已完成且實測通過

- `tests/test_m8_scenario_planning.py` 的 a–d 通過。替換馬達使用 11A，加既有輔助負載 3A 得 **14A／336W**；該案例的電源假設 8A 與文件額定 10A 對照，回覆包含 75%／40%。
- 新增輔助負載 2A 會累加至文件原有 3A，成為 5A；加馬達 8A 得 **13A／312W**。
- `added_value`／`added_unit` 遺漏在目前檔案中**已補上**：`app/engineering.py:107` 寫入、`:127` 傳入 evidence，`app/chat.py:373` 使用。實測新增案例回傳 `"2"`／`"A"`，沒有因欄位缺失中斷。
- 普通重述不覆蓋已授權文件；只提出馬達替換、未提供輔助負載且無來源權限時，結果保持 unknown。
- 新方案有 `proposed_change`／`verified:false` 標示，計算附文件 baseline；這不代表完整多輪流程完成。

## 確認問題與最小建議

### 1. 高：完成首輪後不能修正或追問（已實測）

`app/analyzer.py:183` 在沒有 unknowns 時將 Session 設為 closed；`:59`–`:60` 拒絕延續，回傳 409。M8 測試 e、f 的第一輪都為 200／closed，第二輪都為：

> 此對話已結束；請使用新的 session_id 開始新的對話

因此測試最後呈現 KeyError（缺少 checks／accepted 欄位），真正原因是前一步 HTTP 409。

這是**既有生命週期設計與 M8 需求衝突**，不是此次數值計算新增的偶發錯誤：`tests/test_session_continuity.py:70`、`:77` 原本明確要求完成即關閉、關閉後拒絕。前端 `app/static/app.js:62`、`:80`、`:84` 會沿用同一 ID，除非使用者按新對話；換 ID 又不會承接原 Session 暫存方案。

建議 Claude 優先區分「本輪分析完成」與「對話結束」，為聊天採明確的可延續政策，保留擁有者與每輪授權檢查。先決定如何保留既有 `/analyze` 關閉語意，再做最小修改；不要直接刪除舊測試或繞過 `_open_session`。M8 測試應先斷言第二輪 HTTP 200，再驗證內容。

### 2. 高：同句替換與新增的模式會互相污染（程式路徑確認，未另跑案例）

`app/chat.py:134`–`:138` 取數字前後各 20 字，先找「新增」才找「換成」，沒有依子句或元件綁定操作。

最小輸入：`馬達換成11A，新增2A輔助負載`。假設抽取器正確給出 motor=11A、aux=2A，11A 的視窗仍包含「新增」，所以馬達也被判為 add。依 `engineering.py:101`–`:106` 的分支會得到 `(8+11)+(3+2)=24A`，而正確替換情境是 `11+(3+2)=16A`。

建議先以子句／元件定位各數值所屬的操作；無法消除歧義時追問，不用全視窗固定優先序。後續補一個混合 replace/add 測試。本輪沒有執行此額外案例，不把以上推導當成 API 實測紀錄。

### 3. 高：原負載未知時，新增量被當成總量（程式路徑確認，未另跑案例）

`app/engineering.py:101` 只在原 fact 為 ok 時處理 add；若原 fact 為 missing／stale／unauthorized，會落到 `:115`–`:116`，直接把新增值當 `user_supplied` 的完整值，隨後 `:119` 不再視其為缺漏。

最小條件：原輔助負載未知，使用者只說新增 2A。現有分支會用 2A 作輔助負載總量；但「未知原量＋2A」應繼續 unknown。既有測試 d 只涵蓋「缺輔助負載、提出馬達替換」，未涵蓋這個 add 分支。

建議 add 缺基數時保留 unknown 並追問原負載，不能降級為完整補充值；已有經驗證的 Session 假設基數時，必須明確指定基數來源。後續補該分支的隔離測試。

## 未完成／尚未驗證

- 多輪方案修正及不重述條件的延續：兩個現有測試均失敗。
- 混合操作與缺基數新增：上述程式路徑有缺陷，待 Claude 修復並測試。
- 現有抽取測試全部 mock Ollama，文字回覆走確定性備援；不能由本結果宣稱真實模型抽取通過。
- 未驗收品質、成本、交期的完整方案比較；未複驗 M6／M7／M7.1 或其他既有安全里程碑。

## 本次測試與隔離證據

命令（本輪僅執行一次）：

```sh
.venv/bin/python -B ai_progress/codex-review-m8/run_targeted.py
```

Runner 只選取 `tests/test_m8_scenario_planning.py`，使用臨時目錄及既有 tmp_path fixture；在匯入應用程式前設定臨時 DB／憑證路徑，並禁止開啟正式 runtime、連接臨時目錄外的 SQLite 及外部網路。記錄到 6 個臨時資料庫、0 次受阻存取；查核來源檔案的執行前後 SHA256 一致。

- `pytest-m8.txt`：4 passed／2 failed；2 個警告為 anyio assertion rewrite 與 LangChain pending deprecation，未列為本輪缺陷。
- `test-evidence.json`：首輪／次輪狀態碼、合成計算與 proposed evidence、隔離結果及來源 SHA256；不含 Token。
- `run_targeted.py`：獨立診斷 runner，只新增在本審查目錄。

Claude 接續順序：先處理 Session 生命週期衝突，再修正操作綁定與 add 缺基數的處理，保留已完成的 added 欄位傳遞。Codex 本輪審查到此停止，沒有啟動其他 Agent。
