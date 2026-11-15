# Assignment 2 Submission Checklist (claude-b 版,2026-11-11;Claude A 封版更新)
AI 整理/驗證,非真人驗收（人工審查結果一節除外——那是使用者本人的真實判定）。

**更新（Claude A，封版）**：七題人工審查已由使用者本人完成（BB01/BB23 有條件接受、BB16 FAIL、
其餘 4 題 PASS），完整原話見 `HUMAN_REVIEW_DECISIONS.md`，彙整見 `HUMAN_REVIEW_FINAL_SUMMARY.md`
（簽核欄刻意留白，等待使用者本人簽名/日期，未被任何 Agent 填寫或代簽）。C.2 不再是待辦，移至
A 類。所有相關檔案已 commit，工作樹乾淨。

## A. 已完成且實測通過(macOS Apple Silicon)
- `pytest -q` → 306 passed(我於本輪重跑)。
- Podman:乾淨副本 `--no-cache` 建置 → `up` → `/health` → `smoke`(真實 Ollama qwen3:8b,容器經 host.containers.internal 連線)→ `down`/再 `up` 資料保存。
- 六項作業二功能:Safari 網頁真實點擊(登入、Agent 問答 14A/336W、檢核卡、方案/影響追蹤、engineer 申請 pending→manager 核准→執行→稽核紀錄)。
- 失敗案例(GUI):缺 Token、outsider 無專案權限;(API/測試)401/403/409/422、單位維度錯誤、注入題。
- 完整 Git 歷史憑證掃描:0 命中(本 repo)。
- **Podman Desktop(本輪新驗證)**:設定 `Path to Podman Binary` 後,Desktop 偵測到既有 VM;Containers 列出 3 個 RiskScope 容器、Images 列出 prof/teacher/1.0、Volumes 列出 3 個 riskscope_portable_* volume;`riskscope-portable-prof` 啟動後 Logs 顯示 `/health`、`/api/projects/demo-chamber/overview`、靜態檔 200 OK。證據:`evidence/screenshots/12–15_*.png`(新增,尚未提交)。未建立/重設任何 VM,未按 Set up。
- README 命令與 `deploy/riskscope.sh`(build/up/demo/smoke/restart-test/creds/down/purge)一致;`bash -n` 語法檢查通過;README/FINAL_STATUS 引用檔案皆存在。
- **七題人工審查（使用者本人逐題判定，完整對話記錄）**：BB02/BB07/BB10/BB13 PASS；BB01、BB23
  有條件接受；**BB16 FAIL**。沒有任何一題被改判為 PASS，簽核欄留白待使用者本人填寫。詳見
  `HUMAN_REVIEW/HUMAN_REVIEW_DECISIONS.md`（逐題原話）與 `HUMAN_REVIEW_FINAL_SUMMARY.md`（彙整
  +已知缺陷+展示建議）。
- **Tool 定義與 Agent 執行追蹤**：`TOOL_SPEC.md`（3 個 Tool 的名稱/用途/輸入/輸出/Error
  Handling）與 `EXECUTION_TRACE.md`（Demo A1 的完整 User Input → Agent Decision → Tool Call →
  Observation → Agent Decision → Final Result 標註，含 Agent 架構說明）。

## B. 已完成但未跨平台驗證
- Windows(`riskscope.ps1`)、Linux(`riskscope.sh` 在 Linux 的 host-network/OLLAMA_HOST 路徑):僅程式碼審閱,未實測。
- Apple 以外的 Podman 後端(libkrun 在本機會 abort,實測用 applehv)。

## C. 仍需要你親自操作
1. **GitHub**:repo(建議 Private)、推送權限/認證;目前 `git remote` 為空,我未建立也未推送。
2. **七題人工審查判定已完成**，但 `HUMAN_REVIEW_FINAL_SUMMARY.md` 的簽核欄（姓名/日期）刻意
   留白，依你指示沒有任何 Agent 代填，請你本人簽署。
3. **OpenAgents Workspace Token 輪替**(曾出現在對話紀錄,不在 repo,我無法驗證是否失效)。
4. 決定三個測試容器(8100/8110/8130)與其 volume 的處置:目前我**未清理**。注意:VM 重啟後 8100、8110 為 EXITED,只有 prof(8130)是我在 Desktop 啟動的 Running。
5. (選)確認課程是否要求 Podman Desktop;若老師用 CLI 即可,Desktop 非必要。

## D. 不影響繳交的已知限制 / 需誠實說明
- **模型輸出品質（使用者本人真人審查後的正式結論，非 AI 預審）**：
  - **BB16：FAIL（嚴重工程推理失準）**——結論與文件數據自相矛盾、500 公尺誤判為超過 600 公尺、
    自行假設文件未提供的特性阻抗與傳輸速率公式。**不得當成成功案例展示**，且使用者另外發現
    測試規格本身也有缺陷（真實 RS-485 通常僅兩端端接，本題規格讓每個節點都端接，「文件數值
    限制符合」與「實際硬體接線安全可用」須分開評估）。
  - **BB01、BB23：有條件接受**——核心計算與結論方向正確，但 BB01 的改善方案建議誤導（未針對
    真正的關鍵路徑）、BB23 把模型自行假設的「18 天修補時間」當成已驗證依據宣稱「理論可行」。
    兩題都**不得當成完全成功案例展示**，須在繳交說明中列為已知模型限制。
  - **BB02、BB07、BB10、BB13：PASS**，但各自仍有附註限制（見 `HUMAN_REVIEW_FINAL_SUMMARY.md`
    第 2 節），例如 BB10 只證明本次抵抗提示注入成功、不證明系統有主動警示能力。
  - 27B 單次且自評、8B 與 D/D2 統計上無差異（此為先前的模型分數面向限制，與上述真人審查結果
    是兩個獨立面向，不互相取代）。
- 回答偶有【排程計算】範本殘留:84f80fd 已剝除顯示層殘留(我獨立驗證 PASS);8B 常用「任務id:」前綴時會整段隱藏排程區塊(保守取捨)。
- 軟標示(未核對數字)力道偏弱的 UX 取捨;提示僅附於回答末。
- 截圖 04 為整螢幕截圖(含選單列、時間),右側被裁切;不含 Token。
- 登入需手動貼 Token(`riskscope.sh creds` 取得)。
- Holdout 仍封存;AI 驗收模型結果/快照/volume 全部保留。
- Podman Desktop 偵測到的「預設 machine 為 riskscope-machine(正式機,從未啟動)」提示:我選 **Ignore**,未更改預設連線。

## E. 最終回答
1. 最新可交付 commit:見本次 Claude A 封版 commit（工作樹乾淨，無未提交檔）。
2. GitHub 是否準備完成:本地版本乾淨可上傳;遠端/權限未備。
3. 能否安全推送:歷史掃描 0 命中、.gitignore 排除 runtime/.venv/.env;OpenAgents token 在 repo 外。**未經你授權前不要推送**。
4. Podman Desktop:已可管理既有 RiskScope 容器(見 A)。
5. 七題人工審查:**已完成**（BB02/BB07/BB10/BB13 PASS、BB01/BB23 有條件接受、BB16 FAIL），
   僅簽核欄待你本人簽署,見 C.2。
6. 老師第一次取得作業:`deploy/riskscope.sh build && deploy/riskscope.sh up && deploy/demo_run.sh`(需 Podman ≥4.4、Ollama+qwen3:8b);我已從乾淨副本驗證。
7. 能否正式繳交:**技術面可以(CONDITIONAL PASS)**;待你完成 GitHub 推送授權與人工簽核（簽名/日期）。
