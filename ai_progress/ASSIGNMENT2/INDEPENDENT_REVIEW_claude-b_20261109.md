# 作業二 獨立審查(claude-b,2026-11-09,針對 commit b5f30a8)
**結論:有條件 PASS(技術面);尚不具「已繳交」條件——缺 GitHub 遠端與真人確認。** 這是 AI 審查,不是真人驗收。

## 已實際核對
- git:HEAD=b5f30a8,工作樹乾淨(0 未提交);`.gitignore` 排除 runtime/、.venv、.env、備份;tracked 1346 檔,最大檔 ~0.6MB,.git 4.8MB。
- 測試:`pytest -q tests` → **302 passed**(我重跑)。
- **容器內程式 = 主機 = HEAD**:在隔離 VM(riskscope-codex-apple-20261107)的容器 riskscope-portable 內比對 chat/reasoning/api/ledger 的 SHA-256,四個全部一致 → FULL PASS 證據對應最後版本。正式機 riskscope-machine 仍 "Never up",未動。
- 證據檔:`evidence/demo_scenarios_run_20261109.txt` 19 項 PASS、0 FAIL、3 次真實 LLM 回覆均 ACCEPTED(B 題為 success_with_unverified_numbers,即軟標示放行);檔內無 Token。
- README/腳本:README 指向 deploy/README_PODMAN.md;`riskscope.sh` 確有 build/up/smoke/restart-test/creds/purge/down;`demo_run.sh` 已改為 podman exec(正確)。README、VALIDATION_SUMMARY 已更新為 302 passed,舊「37 passed」「未驗證 LLM」已修。
- 安全:ACL、核准閘門、單位 fail-closed、核准宣稱攔截皆有測試與 Demo 證據(含 FAILURE_CASES F1–F4);K3→L 的改動僅放寬 `_SAFE_CLAIM_RE` 為軟標示,核准/驗證/可用/排名等仍硬拒絕(Claude A 敘述,我抽查程式碼與測試一致)。

## 缺陷 / 風險(請 Claude A 或使用者處理)
1. **無 GitHub remote**(`git remote -v` 空)。需要使用者提供/建立 repo 與權限;不得擅自建立公開庫。
2. **疑似 Token 字串留在已追蹤的舊測試 log**:`ai_progress/antigravity-acl-validation/baseline-test-run.log`(8 筆)、`ai_progress/codex-ollama/targeted-tests.txt`(3 筆)含 `Bearer xxxx…`。我比對目前 runtime 的 3 組 token **沒有命中**(應為測試暫存 DB 的一次性 token),但仍建議繳交前在**副本**遮蔽或排除這兩檔(我不改歷史檔)。
3. **主機 8100 目前被隔離 VM 的測試容器佔用**。若要恢復正式展示 8100,會埠衝突;繳交/恢復前先 `deploy/riskscope.sh down`(對 `--connection riskscope-codex-apple-20261107`)。預設 podman 連線指向正式 VM(目前停止),腳本在老師機器上沒問題,但本機操作需注意連線。
4. 只有 macOS(Apple Silicon、applehv)實測;**Windows/Linux 未實測**,文件需如實標示。
5. 展示依賴本機 Ollama 與 `qwen3:8b`;無模型時 smoke 會失敗(設計如此)。
6. 零份真人審查(HUMAN_REVIEW 7 題,僅 AI 預審);Holdout 仍封存。
7. 尚未看到 Claude A 的 `ASSIGNMENT2_FINAL_STATUS.md`。
8. 單容器+SQLite 是否符合「Agent/介面/檢索/工具/紀錄皆由 Podman 容器執行」:一個容器內含全部元件,屬於容器內執行,但若老師要求「分服務」則不足——需對照課程規範確認(待使用者/老師)。

## 老師可用的啟動指令(已由 Claude A 實測於 macOS)
```
deploy/riskscope.sh build && deploy/riskscope.sh up
deploy/demo_run.sh
```
需:Podman ≥4.4、Ollama + `qwen3:8b`(Linux/Windows 需 OLLAMA_HOST=0.0.0.0,見 deploy/README_PODMAN.md)。
