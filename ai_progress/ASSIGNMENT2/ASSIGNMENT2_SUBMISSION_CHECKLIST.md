# Assignment 2 Submission Checklist (claude-b 版,2026-11-11;Claude A 封版更新)
AI 整理/驗證,非真人驗收（人工審查結果一節除外——那是使用者本人的真實判定）。

> **最新狀態（2026-11-16，取代下方 B、C、E 中已過時的敘述）**
> - **GitHub**：已推送到公開 repo `https://github.com/Cyy002/RiskScope`（`main`；依課程要求於 2026-11-16 改為 Public，免登入即可 clone／下載 ZIP）。
> - **人工審查簽核**：`HUMAN_REVIEW_FINAL_SUMMARY.md` 已簽核（林浩誠，2026-11-15，經使用者本人授權填寫）。
> - **一鍵啟動**：macOS `Start_RiskScope.command`、Windows `Start_RiskScope.bat`。自動檢查／安裝 Podman、Ollama、
>   `qwen3:8b`，建置啟動、預先載入模型、自動以 manager 登入，並在終端機顯示逐步操作教學（固定測資＋預期結果、
>   核准流程、權限驗證、自由測試）。
> - **跨平台實測**：macOS（乾淨 GitHub 副本，一鍵啟動＋教學步驟 1～10＋容器內 pytest 304 passed／2 skipped）、
>   Windows 11 實機（一鍵啟動、容器連線本機 Ollama、冷啟動後第一題 14A/336W、教學步驟 1～10）、
>   Linux（GitHub Actions ubuntu-latest，build／up／health／權限／決定性計算；runner 無 Ollama，未驗證 LLM 回覆）。
>   細節見 README 第 1 節與 `deploy/README_PODMAN.md` 的 Tested status。
> - **仍需使用者本人處理**：在課程平台繳交 repo 連結（截止 2026-11-22）。

**更新（Claude A，封版）**：七題人工審查已由使用者本人完成（BB01/BB23 有條件接受、BB16 FAIL、
其餘 4 題 PASS），完整原話見 `HUMAN_REVIEW_DECISIONS.md`，彙整見 `HUMAN_REVIEW_FINAL_SUMMARY.md`
（簽核欄已於 2026-11-15 填寫：林浩誠，經使用者本人明確授權）。C.2 不再是待辦，移至
A 類。所有相關檔案已 commit，工作樹乾淨。

## A. 已完成且實測通過(macOS Apple Silicon)
- `pytest -q` → 306 passed(我於本輪重跑)。
- Podman:乾淨副本 `--no-cache` 建置 → `up` → `/health` → `smoke`(真實 Ollama qwen3:8b,容器經 host.containers.internal 連線)→ `down`/再 `up` 資料保存。
- 六項作業二功能:Safari 網頁真實點擊(登入、Agent 問答 14A/336W、檢核卡、方案/影響追蹤、engineer 申請 pending→manager 核准→執行→稽核紀錄)。
- 失敗案例(GUI):缺 Token、outsider 無專案權限;(API/測試)401/403/409/422、單位維度錯誤、注入題。
- 完整 Git 歷史憑證掃描:0 命中(本 repo)。
- **Podman Desktop(本輪新驗證)**:設定 `Path to Podman Binary` 後,Desktop 偵測到既有 VM;Containers 列出 3 個 RiskScope 容器、Images 列出 prof/teacher/1.0、Volumes 列出 3 個 riskscope_portable_* volume;`riskscope-portable-prof` 啟動後 Logs 顯示 `/health`、`/api/projects/demo-chamber/overview`、靜態檔 200 OK。證據:`evidence/screenshots/12–15_*.png`(已提交)。未建立/重設任何 VM,未按 Set up。
- README 命令與 `deploy/riskscope.sh`(build/up/demo/smoke/restart-test/creds/down/purge)一致;`bash -n` 語法檢查通過;README/FINAL_STATUS 引用檔案皆存在。
- **七題人工審查（使用者本人逐題判定，完整對話記錄）**：BB02/BB07/BB10/BB13 PASS；BB01、BB23
  有條件接受；**BB16 FAIL**。沒有任何一題被改判為 PASS，簽核已完成（2026-11-15）。詳見
  `HUMAN_REVIEW/HUMAN_REVIEW_DECISIONS.md`（逐題原話）與 `HUMAN_REVIEW_FINAL_SUMMARY.md`（彙整
  +已知缺陷+展示建議）。
- **Tool 定義與 Agent 執行追蹤**：`TOOL_SPEC.md`（3 個 Tool 的名稱/用途/輸入/輸出/Error
  Handling）與 `EXECUTION_TRACE.md`（Demo A1 的完整 User Input → Agent Decision → Tool Call →
  Observation → Agent Decision → Final Result 標註，含 Agent 架構說明）。

## B. 已完成但未跨平台驗證
- ~~Windows、Linux 僅程式碼審閱~~ → 2026-11-15 已實測，見文件開頭「最新狀態」。Linux 未驗證真實 LLM 回覆（runner 無 Ollama）。
- Apple 以外的 Podman 後端(libkrun 在本機會 abort,實測用 applehv)。

## C. 仍需要你親自操作
1. ~~GitHub 推送~~ → 已完成。**仍需**：在課程平台繳交連結。
2. ~~人工審查簽核~~ → 已完成（2026-11-15）。
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
- 手動路徑登入需貼 Token(`riskscope.sh creds` 取得);一鍵啟動檔會自動以 manager 登入。
- Holdout 仍封存;AI 驗收模型結果/快照/volume 全部保留。
- Podman Desktop 偵測到的「預設 machine 為 riskscope-machine(正式機,從未啟動)」提示:我選 **Ignore**,未更改預設連線。

## E. 最終回答
1. 最新可交付 commit:見本次 Claude A 封版 commit（工作樹乾淨，無未提交檔）。
2. GitHub:已推送至公開 repo `Cyy002/RiskScope`。
3. 安全:歷史掃描 0 命中、.gitignore 排除 runtime/.venv/.env。
4. Podman Desktop:已可管理既有 RiskScope 容器(見 A)。
5. 七題人工審查:**已完成**（BB02/BB07/BB10/BB13 PASS、BB01/BB23 有條件接受、BB16 FAIL），
   簽核已完成。
6. 老師第一次取得作業:雙擊 `Start_RiskScope.command`（macOS）或 `Start_RiskScope.bat`（Windows）;手動路徑為 `deploy/riskscope.sh build && deploy/riskscope.sh up`。
7. 能否正式繳交:**可以**;只剩在課程平台繳交連結。
