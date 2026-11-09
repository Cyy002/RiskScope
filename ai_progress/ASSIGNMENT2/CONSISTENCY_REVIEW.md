# 文件與實際版本一致性核對(claude-b,2026-11-09)
實測:`pytest -q tests` → **298 passed**。
不一致(請 Claude A 修正,我未改 README 等核心交付文件以免衝突):
1. `VALIDATION_SUMMARY.md` 寫「37 passed」→ 實際 298。
2. `README.md` 第 6 節:「Ollama 文字生成功能也尚未取得實際 LLM 模型驗證」→ 已過時(Batch G–K3 為真實 Qwen 8B/27B 驗證;但仍非專業結論)。
3. 專案目錄**不是 git repository**(`git status` fatal)→ GitHub 繳交需 `git init`、.gitignore(排除 `runtime/`、token、`.venv`、`__pycache__`、`ai_progress/*/runs` 大檔)並確認無憑證。
4. `deploy/README_PODMAN.md` 的指令(`riskscope.sh build/up/smoke/restart-test/creds/purge`)與腳本存在,但 Codex 中斷前的 libkrun 問題未解,**容器實測狀態:未驗證**;README 不得宣稱已成功。
5. README 對「課程要求:Agent、介面、檢索、工具、紀錄服務皆由 Podman 容器執行」的對應說明需確認(目前單一容器 `riskscope`+SQLite;若老師要求分離服務,需 A 評估)。
6. HUMAN_REVIEW 7 題:資料包已備,**零份真人確認**。
