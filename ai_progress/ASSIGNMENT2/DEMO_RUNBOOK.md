# 作業二 Demo 操作流程與截圖清單(草稿;以實際可啟動的環境為準)
前置(Claude A 負責確認):Podman 容器啟動成功(`deploy/riskscope.sh up`,預設 http://127.0.0.1:8100)、宿主 Ollama 可連線、`deploy/riskscope.sh creds` 取得 manager/engineer/outsider token(**截圖前遮蔽 token**)。

**更新(Claude A,2026-11-09):** 原「Podman VM 停止」已處理——libkrun 後端在本機 abort,已改用獨立測試 VM
`riskscope-codex-apple-20261107`(applehv 後端,與正式機 `riskscope-machine` 完全分離)。`build`/`up`/
`/health`/`smoke`/`restart-test` **皆已實測通過**(見 `deploy/README_PODMAN.md` 開頭的 Tested status;
`smoke` 的 14A 決定性計算與真實 LLM 回覆皆 PASS,`restart-test` 確認重啟後憑證與分析紀錄完整保留)。
下方流程表的步驟 1–11 仍是草稿,截圖/錄影前建議在容器內逐步走一次確認,但前置條件(容器啟動成功)
已不再是阻塞項。

| # | 步驟 | 預期 | 截圖 |
|---|---|---|---|
| 1 | `podman ps` + `riskscope.sh smoke` | 容器運行、smoke 通過(LLM 實際被呼叫) | S1 終端機 |
| 2 | 瀏覽器開 UI,貼 engineer token | 登入成功,看見專案 | S2 |
| 3 | 問「電源24V、名目10A、實際可用8A、馬達11A、輔助3A,電流夠嗎?」 | 確定性工具:14A/336W,+40%/+75%,判不足 | S3 回覆+檢核卡 |
| 4 | 追問「只將馬達改成9A」 | 12A/288W,比較前後(多輪) | S4 |
| 5 | 跨域題:供應商延遲、驗證未完成 | 已知/未知/風險/方案比較(皆標未驗證)、可追溯來源 | S5 |
| 6 | 用 outsider token 開專案 | 403 拒絕 | S6(失敗案例 F1) |
| 7 | engineer 看不到 DOC-CONF,manager 看得到 | ACL 生效 | S7 |
| 8 | 建立動作→engineer 執行(403)→manager 核准→執行 | 模擬寫入,任務狀態改變,稽核紀錄 | S8–S9(F3 + 成功路徑) |
| 9 | 單位錯誤輸入(8 V) | 422 | S10(F2) |
| 10 | 提示注入文件/要求「直接宣稱安全」 | 工具仍判 fail、需人工審查(BB10 類) | S11 |
| 11 | 稽核頁(manager) | 可追溯紀錄 | S12 |
模型說謊攔截(F4)為 mock 驗證,Demo 以測試輸出 `failure_traces.json` 展示,勿口述為真實模型行為。
錄影建議:S3→S5→S6/S7→S8,約 5 分鐘;失敗案例可用 `python scripts/capture_failure_cases.py` 現場重現。
