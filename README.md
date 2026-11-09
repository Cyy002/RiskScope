# RiskScope — 跨領域 AI 專業決策與風險分析輔助系統（PoC v0.1）

> **可執行課程原型，不是企業正式決策系統。** 本專案依附件《跨領域 AI 專業決策與風險分析輔助系統》實作。採用自行建立的合成軟硬體整合研發案例，不包含真實企業、客戶、供應商或機密資料。

本專案不只提供概念文件；包含可操作的繁體中文 Web UI、REST API、SQLite 持久化、權限與來源版本管理、工程規格檢核、可追溯工程影響圖、人工核准與模擬執行、事件監測及自動測試。

> **作業二評分者請先看這裡**：`ai_progress/ASSIGNMENT2/`——`DEMO_EVIDENCE.md`（真實執行的核心能力證據：
> 對話/授權/工具檢查/方案比較/模擬核准/錯誤處理，含原始終端輸出）、`FAILURE_CASES.md`（4 個失敗案例，
> 誠實標示真實模型 vs. mock）、`DEMO_RUNBOOK.md`（截圖/錄影流程）、`CONSISTENCY_REVIEW.md`（文件與
> 實際版本一致性核對）。Podman 實測狀態見本文件第 2 節與 `deploy/README_PODMAN.md`。

## 1. 最快在 Mac / Windows / Linux 啟動

需要 Python **3.12 或 3.13**（建議 3.12）。在終端機執行：

```bash
cd CrossDomainRiskAgent
python3 -m venv .venv
source .venv/bin/activate  # Windows PowerShell 改用 .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m scripts.init_demo
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

開啟瀏覽器：**http://127.0.0.1:8000**

登入時需要本機動態產生的 Token（不是專案中寫死的密碼）。另開終端機，進入專案資料夾後執行：

```bash
cat runtime/demo_credentials.json
```

會看到三個身分的測試 Token：`manager`（管理者）、`engineer`（工程師）、`outsider`（無專案權限）。複製 **manager 對應的那一串字串** 到登入畫面即可。**切勿公開 runtime 目錄或 Token。**

如已經有 `runtime/agent.sqlite3`，再次啟動會沿用資料與 Token，不會覆寫現有記錄。如要全部重置合成測試環境，關閉服務後將 `runtime/` 移開，再重新執行初始化。

API 線上介面：**http://127.0.0.1:8000/docs**（實際 API 操作需填入 Bearer Token）。

### 本地 LangGraph（可選）

未安裝 LangGraph 時，系統使用**明確標記**的確定性循序編排，功能仍正常。若要讓相同的步驟實際走 LangGraph 狀態圖：

```bash
python -m pip install -r requirements-langgraph.txt
```

在 API 分析結果中，`orchestration` 會明確顯示 `langgraph` 或 `sequential_fallback`，不會偽稱已使用 LangGraph。**LangGraph 1.0.0 已安裝並整合驗證**（`pytest -q` 全套測試在此環境下執行，`orchestration=langgraph` 路徑已覆蓋）。

### 可選本機模型 Ollama

確定性工程檢核**不依賴任何 LLM**。如自行安裝並啟動本機 Ollama，再設定：

```bash
export OLLAMA_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen3:8b  # 需已在本機下載此模型
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

到「決策推演」勾選「本機 Ollama」即可要求額外說明。LLM 的內容被標註為**未驗證文字**，不影響工程數值、風險規則、審核狀態或自動執行。系統拒絕把 Ollama URL 指向一般遠端雲端網址。**真實 Qwen3 推理品質已多輪評估**（`qwen3:8b`／`qwen3.6:27b`，見 `ai_progress/RISK_INTELLIGENCE_EVALUATION/`），分數用於持續改善安全護欄，但評估結果本身不等於任何專業領域的正式結論。

## 2. Podman 部署（企劃指定技術）

若你已在 Mac 安裝 Podman，先啟動 Podman machine：

**Portable/demo entry (isolated, never touches any production deployment): see `deploy/README_PODMAN.md`** (`deploy/riskscope.sh` or `deploy\riskscope.ps1`; port 8100, volume `riskscope_portable_data`).

> Historical (0.1-era) commands using `riskscope`/`riskscope_runtime`/port 8000/`--rm` were removed from this README because they collide with the live production deployment.

初次 build 需要網路下載 Python 套件與 base image。**實機驗證（Claude A，2026-11-09）**：`deploy/riskscope.sh build` 成功建置、`up` 啟動容器並通過 `/health`
檢查、`smoke`（決定性引擎計算 + 真實 LLM 回覆）與 `restart-test`（重啟後憑證與分析紀錄完整保留）皆
**PASS**；完整紀錄見 `deploy/README_PODMAN.md` 開頭的「Tested status」。

**對應企劃第 181 行「LLM server 以外的介面、Agent、檢索、工具及紀錄服務均由 Podman 容器執行」**：
單一 `riskscope`/`riskscope-portable` 容器裡的 FastAPI 行程已同時包含網頁介面（`app/static/`）、
Agent 對話邏輯（`app/chat.py`）、文件檢索（`app/retrieval.py`）、工程工具檢核（`app/engineering.py`）
與紀錄（`app/db.py` 寫入容器內 volume 掛載的 SQLite）——只有 LLM 推論本身（Ollama）照企劃明文排除
留在容器外、由主機提供。因此現狀已滿足此條款，不需要拆成多個容器。

## 3. 直接操作驗收

以 `manager` Token 登入 Web 後：

1. **決策推演**：保留預設範例，按「開始分析」。應取得 8 + 3 = **11 A**、24 × 11 = **264 W**，超出 PS-01 額定 10 A / 240 W。方案 A（只換馬達）標為 `blocked`；B、C 仍須驗證。絕不能聲稱設備必然跳脫或精確延誤天數。
2. **影響追蹤**：選 `M-02`，應看到 `DRIVER-01 → FIRMWARE-01 → TEST-01` 和 `MECH-01 → THERMAL-01 → TEST-01` 等來源已登錄的路徑，並標示來源 ID 與版本。
3. **人工審核**：分析下方申請將 `TEST-01` 標記 `blocked`；切到「人工審核」執行核准，然後再按「執行模擬變更」，專案首頁才會變成 `blocked`。注意這只更動 `simulated_tasks`。
4. **事件監測**：模擬供應商交期由 7 天變成 18 天；系統應建立一次內部提醒並完成新的 `event` 分析。相同來源/事件 ID 重複送出要去重。
5. **身分切換**：用 `engineer` 登入，無法看 `DOC-CONF`，也不能核准動作；用 `outsider` 登入應被拒絕。
6. **進階變更**：登入管理者後到 `/docs` 可操作文件更新、來源權限撤銷、規格人工再次確認、依賴新增等 API。對文件改版後，關聯數值會轉為 `unknown`，直到來源版本重新確認。

## 4. 可重現自動測試與固定案例

```bash
python -m pytest -q
python -m scripts.evaluate
```

`tests/test_core.py` 涵蓋：越權、來源 ACL、撤權後舊分析不可重讀、舊版文件不可沿用、單位維度/異常數值、Graph 循環與來源失效、未核准寫入、冪等申請、核准後版本變更、事件去重及測試 pass 不誤報。

`data/evaluation_cases.json` 是人工建的 **12 個固定合成案例**，包含影響路徑參考答案和兩個負例。`scripts.evaluate` 分別比較「只看直接依賴」和「多層依賴追蹤」的精確率/召回率；**這只衡量預先登錄的圖能否被正確遍歷，不等於 AI 真的學會工程判斷**。

> 維持獨立性：修改演算法後請不要依照 Agent 的新輸出反覆修改參考答案；新資料應另建立開發集。

## 5. 功能對照企劃 FR

| 規格項目 | 狀態 | 此版本實際交付 |
|---|---|---|
| FR-01 受控資料 | **實作** | API Token、專案成員角色、文件 ACL、撤權即時檢查；僅 demo 身分驗證 |
| FR-02 地端知識 | **實作** | 合成文件、文件修訂表、人工規格標註、來源 ID/版次、SQLite |
| FR-03 主動對話 | **實作** | 以決策問題選擇焦點、動態產生必要追問；多輪自然語言對話（同 session 先前訊息的事實會餵入後續回答，跨 session/專案/使用者皆已驗證不洩漏，見 `tests/test_reasoning_integration.py`） |
| FR-04 工具驗證 | **實作** | 單位維度、負載/功率計算、缺資料與來源版本回報 `unknown` |
| FR-05 決策分析 | **實作於範例** | 分離事實/推論/假設/未知、方案 A/B/C、必要風險與來源 |
| FR-06 人工審核 | **實作** | 待核准 → 批准/拒絕 → 僅模擬寫入；版本與冪等保護 |
| FR-07 決策狀態 | **實作** | 分析/工具結果/審核/操作稽核落地 SQLite |
| FR-08 多層影響 | **實作於合成圖** | 限深度圖遍歷、路徑/來源、去循環、過期/越權邊隱藏 |
| FR-09 雙模式 | **部分實作** | 手動對話入口 + 人工送出合成事件 → 分析 → 內部提醒；未做真正定期監控 |
| FR-10 時程支援 | **尚未實作定量** | 因欠缺工期，只呈現相關依賴，不偽造延期天數 |
| FR-11 企業連接器 | **未實作** | 未接 Email/Jira/GitHub/BOM 等 |
| FR-12 組織記憶 | **部分雛形** | 存分析與操作紀錄；尚未有成熟相似案例檢索/成效追蹤 |
| FR-13 跨領域擴充 | **部分實作並驗證** | 確定性工程檢核仍只有電源/馬達一個合成硬體案例；通用（非工程）問答路徑已用涵蓋軟體可靠度、供應鏈、排程、安全/合規等多領域的 `ai_progress/RISK_INTELLIGENCE_EVALUATION/BENCHMARK_CASES/` 真實模型測試，但結果仍是工程測試分數，不是任何領域的正式專業結論 |

## 6. 資安界線與已知限制（務必閱讀）

- 資料和 API Token 只保存在本機 SQLite / runtime；預設不會連接外部 AI。示範 Token **不等於** SSO、OAuth、企業權限整合。沒有 TLS、硬體金鑰管理、商用監控、備份策略、完整使用者生命週期功能。不要將服務開放到公網。
- 沒有外部通知功能，從程式上限制僅更動本機 `simulated_tasks`，不可能依本版程式直接改動客戶 Jira、設備或生產資料庫。
- 文件檢索是**授權後的簡易字詞/字串排序**，沒有成熟 RAG、向量索引、文件解析或語意校對；表格/掃描文件仍需另外做擷取處理。
- 工程規格目前只做明確的額定電流與電壓檢核；啟動電流、動態負載、選型裕量、熱、機構及時程並沒有完整實算器。若文件版次不同，原值一律回報未知，停止憑空結論。
- 人工重新驗證規格時會檢查該數值與單位是否出現在**最新授權文件文字**，但不代表已證明規格正確或符合實際工況，仍須工程師判斷。
- LangGraph 是可選編排；現有測試已在未安裝情況下驗證循序 fallback。Ollama 文字生成功能已用真實本機模型（`qwen3:8b`、`qwen3.6:27b`）多輪驗證（詳見
  `ai_progress/RISK_INTELLIGENCE_EVALUATION/`），但這些是「回答品質」的工程測試分數，**不等於**任何專業領域（供應鏈/排程/工程安全）的正式結論，所有結果仍需人工審核，不得直接當作可執行的專業判斷。
- 事件入口是**手動觸發**合成資料異動；尚未實作真正持續 polling、事件串流、企業通知。
- SQLite 適用單人/小型 PoC。真實多人同時使用應引入資料庫遷移、具認證的企業 DB、秘鑰輪替、審計不可竄改、可信時間戳及細粒度拒絕策略。

## 7. 檔案結構

```text
CrossDomainRiskAgent/
├── app/
│   ├── api.py          # REST / 驗證與管理者操作
│   ├── analyzer.py     # 決策流程 + 可選 LangGraph + 本機 LLM 補充
│   ├── db.py           # SQLite schema 與合成資料初始化
│   ├── security.py     # Token, Project role, Document ACL
│   ├── retrieval.py    # 權限前置過濾 + 來源/版次
│   ├── engineering.py  # 有單位的數值計算與 Unknown
│   ├── impact.py       # 可追溯、權限/版本-aware 圖遍歷
│   ├── actions.py      # 人工審核、版本防護與冪等性
│   ├── events.py       # 模擬事件、去重、再分析、內部提醒
│   └── static/         # 自主開發 HTML/CSS/JS（無 CDN）
├── data/evaluation_cases.json
├── tests/test_core.py
├── scripts/{init_demo.py,evaluate.py}
├── deploy/                # 可攜式 Podman 部署（build/up/smoke/restart-test），見 deploy/README_PODMAN.md
├── Containerfile / compose.yml
├── requirements*.txt
├── ARCHITECTURE_AND_HANDOFF.md
└── README.md
```

專案維護建議：先執行 `pytest -q`，再跑 `scripts.evaluate` 檢查固定基準；新功能請新增測試而不要刪掉原有安全性與 Unknown 防護。完整接手清單請見 [ARCHITECTURE_AND_HANDOFF.md](ARCHITECTURE_AND_HANDOFF.md)。
