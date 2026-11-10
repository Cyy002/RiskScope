# RiskScope 作業二 最終狀態 (Claude A, 更新於 2026-11-10 深夜)

對照 commit `67d53ea`。延續 claude-b 的獨立審查、「教授第一次驗收」真實瀏覽器 GUI 操作模擬，本輪
（daemon 重啟後第二輪）新完成：Podman Desktop 整合排查（已驗證安全但無法修復的限制）、
`riskscope.ps1` 一個真實邏輯錯誤修復、GitHub CLI 現況確認、一項需要使用者親自處理的安全提醒
（見第 0 節），以及 claude-b 獨立審查 `HUMAN_REVIEW_FOR_USER.md` 時發現、Claude A 已修復並驗證的
**兩個真實程式缺陷**（見第 3.5 節「B1」）：模型回答中殘留的範本佔位符文字外洩給使用者、軟標示
提醒重複列出同一個數字。全套測試現為 306 passed（302 既有 + 1 pytest.ini 修復驗證不變 + 4 本輪
新增回歸測試：3 個排程範本外洩案例 + 1 個去重案例）。

## 0. ⚠️ 需要你立即知道的安全提醒（非程式問題）

**OpenAgents Workspace Token 已在本次對話的多個 Bash 指令中以明文出現過**（我呼叫
`workspace-endpoint.openagents.org` 的 `curl` 指令裡的 `X-Workspace-Token` 標頭）。這**不是**
git 歷史或程式碼裡的問題（我已確認它從未被寫入任何追蹤檔案），而是這個 OpenAgents 對話本身的
工具呼叫紀錄裡會留存這個值。我沒有能力自己輪替或撤銷這個 Token（那是 OpenAgents 平台的權限，
不是我能呼叫的工具範圍）。**依你的指示，不能只憑「我改了記錄」就宣稱這個 Token 已經安全**——
請你自行到 OpenAgents 後台確認是否要輪替這個 workspace token，以及評估這個對話紀錄本身的存取
範圍是否需要限制。

## 總結判定

**技術面：有條件 PASS（CONDITIONAL PASS）。繳交面：尚未具備「可繳交」條件——缺 GitHub 遠端與任何真人確認。**

這與 claude-b 獨立審查（`INDEPENDENT_REVIEW_claude-b_20261109.md`）及其後續「教授第一次驗收模擬」
的結論一致。技術實作、測試、真實 Podman/Demo 執行證據都已完成且可重現（含真實瀏覽器 GUI 點擊，
不只是 API 腳本）；缺的兩項都不是程式問題，而是需要使用者本人處理的外部事項（GitHub 帳號/權限、
真人審查時間）。

**本輪新發現並已修復的兩個真正阻塞問題：**
1. README 文件寫的 `python -m pytest -q`（不帶任何路徑參數）原本會**整批收集失敗**——
   `ai_progress/codex-m125-review/` 底下保留的兩份舊 `tests/` 快照各自帶有自己的 `conftest.py`，
   pytest 從倉庫根目錄做預設遞迴收集時會把模組名稱搞混，丟出 `ImportPathMismatchError`，0 項測試
   執行。已修復：新增 `pytest.ini`（`testpaths = tests`），不改動任一份舊快照，驗證後 302 passed。
2. **git 完整歷史（不只是最新檔案）曾經包含 11 組真實的一次性測試 Token 字串**（在
   `ai_progress/antigravity-acl-validation/baseline-test-run.log` 與
   `ai_progress/codex-ollama/targeted-tests.txt` 的最早一次提交裡）。先前只修正了最新版本的檔案
   內容，但舊 commit 仍可用 `git log -p` 完整還原出這些字串——這正是你特別提醒要檢查的風險。已處理：
   備份整個 `.git`（`~/riskscope_git_backup_before_history_rewrite_20261110.tar.gz`）後，用
   `git-filter-repo` 把這 11 組字串從**全部歷史**換成統一的 `<redacted-ephemeral-test-token>`佔位字串，
   重新掃描全歷史（含更廣泛的 API key / private key 樣式）確認乾淨，commit 數與訊息不變。這些 Token
   本身已確認是過去暫存測試資料庫產生的一次性字串，與目前任何真實憑證都不吻合，不是真正能用的機密，
   但既然會出現在將要公開/繳交的歷史裡，清乾淨仍是必要的。重寫後重跑 302 passed 驗證無誤。

## 1. 逐項對照老師要求

| 要求 | 狀態 | 證據 |
|---|---|---|
| 對話觸發與 Agent 決策流程 | ✅ 已完成 | `app/chat.py chat_turn()`；多輪歷史（同 session/project/user）`tests/test_reasoning_integration.py`；真實執行見 Demo A1→A2→A3（`DEMO_EVIDENCE.md`） |
| 合成資料與權限檢索 | ✅ 已完成 | `app/retrieval.py` + `app/security.py`（Token/角色/文件 ACL）；Demo C1（401）、C2（403）、C3（機密文件隔離） |
| 真實 Tool 呼叫與工程驗證 | ✅ 已完成 | `app/engineering.py power_continuous()`；Demo A1/A2 真實算出 14A/336W→12A/288W，含超額百分比 |
| 方案比較 | ✅ 已完成 | Demo B 跨領域供應商決策：facts/unknowns/options 齊全，標示需人工審核，無捏造成本數字 |
| 管理者模擬核准 | ✅ 已完成 | `app/actions.py`；Demo C4（engineer 未核准不能執行,403）、C4b（不能自我核准） |
| 至少兩個失敗案例與錯誤處理 | ✅ 已完成（4 個，超過要求） | `FAILURE_CASES.md` F1–F4：越權/ACL、單位維度錯誤、未核准寫入、模型謊稱已核准(mock)注入攔截 |
| Podman 可重現啟動 | ⚠️ 已完成但範圍有限 | `deploy/riskscope.sh build/up/smoke/demo/restart-test` 皆 PASS，含一次 `--no-cache` 從乾淨 checkout 的冷建置；**但只在 macOS（Apple Silicon, applehv）實測**，Windows/Linux 腳本存在但未實測，已在文件誠實標示。Podman Desktop GUI 在這台機器因 Podman 走非標準安裝路徑而顯示「No Container Engine」，已在文件記錄為環境問題，不是程式缺陷（`podman ps`/`logs` 在 Terminal 正常） |
| 執行紀錄、測試證據 | ✅ 已完成（修復一個真正的阻塞問題） | `python -m pytest -q`（不帶路徑，即 README 文件寫的指令）原本會整批收集失敗，已修復（見上方總結），現為 302 passed；`scripts.evaluate` 45/45；完整原始終端輸出存檔於 `ai_progress/ASSIGNMENT2/evidence/` |
| GitHub | ❌ 尚未完成 | 本地 git 倉庫已備好（見第 2 節），**無遠端**，需使用者提供 |

## 2. Git / GitHub 狀態

- 本地倉庫：13 個 commit，工作樹乾淨，HEAD = `96445e1`。
- `git remote -v` 為空——**沒有建立任何遠端，也沒有嘗試建立公開儲存庫**（依指示不擅自建立）。
- **已完整檢查過 git 歷史（不只最新檔案）**：用 `git log -p --all` 對全部歷史掃描 Bearer token、
  `sk-`/`AKIA`/私鑰等樣式，找到的 11 組一次性測試 Token 已用 `git-filter-repo` 從全歷史清除（詳見
  上方總結），清除前已備份完整 `.git` 到使用者家目錄外的 `riskscope_git_backup_before_history_rewrite_20261110.tar.gz`。
  重寫後重新掃描確認乾淨。
- 無 `.venv/`、無 `runtime/`、無任何目前有效的憑證/Token 被追蹤。
- `.gitignore` 排除 `runtime/`、`.venv/`、`.env`、本機備份 tar。追蹤檔案約 1360 個（含新增的截圖
  與審查文件），最大檔案約 1.6MB（截圖），`.git` 總大小 12MB——適合直接 push。

**缺少且需要使用者處理：**
1. 提供要推送的 GitHub repository（新建或既有），以及推送權限/認證方式（SSH key 或 HTTPS token）。
2. 決定 repository 是否要公開；本專案不含真實企業資料，但若要公開請使用者自行確認校方/系上規範。
3. **這台機器沒有安裝 GitHub CLI**（`gh` 指令不存在）。要上傳需要你自行安裝 `gh` 並登入，或直接用
   `git remote add` + `git push`（需要 SSH key 或 Personal Access Token，請勿在對話中貼出）。

我**沒有**自行建立 GitHub repo 或推送，待使用者指示後立即執行 `git remote add` + `git push`。
**注意**：由於歷史已被重寫（commit hash 全部改變），若你或 claude-b 之前已經手動複製/備份過舊版的
`.git`，那份備份和現在的倉庫是兩條不同的歷史，push 前請確認用的是這次重寫後的版本（HEAD `96445e1`）。

## 3. Podman 啟動與 Demo 現況

**已實測並 PASS，含兩層證據：**
```
deploy/riskscope.sh build && deploy/riskscope.sh up
deploy/demo_run.sh
```
1. **CLI/API 層**（`demo_run.sh`/`scripts/demo_scenarios.py`）：`build`→`up`/`health`→`demo`(FULL
   PASS)→`smoke`→`restart-test` 全部成功，見 `deploy/README_PODMAN.md` 開頭與
   `ai_progress/ASSIGNMENT2/DEMO_EVIDENCE.md`。
2. **真實瀏覽器 GUI 層**（claude-b 的「教授第一次驗收模擬」+ Claude A 本輪的清潔重跑，CONDITIONAL
   PASS）：用 AppleScript/Accessibility 實際在 Safari 裡點擊操作，不是背景 API 腳本冒充——manager/
   engineer 登入 → 對話式 Agent 問答（真實等待 LLM 回覆，14A/336W 檢核、風險 R-POWER）→ 決策推演頁
   看到確定性檢核卡與可追溯工程依賴 → 提出模擬變更申請 → manager 核准並執行 → 操作稽核頁確認紀錄
   → GUI 可見的失敗案例（outsider 無權限）。Token 全程透過 accessibility API 直接填入輸入框，從未
   顯示或列印在畫面、截圖或終端機輸出中。**正式截圖包**（11 張，含 Podman Desktop 真實限制畫面）已
   整理於 `ai_progress/ASSIGNMENT2/evidence/screenshots/`，索引見該目錄的 `README.md`。

**阻塞風險（非程式缺陷，但請知悉）：**
- 目前獨立測試 VM（`riskscope-codex-apple-20261107`）上**同時有三個測試容器在跑**（8100 原始測試、
  8110 "teacher"、8130 "prof"，各自獨立 volume），皆為本輪驗收過程留下，尚未清理，因使用者指示
  暫時保留供查驗。若要恢復正式「展示」環境在 8100，請先對該連線執行 `deploy/riskscope.sh down`
  （`CONTAINER_CONNECTION=riskscope-codex-apple-20261107 deploy/riskscope.sh down`，`8110`/`8130`
  需另外指定 `RS_NAME`/`RS_PORT` 才能分別關閉）。正式機 `riskscope-machine` 全程維持 "Never up"，
  未被觸碰。
- 只在 macOS（Apple Silicon）實測；Windows/Linux 的 `riskscope.ps1`/shell 指令**理論相容但未實測**，
  已在 README 誠實標示，不得向老師宣稱已驗證。
- Podman Desktop GUI 在這台機器上看不到容器（見上表「Podman 可重現啟動」列），老師自己標準安裝的
  Podman Desktop 不一定會遇到這個問題，但目前**無法證明** Podman Desktop 一定能正確顯示本專案容器。
- **容器目前狀態更新（2026-11-10 晚間盤點）**：隔離測試 VM 曾經停止過（原因不明，可能是閒置逾時
  或系統睡眠，不是被誰關掉的），已重新啟動並確認 3 個測試容器（8100/8110/8130）都還在、狀態是
  `Exited (0)`（乾淨停止，不是崩潰），對應的 3 個 volume（`riskscope_portable_data`/`_teacher`/
  `_prof`）資料完整，**沒有刪除任何東西**。正式機 `riskscope-machine` 全程仍是 "Never up"。若要
  恢復使用任一個，`podman start <容器名>` 即可；若確認不再需要，由你決定何時清理。

## 3.5 本輪（daemon 重啟後）新排查項目

**A1：Podman Desktop 整合（第二輪，已找到官方正解，缺最後一步需要你操作）**
第一輪只是實測「會不會單純是PATH問題」（答案：不是）。這輪改用直接解壓縮 Podman Desktop 自己的
`app.asar`、讀取其「Podman」內建擴充功能的**官方原始碼**（`podman-cli.ts`/`podman-install.ts`/
`mac-os-installer.ts`/`package.json`），不是用猜的：
- **證實「Set up」按鈕不安全**：原始碼顯示它會執行 `open <內建.pkg> -W`——跳出 macOS 系統安裝精靈
  （需要管理員密碼），把 Podman 裝到 `/opt/podman/bin/`，等於建立**第二套獨立安裝**，不是修好現有
  這套。因此沒有點擊測試，完全沒有違反「不重新安裝、不建立另一套 Podman」。
- **找到真正的官方解法**：這個擴充功能原本就設計了一個專門給這種情況用的設定——
  `podman.binary.path`，UI 上顯示名稱是「**Path to Podman Binary**」，在
  **Settings → Preferences → Podman 分類**底下。原始碼證實 `getPodmanCli()` 會優先用這個自訂路徑，
  PATH 搜尋只是備援。填入 `/Users/haochenglin/.local/podman/bin/podman` 後，理論上完全不需要重裝、
  不會碰任何 machine，因為既有的 3 台 machine 早就正確登記在
  `~/.config/containers/podman-connections.json`（已確認內容正確,含正式機),Podman Desktop 讀到
  對的執行檔後應該就能直接偵測到，純讀取不會自動新建。
- **沒有完成最後一步的原因（不是沒試，是確認不安全才停）**：Podman Desktop 整個視窗（含側邊欄
  「Settings」文字）用 System Events 檢視只看到 `button 1`/`group 1` 這種完全沒有語意標籤的通用
  元素；嘗試用螢幕座標直接點擊（`click at {x,y}`）在這台機器上系統回傳 -25200 錯誤，不支援。在
  無法事先確認「即將點到的到底是哪個按鈕」的情況下，用猜測性的索引或座標點擊有風險（旁邊可能就是
  真的會動到 machine 的按鈕），所以沒有進一步嘗試，直接把確切步驟列出來。
- **需要你做的 30 秒操作**：開啟 Podman Desktop → 左側齒輪圖示「Settings」→「Preferences」→
  找「Podman」分類 → 「Path to Podman Binary」欄位填 `/Users/haochenglin/.local/podman/bin/podman`
  → 存檔。做完跟我說一聲，我可以馬上重新檢查 Containers/Images/Volumes/Logs 是否正確顯示。
- 這個發現已寫進 `deploy/README_PODMAN.md` 常見問題一節，含完整技術細節。

**A2：GitHub 正式交付準備（檢查結果）**
- 這台機器**沒有安裝 GitHub CLI**（`gh` 指令不存在）。要上傳需要你自行安裝並登入 `gh auth login`，
  或直接用 `git remote add` + `git push`（需要你提供 SSH key 或 Personal Access Token）。
- 重新掃描了這一輪新增的所有 commit（截圖、審查文件、文件修正）的完整歷史，Bearer token、API
  key、私鑰樣式、demo_credentials.json 格式字串皆無發現，連截圖檔案本身的二進位內容都用 `strings`
  掃過一次，乾淨。
- `.gitignore` 排除項目未變、仍然正確。
- README 文件裡列出的指令（`build`/`up`/`demo`/`smoke`/`restart-test`/`creds`/`down`/`purge`）
  與 `deploy/riskscope.sh`/`riskscope.ps1` 實際支援的指令逐一核對一致。
- **見第 0 節：OpenAgents Workspace Token 曝露在對話紀錄裡，需要你親自處理，與本倉庫無關。**

**A3：真實程式缺陷排查（找到並修復 1 個）**
逐行比對 `riskscope.ps1`（Windows 版本）與已驗證過的 `riskscope.sh`（Linux/macOS 版本）邏輯，
發現 `restart-test` 有一個真實的行為差異：PowerShell 版的 `Pod` 輔助函式只要指令結束碼非 0 就會
直接拋出例外，但 `restart-test` 一開始直接用它執行 `scripts/portable_smoke.py`——如果 smoke
腳本因為模型輸出的隨機性而非確定性地回報失敗（不是 podman 的問題），整個 `restart-test` 會在
做持久性檢查之前就中止，還會誤報成「podman exec 失敗」，掩蓋了真正原因。已修正為比照 `.sh` 版本
的作法：先記下結束碼、不中止、做完持久性檢查後才一起回報。**這台機器沒有安裝 PowerShell（`pwsh`
不存在），無法實際執行驗證語法或行為，這個修正僅經過與 `.sh` 版本的邏輯比對確認——Windows 實測
仍然掛零，必須繼續誠實標示為未實測。**

**B1：claude-b 獨立審查 `HUMAN_REVIEW_FOR_USER.md` 發現並由 Claude A 修復的 2 個真實缺陷**
claude-b 對照 K3 真實最終回答逐題核對該文件時，發現：
1. **範本佔位符外洩（P2，真實使用者會看到的缺陷）**：BB01、BB23 的回答裡，`【排程計算】` 區塊
   殘留了提示詞本身的格式說明文字（例如模型把「工期=數字」「前置=[其他任務id,...]」原樣抄出，
   或用字面上的「任務id」當作真正的任務識別碼，而非替換成實際數值）。根因：`parse_schedule_block()`
   原本只有在**整個區塊解析失敗**時才會讓呼叫端選擇忽略，但 BB01 的情況是 6 個真實任務行本身解析
   成功（殘留的那一行格式不符而被 regex 的 `findall()` 悄悄跳過，不影響其餘解析），所以沒有觸發
   「忽略」邏輯，殘留文字就直接顯示給使用者。已修正為**直接偵測殘留文字本身**（而非只看解析是否
   成功），一律從顯示內容中移除 `【排程計算】` 標記之後的部分。用真實 K3 BB01/BB23 文字驗證，另加
   3 個回歸測試（含一個「真正乾淨、沒有殘留文字的區塊絕對不能被誤刪」的保護測試）。**完全沒有
   碰 M7 安全層、核准/注入檢查或任何 AI 判斷邏輯，純粹是顯示層清理既已判定「該忽略」的內容。**
2. **軟標示數字重複（P3，已修復）**：BB23 的提醒文字出現「...包括：18天、18天，請自行核實...」——
   同一個未經查核的數字在文字裡出現兩次，就被各自的檢查各記錄一次。已改用 `dict.fromkeys()` 在
   組成提醒文字前去重（只影響提醒文字本身，模型原本的回覆內容完全不動）。
- claude-b 另外建議的 2 項（截圖只截瀏覽器視窗不含選單列、不裁切）標記 P3、不阻塞 11/22，尚未處理。

## 4. 尚未完成，需要使用者本人處理的事項

1. **GitHub 遠端**：如上，需使用者提供 repo 與權限。
2. **HUMAN_REVIEW 7 題真人審查**：精簡版已備好在
   `ai_progress/RISK_INTELLIGENCE_EVALUATION/HUMAN_REVIEW/HUMAN_REVIEW_FOR_USER.md`——每題一張卡片
   （模型實際回答摘要、AI 評審分數與理由、你可以直接打勾的判定欄），設計成可以在合理時間內親自看完；
   原始完整版（9000+ 行）仍保留供深入查證。**目前零份真人確認**；AI 的預審不能取代，你填完判定欄後
   請回報給 Claude A / claude-b 記錄完成日期。
3. **最終繳交前的正式截圖/錄影**：11 張真實操作截圖已整理在
   `ai_progress/ASSIGNMENT2/evidence/screenshots/`（涵蓋 Podman Desktop、登入、Agent 問答+工具檢核、
   決策分析、管理者核准、失敗案例），可直接用於繳交文件；若需要錄影檔案（非靜態截圖），仍待製作。
4. **是否要做 Windows/Linux 實測**：若時間允許，建議至少找一台 Windows/Linux 機器跑一次
   `riskscope.ps1`/對應 shell 指令驗證，否則提交時必須保留「僅 macOS 實測」的誠實標示。
5. **清理驗收期間留下的多個測試容器**（8100/8110/8130，見第 3 節）：確認不再需要後請執行
   `deploy/riskscope.sh down`（逐一指定對應 `RS_NAME`/`RS_PORT`），避免正式繳交前這台機器上
   累積過多無人管理的測試資源。

## 5. 老師拿到專案後的實際啟動指令

```bash
# 1) 需求：Podman >= 4.4、本機 Ollama 已安裝並 pull 好 qwen3:8b
podman machine init && podman machine start   # 若尚未建立/啟動 Podman machine
ollama serve &   # 若尚未啟動
ollama pull qwen3:8b

# 2) 建置並啟動（全新環境自動建置）
deploy/riskscope.sh build
deploy/riskscope.sh up          # http://127.0.0.1:8100

# 3) 一鍵展示全部六項能力（對話/授權/工具/方案比較/模擬核准/錯誤處理）
deploy/demo_run.sh

# 4) 其他驗證
deploy/riskscope.sh smoke         # 單輪真實 Agent 測試
deploy/riskscope.sh restart-test  # 重啟持久化驗證
deploy/riskscope.sh creds         # 取得登入 Token，開瀏覽器 http://127.0.0.1:8100 操作 UI

# 5) 本機程式測試（不需要 Podman）
python -m pytest -q                # 302 passed
python -m scripts.evaluate         # 45/45

# 6) 結束
deploy/riskscope.sh down          # 或 purge（同時刪除 volume）
```
常見問題排解見 `deploy/README_PODMAN.md` 第 4 節。
