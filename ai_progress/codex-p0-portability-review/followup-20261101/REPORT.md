# 持續獨立審查：部署失敗路徑與正式環境隔離

2026-11-01；Owner Codex；部署修正 Owner Claude-b。

本輪範圍是部署套件與驗收工具，不修改產品或部署程式。前次 `.env.example`／`.containerignore` 的兩個失敗已針對目前磁碟版本複驗為 **2 passed**；新增五項故障注入測試為 **5 failed**。這五項是待修問題，沒有為了變綠而修改預期。

## 新增已重現問題

| ID | 級別 | 位置（凍結版） | 重現與影響 | 建議最小修復 |
|---|---|---|---|---|
| DEP-01 | P1，阻擋隔離驗收 | deploy/riskscope.sh，HPORT 與 NETARGS 分支 | `RS_HOST_NETWORK=1 RS_PORT=8100` 通過保護後仍發出 `--network=host`；Containerfile 的 app 綁定仍是 `0.0.0.0:8000`。8000 防護與實際綁定不一致。主機網路指 Linux host 或 Podman VM 的 namespace，不可推論一定直接改動 Mac 網路。 | 在能驗證 app 綁定位址與非正式埠前拒絕此模式；健康探針不得把原有服務誤判為新容器就緒。 |
| DEP-02 | P1，正式映像保護 | deploy/riskscope.sh build；PowerShell 同樣讀 RS_IMAGE | `RS_IMAGE=localhost/riskscope-poc:0.4` 仍傳入 `podman build -t`。可重新指派正式標籤，雖不會立即換掉正在執行的容器，卻破壞正式版本／回滾標籤保證。 | 建置、啟動前拒絕受保護的正式映像名稱及等價標籤寫法，或限定 portable repository。 |
| DEP-03 | P1，憑證外洩 | deploy/riskscope.sh restart-test | 先將明文憑證寫入固定 `/tmp/rs_tok_before`；注入 `podman restart` exit 42，set -e 中止，留下 0644 檔案。固定路徑另有並行碰撞／符號連結風險。 | 在容器內計算 hash，只傳遞 hash；如需 tempfile 則 mktemp、umask 077、trap 清理，不輸出明文。 |
| DEP-04 | P1，非本專案資源刪除 | deploy/riskscope.sh purge/up/down；PS 同類路徑 | `RS_NAME=unrelated-workload RS_VOLUME=unrelated-data purge` 直接發出 rm。除三個精確保留值外沒有命名／所有權保護。 | 對容器與 volume 加專案 ownership label，破壞操作前驗證兩者；拒絕未認領既有資源，保留可控的明確遷移方式。 |
| DEP-05 | P1，驗收誤報 | scripts/portable_smoke.py 最後結果分支 | mock 回覆為 deterministic、reply diagnostic=not_configured，設定 `SMOKE_ALLOW_FALLBACK=1`；印出 NO-LLM 後最後卻是 `RESULT: PASS []` 且 exit 0。 | 結果分開 deterministic_pass 與 real_llm_pass；fallback-only 不得回報完整真實 Agent PASS，整合驗收要以明確欄位判斷。 |

故障注入測試皆使用假 podman/curl/sleep 與合成憑證，無模型推論或引擎操作。DEP-03 僅在測試複本將固定 `/tmp` 路徑導向 tmp_path；不讀寫真實 `/tmp/rs_tok_before`。其餘控制流程未改。DEP-05 的 HTTP 與數字均為故障注入 fixture，**不是真實 Agent 或真實模型驗收**。

## 靜態補充，尚未動態證實

- PowerShell 設 `$ErrorActionPreference='Stop'`，但沒有在每個 native podman 命令後檢查 `$LASTEXITCODE`；Windows PowerShell 的 native 非零 exit 可能不轉為 terminating error。無 PowerShell 執行證據，應補注入 build/run/restart/exec 非零的腳本驗收，不能標成 Windows 已過。
- `restart-test` 目前只比對一個 engineer token，後續 smoke 會建立新 session；不足以證明原有資料紀錄與 session 存活。應在重啟前後比對同一份既有 analysis/session ID、內容及憑證 hash。
- 跨平台模型 endpoint 的 allowlist 限制及 UID10001/volume 權限仍由部署與環境主力實測。
- 得知其他 Agent 使用 `$HOME/.local/podman/bin`；前輪「無 Podman」只表示當時執行器 PATH 與所查四個位置未找到，不代表使用者 Mac 未安裝。本輪未搶占其他 Agent 正在使用的引擎與模型資源。

## 測試與重現

前次修復：`prior_fixes.log`、`prior_fixes.xml`（2 passed，6 deselected）。

新增：`guard_results.log`、`guard_results.xml`（5 failed）；來源 `snapshot/` 與 `manifest.json` 保留問題版本。

```bash
# 凍結版重現：不操作真實 Podman
.venv/bin/python -m pytest ai_progress/codex-p0-portability-review/followup-20261101/test_deploy_guards.py -q -p no:cacheprovider

# 修復版針對性複驗；新結果另存，不覆寫原始失敗證據
P0_REVIEW_DEPLOY_SOURCE="$PWD" .venv/bin/python -m pytest ai_progress/codex-p0-portability-review/followup-20261101/test_deploy_guards.py -q -p no:cacheprovider
```

這是針對第一版腳本的契約測試。若修復新增 inspect/labels 或更改部署架構，需讓 fake podman 能模擬該協定、並補相符正例；不能單靠 fake 回覆不完整造成的拒絕就宣稱真實引擎通過。

## 秘密處理

過去工作紀錄出現的 **OpenAgents 工作區存取憑證** 應安排輪替；這與 RiskScope 正式登入 Token 是不同憑證，不能一併重置。此輪從既有本機 OpenAgents 設定讀取工作區認證，經 curl stdin 設定傳入，不把值放在 argv、stdout、報告或測試包。未變更任何憑證或刪除歷史稽核。

## 接續

已直接交接 Claude-b 修復，Codex 只複驗修改後的失敗契約；不重跑完整核心測試。共享佇列 `ACTIVE_TASK_QUEUE.md` 記錄相應 owner、阻礙與下一步。完整成品仍需核心修復、真實容器／模型／GUI與各平台證據，不能以本輪 mock 與靜態測試取代。
