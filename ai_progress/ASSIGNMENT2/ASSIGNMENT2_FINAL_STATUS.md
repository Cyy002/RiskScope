# RiskScope 作業二 最終狀態 (Claude A, 2026-11-09)

對照 commit `5354851`（延續 `b5f30a8`，加上 claude-b 的獨立審查與兩項小修正）。

## 總結判定

**技術面：有條件 PASS。繳交面：尚未具備「可繳交」條件——缺 GitHub 遠端與任何真人確認。**

這與 claude-b 獨立審查（`INDEPENDENT_REVIEW_claude-b_20261109.md`）的結論一致。技術實作、測試、
真實 Podman/Demo 執行證據都已完成且可重現；缺的兩項都不是程式問題，而是需要使用者本人處理的
外部事項（GitHub 帳號/權限、真人審查時間）。

## 1. 逐項對照老師要求

| 要求 | 狀態 | 證據 |
|---|---|---|
| 對話觸發與 Agent 決策流程 | ✅ 已完成 | `app/chat.py chat_turn()`；多輪歷史（同 session/project/user）`tests/test_reasoning_integration.py`；真實執行見 Demo A1→A2→A3（`DEMO_EVIDENCE.md`） |
| 合成資料與權限檢索 | ✅ 已完成 | `app/retrieval.py` + `app/security.py`（Token/角色/文件 ACL）；Demo C1（401）、C2（403）、C3（機密文件隔離） |
| 真實 Tool 呼叫與工程驗證 | ✅ 已完成 | `app/engineering.py power_continuous()`；Demo A1/A2 真實算出 14A/336W→12A/288W，含超額百分比 |
| 方案比較 | ✅ 已完成 | Demo B 跨領域供應商決策：facts/unknowns/options 齊全，標示需人工審核，無捏造成本數字 |
| 管理者模擬核准 | ✅ 已完成 | `app/actions.py`；Demo C4（engineer 未核准不能執行,403）、C4b（不能自我核准） |
| 至少兩個失敗案例與錯誤處理 | ✅ 已完成（4 個，超過要求） | `FAILURE_CASES.md` F1–F4：越權/ACL、單位維度錯誤、未核准寫入、模型謊稱已核准(mock)注入攔截 |
| Podman 可重現啟動 | ⚠️ 已完成但範圍有限 | `deploy/riskscope.sh build/up/smoke/restart-test` 皆 PASS，**但只在 macOS（Apple Silicon, applehv）實測**；Windows/Linux 腳本存在但未實測，已在文件誠實標示 |
| 執行紀錄、測試證據 | ✅ 已完成 | `pytest -q` 302 passed（本機與容器內一致，claude-b 已重跑確認）；`scripts.evaluate` 45/45；完整原始終端輸出存檔於 `ai_progress/ASSIGNMENT2/evidence/` |
| GitHub | ❌ 尚未完成 | 本地 git 倉庫已備好（見第 2 節），**無遠端**，需使用者提供 |

## 2. Git / GitHub 狀態

- 本地倉庫：5 個 commit，工作樹乾淨，HEAD = `5354851`。
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

**已實測並 PASS（claude-b 已獨立重跑容器內程式雜湊核對，確認與 HEAD 完全一致）：**
```
deploy/riskscope.sh build && deploy/riskscope.sh up
deploy/demo_run.sh
```
`build`→`up`/`health`→`demo`(FULL PASS)→`smoke`→`restart-test` 全部成功，見
`deploy/README_PODMAN.md` 開頭與 `ai_progress/ASSIGNMENT2/DEMO_EVIDENCE.md`。

**阻塞風險（非程式缺陷，但請知悉）：**
- 目前獨立測試 VM（`riskscope-codex-apple-20261107`）上的容器仍佔用主機 `127.0.0.1:8100`。
  若要恢復正式「展示」環境在 8100，請先對該連線執行 `deploy/riskscope.sh down`
  （`CONTAINER_CONNECTION=riskscope-codex-apple-20261107 deploy/riskscope.sh down`）。
  正式機 `riskscope-machine` 全程維持 "Never up"，未被觸碰。
- 只在 macOS（Apple Silicon）實測；Windows/Linux 的 `riskscope.ps1`/shell 指令**理論相容但未實測**，
  已在 README 誠實標示，不得向老師宣稱已驗證。

## 4. 尚未完成，需要使用者本人處理的事項

1. **GitHub 遠端**：如上，需使用者提供 repo 與權限。
2. **HUMAN_REVIEW 7 題真人審查**：`ai_progress/RISK_INTELLIGENCE_EVALUATION/HUMAN_REVIEW/` 準備好了，
   但目前零份真人確認；AI 的預審不能取代。
3. **最終繳交前的實際截圖/錄影**：`DEMO_RUNBOOK.md` 流程已可直接執行（容器仍在線上），
   由 claude-b 負責整理，尚未完成。
4. **是否要做 Windows/Linux 實測**：若時間允許，建議至少找一台 Windows/Linux 機器跑一次
   `riskscope.ps1`/對應 shell 指令驗證，否則提交時必須保留「僅 macOS 實測」的誠實標示。

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
