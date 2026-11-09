# v0.1 實作驗證摘要

- 更新時間：2026-11-09（Claude A，修正過時的 37 passed 等舊數字，與 claude-b 的
  `ai_progress/ASSIGNMENT2/CONSISTENCY_REVIEW.md` 一致性核對對齊）。
- 自動化：`python -m pytest -q` → **302 passed, 0 failed**（含 ACL/Session/多輪對話/
  M7 安全護欄/跨專案隔離等回歸測試，詳見 `tests/`）。
- 工程檢核：合成 24 V、10 A 電源與 8 A + 3 A 同時負載 → 11 A / 264 W，規則 `fail`。不以此斷言實機必然故障。
- 12 個固定參考案例：直接依賴基準 recall **11/45 = 24.44%**；多層路徑 recall **45/45 = 100%**，precision **45/45 = 100%**。**此結果僅為已登錄的合成圖遍歷測試，不是跨領域風險推理品質評分。**
- UI：使用受限環境的 Chromium，將本機 API 代理給瀏覽器執行前端，通過管理者登入、總覽渲染、馬達負載分析、模擬任務變更申請並進入人工審核；無前端 JavaScript 例外。預覽在 `previews/`。
- API：測試覆蓋角色授權、ACL 撤銷、過期文件、單位不匹配、循環、核准、冪等、過期批准、事件去重、測試成功不誤報等。
- **真實 Ollama LLM**：已多輪驗證（`qwen3:8b`／`qwen3.6:27b`，見
  `ai_progress/RISK_INTELLIGENCE_EVALUATION/`Batch G–K3 的真實模型驗收紀錄），非僅
  mock。**但這些分數是「回答品質」的工程測試，不等於任何專業領域（供應鏈/排程/
  工程安全）的正式結論**，仍需人工審核。
- **Podman**：image 已用 `deploy/riskscope.sh build` 成功建置；容器已用
  `deploy/riskscope.sh up` 在一台獨立測試用 VM（`riskscope-codex-apple-20261107`，
  applehv 後端，與正式機 `riskscope-machine` 完全分開、未被觸碰）啟動並通過 `/health`
  檢查；`smoke`（決定性引擎 14A 計算 + 真實 LLM 回覆皆 PASS）與 `restart-test`
  （重啟後憑證雜湊與 3 筆分析紀錄完全一致）**均已實測通過**（Claude A，2026-11-09，
  Ollama 佇列閒置時的乾淨重跑；先前一次因與本機模型驗證批次搶佔 Ollama 資源導致逾時
  FAIL，非程式缺陷，已排除）。原始 `libkrun` 後端在此機器上會 abort，已改用
  `applehv` 後端繞過（兩者皆非正式機使用的設定，正式機設定未變更）。
- **尚未驗證**：LangGraph 安裝後完整 StateGraph 多節點路徑的大規模壓力測試、跨領域
  企業資料匯入及真實企業帳號/密鑰/事件串接——這些屬於 PoC 範圍外，沒有宣稱已完成。
