# RiskScope v0.1 — Claude 對 Codex 兩項 ACL 缺口的獨立複核

執行者：Claude。日期：2026-10-18（Asia/Taipei）。
共用專案：`/Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent`
本階段僅驗證與根因分析，**未修改 app/ 下任何產品程式碼**，也未覆寫 `ai_progress/codex-p0/` 原始紀錄。

## 1. 複核方法

- 使用自己的 venv(`~/.local/bin/python3.12` 建立，`langgraph==1.0.0`，與交接文件指定版本一致）。
- 直接執行 Codex 的重現腳本 `ai_progress/codex-p0/verify_application.py`，但輸出目錄指向自己的 `ai_progress/claude-p0/`（避免覆寫 Codex 紀錄），參見同目錄 `application-probes.json`、`evaluation.json`。
- 執行結果與 Codex 回報一致：37 passed、`orchestration=langgraph`、11A/264W、12 案 45/45；兩項 ACL 缺口 `finding_reproduced` 皆為 `true`。
- 另外直接讀原始碼逐行核對，定位到造成兩項缺口的確切程式位置（見下）。

## 2. 缺口 A：撤權後舊分析仍回傳已撤銷來源的證據 — 根因確認

**位置：** `app/api.py:134-143` 的 `_analysis_access()`。

```python
def _analysis_access(c,actor,project,row):
    role=require_role(c,actor,project)
    if row['user_id']!=actor and role!='manager':
        raise HTTPException(403,'不能讀取他人的分析紀錄')
    result=json.loads(row['result_json'])
    for doc in result.get('documents',[]):          # <-- 只檢查這個 list
        if not document_permitted(c,actor,project,doc['id']):
            raise HTTPException(403,'該分析包含現已撤銷授權的來源；禁止重讀')
    return result
```

`result['documents']` 的來源是 `app/retrieval.py` 的檢索結果（top-8），而非分析實際使用到的所有來源。我追到兩個額外來源管道，兩者都**不受此 ACL 重驗證覆蓋**：

1. `app/engineering.py:40-44` — `power_continuous()` 呼叫 `read_facts()` 取得規格，組出 `evidence=[{'fact_key':k,'source_id':f['source_id'],...}]`。這份 `evidence` 寫進 `result['checks'][i]['evidence']`，`source_id` 可以是任何已驗證過的 fact 來源文件（例如 DOC-PS），**不要求該文件出現在 top-8 檢索結果裡**。
2. `app/impact.py:21,50` — `trace_impact()` 的每條路徑 edge 帶 `source_id`/`source_version`，寫進 `result['impacts'][i]['paths'][j]['evidence']`，同樣不經過 `result['documents']`。

因此，只要工具證據的來源文件不在當次 top-8 檢索清單內（Codex 用 8 份 distractor 文件製造此條件），`_analysis_access` 的迴圈就不會檢查到它，撤權後舊分析仍 200 回傳。我用自己的 venv 重跑腳本，確認：
`retrieved_documents` 只有 8 個 `DOC-P0-*`；`tool_evidence_documents` 含 `DOC-PS`；撤銷 `DOC-PS` 後 `fresh_check_status=unknown` 但 `stored_analysis_http_status=200` 且回應仍含 `DOC-PS`——與 Codex 回報一致。

**修正建議（與 Codex 一致，補充實作細節）：**
- 在 `_analysis_access` 增加一個「收集此分析全部來源」的 helper，遍歷 `result['documents']`、`result['checks'][*]['evidence'][*]['source_id']`、`result['impacts'][*]['paths'][*]['evidence'][*]['source_id']`（`result['sources']` 本身衍生自 `documents`，可不重複），對每個 `source_id` 呼叫 `document_permitted`。
- 更穩健的做法是在**寫入** `analyses` 表時，把分析實際用到的全部 `source_id` 正規化存成獨立欄位/表（例如 `analysis_sources(analysis_id, source_id)`），讀取時直接 JOIN 檢查，不必每次反解析巢狀 JSON 結構——避免未來新增欄位時又漏掉一處。

## 3. 缺口 B：內部提醒 (alerts) 繞過來源 ACL，洩漏受保護的依賴節點 — 根因確認

**位置：** `app/events.py:65-74`（寫入提醒內容）+ `app/api.py:208-212`（讀取提醒 endpoint）。

寫入端（`simulate_event`）：
```python
analysis = analyze(conn,actor,project,...,mode='event')   # actor = 觸發事件的 manager
...
f'可能受影響節點：{", ".join(analysis["impacts"][0]["affected_nodes"])}。'   # 用 manager 的 ACL 視角算出的節點，直接寫死進 alert body 文字
```

讀取端（`alerts` endpoint）：
```python
@app.get('/api/projects/{project}/alerts')
def alerts(project:str,s=Depends(session)):
    c,actor=s
    require_role(c,actor,project)     # 只檢查「是不是這個專案的成員」，不檢查個別來源/節點的 ACL
    return {'alerts':[dict(r) for r in c.execute('SELECT * FROM alerts WHERE project_id=? ...')]}
```

`affected_nodes` 是用**建立事件者**（通常是 manager，權限最大）的 ACL 視角算出，寫進 `alerts.body` 純文字後就與原始 ACL 脫鉤；任何之後讀取 `/alerts` 的專案成員都拿到同一份文字，不論自己當下對這些節點背後的來源文件有沒有權限。我重跑腳本確認：工程師被撤銷 `DOC-SUPPLIER`/`DOC-PLAN` 後，`/impact/SUPPLIER-01` 正確回空清單（`engineer_direct_affected_nodes: []`），但 `/alerts` 仍讀到含 `PROCURE-01` 等節點的 alert body——與 Codex 回報一致，且証明這不是「沒做 ACL」而是「兩條路徑不一致」：直接查詢有做 ACL 過濾，提醒文字沒有。

**修正建議（與 Codex 一致，補充實作細節）：**
- 不要把 `affected_nodes` 的具體節點 ID 直接拼進可被任何成員讀到的純文字 `body`；改成：alert 只存事件 metadata（signal_key/old/new/analysis_id），受影響節點清單另存結構化欄位，**讀取 `/alerts` 時依讀者當下 ACL 重新過濾節點清單**（可重用 `app/impact.py` 既有的 `document_permitted` 逐邊檢查邏輯），而不是重用建立者當時算好的結果。
- 這本質上與缺口 A 同一類問題：「分析/提醒在建立時間點算好的結果，被當作靜態文字長期快取，之後讀取時沒有用讀者的目前 ACL 重新驗證」。兩處修正可以共用同一個「以讀者身分重新過濾來源」的工具函式，避免各自實作出現第三個遺漏點。

## 4. 與 Codex 結論的比對

- 兩項缺口的重現結果（`finding_reproduced=true`）、數字（11A/264W、45/45、37 passed）與 Codex 完全一致，獨立複核通過。
- 根因定位一致，本次補充了：(1) 缺口 A 的「第三個洩漏管道」只有兩個（checks.evidence、impacts.paths.evidence），`sources` 欄位可排除、不需額外處理；(2) 兩個缺口本質上是同一種模式（建立時快取 vs 讀取時重驗證不一致），建議共用同一個修正用的 ACL 重過濾函式，減少未來第三處遺漏的風險。
- 尚未實作修正，等待 Copilot 依此交叉結論拆分不衝突的修正任務（例如：Codex 負責 `_analysis_access` 的來源收集；Claude 負責 `alerts` 讀取時重過濾），修正後再互相審查。

## 5. 可查核證據

- `ai_progress/claude-p0/application-probes.json`：本次獨立重跑腳本的完整輸出（`finding_reproduced` 兩項皆 `true`）。
- `ai_progress/claude-p0/evaluation.json`：12 案評估重現。
- 原始程式位置：`app/api.py:134-143`、`app/api.py:208-212`、`app/engineering.py:40-44`、`app/impact.py:21,50`、`app/events.py:65-74`。
