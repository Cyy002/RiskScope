# Assignment 2 Submission Checklist (claude-b 版,2026-11-11;Claude A 更新 HEAD 至 `a66be23`)
AI 整理/驗證,非真人驗收。

**更新(Claude A)**:C.6 的截圖與本 checklist、`HUMAN_REVIEW_FULL_FOR_USER.md` 已全部 commit
（`a66be23`），不再是待辦。工作樹乾淨，306 passed。

## A. 已完成且實測通過(macOS Apple Silicon)
- `pytest -q` → 306 passed(我於本輪重跑)。
- Podman:乾淨副本 `--no-cache` 建置 → `up` → `/health` → `smoke`(真實 Ollama qwen3:8b,容器經 host.containers.internal 連線)→ `down`/再 `up` 資料保存。
- 六項作業二功能:Safari 網頁真實點擊(登入、Agent 問答 14A/336W、檢核卡、方案/影響追蹤、engineer 申請 pending→manager 核准→執行→稽核紀錄)。
- 失敗案例(GUI):缺 Token、outsider 無專案權限;(API/測試)401/403/409/422、單位維度錯誤、注入題。
- 完整 Git 歷史憑證掃描:0 命中(本 repo)。
- **Podman Desktop(本輪新驗證)**:設定 `Path to Podman Binary` 後,Desktop 偵測到既有 VM;Containers 列出 3 個 RiskScope 容器、Images 列出 prof/teacher/1.0、Volumes 列出 3 個 riskscope_portable_* volume;`riskscope-portable-prof` 啟動後 Logs 顯示 `/health`、`/api/projects/demo-chamber/overview`、靜態檔 200 OK。證據:`evidence/screenshots/12–15_*.png`(新增,尚未提交)。未建立/重設任何 VM,未按 Set up。
- README 命令與 `deploy/riskscope.sh`(build/up/demo/smoke/restart-test/creds/down/purge)一致;`bash -n` 語法檢查通過;README/FINAL_STATUS 引用檔案皆存在。

## B. 已完成但未跨平台驗證
- Windows(`riskscope.ps1`)、Linux(`riskscope.sh` 在 Linux 的 host-network/OLLAMA_HOST 路徑):僅程式碼審閱,未實測。
- Apple 以外的 Podman 後端(libkrun 在本機會 abort,實測用 applehv)。

## C. 仍需要你親自操作
1. **GitHub**:repo(建議 Private)、推送權限/認證;目前 `git remote` 為空,我未建立也未推送。
2. **七題人工審查**:請打開 `ai_progress/RISK_INTELLIGENCE_EVALUATION/HUMAN_REVIEW/HUMAN_REVIEW_FULL_FOR_USER.md`(每題含題目/文件、預期要點、模型實際最終回答全文、AI 評審理由、你的判定欄),逐題勾選並簽名日期。完成前一律標示「AI 預審,尚未經真人確認」。
3. **OpenAgents Workspace Token 輪替**(曾出現在對話紀錄,不在 repo,我無法驗證是否失效)。
4. 決定三個測試容器(8100/8110/8130)與其 volume 的處置:目前我**未清理**。注意:VM 重啟後 8100、8110 為 EXITED,只有 prof(8130)是我在 Desktop 啟動的 Running。
5. (選)確認課程是否要求 Podman Desktop;若老師用 CLI 即可,Desktop 非必要。
6. ~~提交新增的 4 張 Desktop 截圖與本 checklist/七題完整包~~ **已由 Claude A commit（`a66be23`）。**

## D. 不影響繳交的已知限制 / 需誠實說明
- **模型輸出品質**:BB16(18 分,結論與文件數據矛盾且編造反射係數)、BB23(77 分,自行假設 18 天)、BB01(88 分,建議非關鍵路徑為誤導)為真實模型限制,已在七題包中標出;27B 單次且自評、8B 與 D/D2 統計上無差異。
- 回答偶有【排程計算】範本殘留:84f80fd 已剝除顯示層殘留(我獨立驗證 PASS);8B 常用「任務id:」前綴時會整段隱藏排程區塊(保守取捨)。
- 軟標示(未核對數字)力道偏弱的 UX 取捨;提示僅附於回答末。
- 截圖 04 為整螢幕截圖(含選單列、時間),右側被裁切;不含 Token。
- 登入需手動貼 Token(`riskscope.sh creds` 取得)。
- Holdout 仍封存;AI 驗收模型結果/快照/volume 全部保留。
- Podman Desktop 偵測到的「預設 machine 為 riskscope-machine(正式機,從未啟動)」提示:我選 **Ignore**,未更改預設連線。

## E. 最終回答
1. 最新可交付 commit:`a66be23`(工作樹乾淨，無未提交檔)。
2. GitHub 是否準備完成:本地版本乾淨可上傳;遠端/權限未備。
3. 能否安全推送:歷史掃描 0 命中、.gitignore 排除 runtime/.venv/.env;OpenAgents token 在 repo 外。**未經你授權前不要推送**。
4. Podman Desktop:已可管理既有 RiskScope 容器(見 A)。
5. 七題人工審查:見 C.2。
6. 老師第一次取得作業:`deploy/riskscope.sh build && deploy/riskscope.sh up && deploy/demo_run.sh`(需 Podman ≥4.4、Ollama+qwen3:8b);我已從乾淨副本驗證。
7. 能否正式繳交:**技術面可以(CONDITIONAL PASS)**;待你完成 GitHub 推送授權與人工簽核。
