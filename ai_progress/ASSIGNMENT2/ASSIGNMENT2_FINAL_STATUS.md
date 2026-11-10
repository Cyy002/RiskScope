# RiskScope 作業二 最終狀態 (Claude A, 更新於 2026-11-10)

對照 commit `0c84fcf`（延續 `5354851`/`b5f30a8`，加上 claude-b 的獨立審查、一次完整的「教授第一次
驗收」真實瀏覽器 GUI 操作模擬，以及本次新發現並修復的一個真正的繳交阻塞問題）。

## 總結判定

**技術面：有條件 PASS（CONDITIONAL PASS）。繳交面：尚未具備「可繳交」條件——缺 GitHub 遠端與任何真人確認。**

這與 claude-b 獨立審查（`INDEPENDENT_REVIEW_claude-b_20261109.md`）及其後續「教授第一次驗收模擬」
的結論一致。技術實作、測試、真實 Podman/Demo 執行證據都已完成且可重現（含真實瀏覽器 GUI 點擊，
不只是 API 腳本）；缺的兩項都不是程式問題，而是需要使用者本人處理的外部事項（GitHub 帳號/權限、
真人審查時間）。

**本次新發現並已修復的真正阻塞問題**：README 文件第 4 節寫的 `python -m pytest -q`（不帶任何路徑
參數）在這個倉庫目前的狀態下實際上會**整批失敗**——`ai_progress/codex-m125-review/` 底下保留的
兩份舊 `tests/` 快照各自帶有自己的 `conftest.py`，pytest 從倉庫根目錄做預設遞迴收集時，會把它們
的模組名稱和真正的 `tests/conftest.py` 搞混，丟出 `ImportPathMismatchError`，整個收集中止、0 項
測試執行。這代表一個完全照 README 操作的老師，光是執行文件寫的那一行指令就會得到看起來像是程式
壞掉的錯誤。已修復：新增 `pytest.ini`（`testpaths = tests`），不改動、不刪除任一份舊快照，驗證
後乾淨的 `python -m pytest -q` 可重現 302 passed。

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

- 本地倉庫：9 個 commit，工作樹乾淨，HEAD = `0c84fcf`。
- `git remote -v` 為空——**沒有建立任何遠端，也沒有嘗試建立公開儲存庫**（依指示不擅自建立）。
- 已核對：無 `.venv/`、無 `runtime/`、無目前有效的憑證/Token；舊測試 log 裡兩處一次性測試 Token
  字串已遮蔽（確認與目前任何真實憑證不符，純屬過去暫存資料庫的拋棄式 Token）。
- `.gitignore` 排除 `runtime/`、`.venv/`、`.env`、本機備份 tar。追蹤檔案 1346 個，最大檔案約
  0.6MB，`.git` 總大小 4.8MB——適合直接 push。

**缺少且需要使用者處理：**
1. 提供要推送的 GitHub repository（新建或既有），以及推送權限/認證方式（SSH key 或 HTTPS token）。
2. 決定 repository 是否要公開；本專案不含真實企業資料，但若要公開請使用者自行確認校方/系上規範。

我**沒有**自行建立 GitHub repo 或推送，待使用者指示後立即執行 `git remote add` + `git push`。

## 3. Podman 啟動與 Demo 現況

**已實測並 PASS，含兩層證據：**
```
deploy/riskscope.sh build && deploy/riskscope.sh up
deploy/demo_run.sh
```
1. **CLI/API 層**（`demo_run.sh`/`scripts/demo_scenarios.py`）：`build`→`up`/`health`→`demo`(FULL
   PASS)→`smoke`→`restart-test` 全部成功，見 `deploy/README_PODMAN.md` 開頭與
   `ai_progress/ASSIGNMENT2/DEMO_EVIDENCE.md`。
2. **真實瀏覽器 GUI 層**（claude-b，「教授第一次驗收模擬」，CONDITIONAL PASS）：用 AppleScript/
   Accessibility 實際在 Safari 裡點擊操作，不是背景 API 腳本冒充——engineer 登入 → 對話式 Agent
   問答（14A/336W 檢核）→ 決策推演頁看到 `fail` 檢核卡與方案比較 → 提出模擬變更申請 → 換 manager
   登入核准並執行 → 操作稽核頁確認紀錄 → 兩個 GUI 可見的失敗案例（無 Token 登入、outsider 無權限）
   → `down`/`up` 重啟後資料保留。Token 全程透過剪貼簿貼入並隨即清空，未顯示在畫面或截圖中。

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

## 4. 尚未完成，需要使用者本人處理的事項

1. **GitHub 遠端**：如上，需使用者提供 repo 與權限。
2. **HUMAN_REVIEW 7 題真人審查**：`ai_progress/RISK_INTELLIGENCE_EVALUATION/HUMAN_REVIEW/` 準備好了，
   但目前零份真人確認；AI 的預審不能取代。
3. **最終繳交前的實際截圖/錄影**：核心流程已用真實瀏覽器 GUI 走過一次（見第 3 節），但尚未產出
   正式的截圖/錄影檔案給老師，由 claude-b 負責整理。
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
