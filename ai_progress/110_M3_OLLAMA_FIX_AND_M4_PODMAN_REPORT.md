# M3 — Ollama 真實整合修復 + M4 — Podman 部署前置檢查

執行者：Claude。時間：2026-10-19 15:10(Asia/Taipei)。
授權依據:使用者「RiskScope｜Claude 正式接手開發指令」。Codex 已完成最小重現診斷(`ai_progress/codex-ollama/`)但額度耗盡停止;本輪由 Claude 接手正式修復,直接採用 Codex 的診斷證據,沒有重新分析已確定的問題。

## 一、M3：修復的問題與根因

### 根因 1：`think:false` 未設定(主要根因,Codex 已定位到現象,Claude 找到確切修法)

Codex 的 `diagnostic-configured.json` 顯示:抽取呼叫 10.025 秒、回覆呼叫逾時(20.004 秒 ReadTimeout),且回應裡有 `thinking_chars: 384` 欄位。本機直接用 curl 測試 `qwen3:8b` 證實:這個模型預設會先輸出大量「思考」token 才給最終答案,是 Ollama `/api/generate` 可以用 `"think": false` 關閉的行為。實測:同一個抽取提示詞,熱機後從 ~10-20 秒降到 **0.3-1.7 秒**;回覆提示詞(內容已依 M5 加長)從 ~17-20 秒降到 **~8-17 秒**(視輸出長度,無思考 token 浪費)。

### 根因 2：`compose.yml` 沒有傳入 `OLLAMA_URL`/`OLLAMA_MODEL`

Codex 已確認。原始 `compose.yml` 完全沒有 `environment:` 區塊,容器裡的程式永遠讀不到這兩個變數,等於永遠停用 LLM。

### 根因 3(獨立發現,Codex 的測試檔已預先寫好斷言但尚待程式修正)：非字串 `response` 被誤判為成功

原始程式碼 `str(r.json().get('response',''))` 在 `response` 欄位是 `None`、`[]`、或字典時,會被 `str()` 轉成看起來「成功」的非空字串(例如 `str(None)` == `'None'`),導致系統誤判為已經拿到 LLM 回覆。這是獨立於逾時問題之外的真實 bug,由 Codex 預先寫好的 `tests/test_ollama_integration_codex.py::test_non_string_response_must_not_count_as_successful_llm` 測試在 Claude 接手後首次執行時抓到。

### 根因 4：例外處理過度籠統

原始 `except Exception: return None` 完全不區分「沒設定」「連不上」「模型不存在」「逾時」「格式錯誤」,使用者永遠只看到「確定性模板」,無從得知原因。

## 二、修改過的檔案

| 檔案 | 變更 |
|---|---|
| `app/llm_client.py`(新檔案) | 統一的 Ollama 呼叫器:`think:false`、`keep_alive`、嚴格區分 7 種狀態(`not_configured`/`connection_error`/`model_not_found`/`http_error`/`timeout`/`invalid_json`/`empty_response`/`success`),並修掉非字串 response 的誤判。不記錄 prompt/response 內容,只記錄狀態與耗時。 |
| `app/chat.py` | `_extract_user_supplied()`/`_llm_reply()` 改用 `llm_client.call_ollama()`;回覆品質同步改善(見下方 M5);回傳值新增 `llm_diagnostic`(狀態/耗時,不含敏感內容)。 |
| `app/analyzer.py` | `_safe_local_explanation()` 同步改用 `llm_client.call_ollama()`,錯誤訊息改為區分狀態,不再只顯示例外類別名稱。 |
| `compose.yml` | 新增 `environment:` 傳入 `OLLAMA_URL`/`OLLAMA_MODEL`(預設 `http://host.containers.internal:11434`,Podman 的主機閘道位址);新增 `healthcheck`(呼叫既有 `/health`,不需額外套件)。 |
| `.env.example`(新檔案) | 本機與容器兩種情境的環境變數範本,說明 `127.0.0.1` 在容器內不等於主機。 |
| `.gitignore` | 新增 `.env`。 |
| `tests/test_ollama_integration_codex.py` | 修正 2 處 `monkeypatch` 目標(`chat.OLLAMA_MODEL` → `config.OLLAMA_MODEL`,因為 Ollama 呼叫邏輯搬到 `llm_client.py` 後,正確的即時讀取來源變了);沒有修改任何斷言強度。 |
| `tests/test_chat_agent.py`、`tests/test_user_supplied_values.py` | 同步修正呼叫新的 `(text, diagnostic)` 回傳格式與正確的 monkeypatch 目標,斷言邏輯不變。 |

未修改:`app/actions.py`、`app/events.py`、`app/impact.py`、`app/retrieval.py`、`app/security.py`、`app/engineering.py`——ACL、人工核准、資料版本機制完全沒動。

## 三、實際測試指令與通過/失敗數量

```sh
.venv/bin/python -m pytest -q tests/test_ollama_integration_codex.py   # Codex 寫的 17 項模擬測試
→ 17 passed, 0 failed（接手前因 API 變動是 1 passed + 16 error；修正後全過，包含那個真實 bug）

.venv/bin/python -m pytest -q        # 全專案
→ 84 passed, 0 failed
   - tests/test_core.py: 37/37
   - tests/test_acl_regression.py: 6/6
   - tests/test_session_continuity.py: 6/6
   - tests/test_legacy_alert_safety.py: 2/2
   - tests/test_p1_multi_turn.py: 4/4
   - tests/test_chat_agent.py: 5/5
   - tests/test_user_supplied_values.py: 7/7
   - tests/test_ollama_integration_codex.py: 17/17（新）

.venv/bin/python -m scripts.evaluate   → 12 案 45/45 不變
.venv/bin/python -m pip check           → 乾淨
```

Codex 要求的 10 類測試涵蓋情況:
1. Ollama 正常回覆 ✅（`test_success_uses_model_text_and_persists_provenance`）
2. 環境變數缺失 ✅（`test_missing_or_disallowed_config_or_disabled_llm_makes_no_calls`）
3. 服務無法連線 ✅（`test_generation_failures_keep_deterministic_safety[connect]`）
4. 模型逾時 ✅（`[timeout]`）
5. 安全備援 ✅（全部失敗情境都驗證 `reply_source=deterministic_template` 且 ACL/資料表不變）
6. 真實 LLM 回覆來源 ✅（見下方第四節真實手動驗證，非模擬）
7. Session 延續 ✅（`tests/test_session_continuity.py`，M3 沒有修改這部分邏輯）
8. 使用者暫存數值 ✅（`test_extraction_can_succeed_while_reply_times_out`、`test_untrusted_extraction_is_validated_before_safe_fallback`）
9. ACL 權限 ✅（每個 Ollama 測試都用 `protected_rows()` 比對 facts/document_access/project_members/documents/actions/simulated_tasks 完全不變）
10. 人工核准流程 ✅（同上，`actions`/`simulated_tasks` 表在所有情境下都不變）

## 四、真實 LLM 成功回覆的證據(非模擬,本機實跑)

使用者範例問題:「我想升級目前設備的馬達，請分析現有電源供應器是否能承受升級後的負載，並說明可能的風險與計算依據」

- `llm_diagnostic`: `{'extract': {'status': 'success', 'elapsed_seconds': 0.315}, 'reply': {'status': 'success', 'elapsed_seconds': 29.759}}`
- `reply_source`: `llm_phrased`
- 回覆內容具體列出：已確認工程條件、11A/264W 的實際計算結果、R-POWER 等風險、分析依據（電源/馬達/輔助負載的電壓電流）、尚未確定條件（啟動電流/降額/散熱）、方案 A/B/C 狀態、建議下一步——完整逐字內容見本次對話紀錄，與下方 M5 章節一致。

## 五、M5 — 現有 Agent 回答品質改善(與 M3 同時完成,同一組程式改動)

**問題**：原本 `session.status=='closed'` 時,回覆一律是固定一句「已取得足夠資料完成本輪分析，詳見風險與方案；任何變更仍需人工審核後才能執行。」——即使確定性分析早就算出了具體數字、風險、依據。

**根因**：`_deterministic_reply()`(模板)和餵給 LLM 的 `safe_facts`(轉述用摘要)原本都只包含 `unknowns`/`questions_to_manager`/`session`/`risks`/`decision_status`,完全沒有放入 `facts`/`checks`(含 `numbers`/`reason`/`limitations`)/`options`——不是「資料沒有傳遞到位」的 bug,是原始設計範圍本來就沒打算講這麼細。

**修正**：兩條路徑(模板與 LLM 提示詞)都改成納入 `facts`/`checks.numbers`/`checks.reason`/`checks.limitations`/`options`,並要求「盡量具體提到已確認的工程條件、計算出的數字、主要風險、分析依據，以及尚未確定的條件與建議下一步」——對應使用者第五節列的六個項目。LLM 仍只能轉述這些已經算好的欄位,**沒有被要求或允許自己計算或下結論**,備用模板的語意邊界沒有放寬。

**驗證**：第四節的真實回覆已直接證明效果——六個項目全部具體呈現,沒有編造任何模板和 LLM 兩個版本之外的數字。確定性模板版本(`reply_source=deterministic_template`)也一樣詳細(見第四節前一次測試,逾時降級時的回覆內容同樣完整),確保 LLM 不可用時使用者也不會退回到含糊的單句話。

## 六、M4 — Podman 部署狀態(只做檢查與檔案修正,未安裝、未實測建置)

### 已完成的部署準備
- `Containerfile`：Python 3.12-slim 基底、安裝 `requirements.txt` + `requirements-langgraph.txt`、非 root 使用者(`risk`,uid 10001)、`/app/runtime` 持久化路徑、對外只 `EXPOSE 8000`。結構合理,**本次沒有修改**。
- `compose.yml`(本次修正)：新增 `environment:` 正確傳入 `OLLAMA_URL`(預設指向 `host.containers.internal`,Podman 主機閘道位址)/`OLLAMA_MODEL`;新增 `healthcheck`(呼叫既有 `/health`,用 Python 標準庫,不需額外套件);既有的 `riskscope_runtime` volume 與 `127.0.0.1:8000:8000`(只綁主機 loopback,不對外網暴露)維持不變。
- `app/config.py` 的 `local_ollama_url()` **早就**把 `host.containers.internal` 列入白名單——這代表原設計已經考慮過容器連回主機 Ollama 的情境,本次不需要改這個檔案。
- `.env.example`(新增)：說明本機與容器內 `127.0.0.1` 語意不同,給出容器情境該用的值。

### 尚未完成的必要項目
- **從未在這台機器上實際執行 `podman build`/`podman compose up`**，因為 `podman`/`docker`/`brew` 全部未安裝（已重複確認）。本次只做了檔案層級的準備與修正，**不宣稱容器部署已通過實測**。
- 沒有驗證 `requirements.txt`/`requirements-langgraph.txt` 在全新容器環境下的實際安裝行為（只能靜態檢視內容合理）。

### Mac 上需要的 Podman 元件(需使用者自行安裝/授權,本次未擅自安裝任何東西)
1. **Podman Desktop**（含 Podman CLI 與 GUI）或單獨的 Podman CLI + `podman-compose`/原生 `podman compose`（新版 Podman 已內建 compose 子命令）。
2. **Podman machine**（Mac 上 Podman 需要一個 Linux VM 才能跑容器）：`podman machine init` → `podman machine start`。這一步需要系統授權建立虛擬機，屬於使用者本次明確保留、不授權 Claude 自行執行的範圍。

### Podman 容器如何連接主機 Ollama(已在檔案層級準備好，待使用者有執行環境後驗證)
- 容器內的程式讀 `OLLAMA_URL=http://host.containers.internal:11434`，這是 Podman 提供的、容器可解析到 Mac 主機的特殊 DNS 名稱（compose.yml 已設為預設值）。
- `app/config.py` 的 `local_ollama_url()` 只允許 `localhost`/`127.0.0.1`/`::1`/`host.containers.internal` 四個主機名，其他（包含任何雲端位址）一律拒絕——這個白名單本次沒有放寬，維持「只能本機模型」的既有安全邊界。
- Mac 主機上的 Ollama 服務本身**不需要**也**不會**被放進容器，依企劃「LLM server 可保持在容器外」的例外部署方式。

### 需要使用者授權的安裝或設定(明確列出,等待指示)
1. 安裝 Podman Desktop（或 Podman CLI + compose 插件）。
2. 執行 `podman machine init` 並 `podman machine start`（建立/啟動 Linux VM）。
3. 確認 Mac 上的 Ollama 服務本身對外（對 Podman machine 這個 VM）可連線——預設 Ollama 只聽 `127.0.0.1`，如果 Podman machine 是獨立 VM，可能需要確認 Ollama 的監聽位址或 Podman 的 host-gateway 轉發設定是否正常（本次無法在沒有 Podman machine 的情況下實測這一步，留給使用者完成第 1、2 項後再驗證）。

使用者完成以上授權項目後，Claude 可以接續執行 `podman build`/`podman compose up -d` 並做第六節仍待驗證的健康檢查、網頁運作、端到端分析、重啟與資料持久化測試。

## 七、尚未完成事項

- Podman 實際建置、啟動、健康檢查、容器連接主機 Ollama、網頁端到端、重啟持久化——全部等待使用者完成第六節「需要使用者授權的安裝或設定」後才能實測。
- LLM 回覆延遲在這台機器上仍有變動(觀察到 0.3 秒到 30 秒都出現過，可能與主機同時載入的其他大型模型有關)，45 秒逾時留了餘裕但不是保證值；逾時時系統會正確降級為一樣詳細的確定性模板，不影響正確性，只影響是否用得到「LLM 轉述」的語氣。
- 本輪由 Claude 單人完成程式修正，尚待 Codex 額度恢復後對照自己原始診斷覆核修法是否正確；也尚待 Antigravity 獨立驗收。

## 八、安全或架構風險

- 沒有發現新的安全退化：所有 Ollama 相關測試都比對 `facts`/`document_access`/`project_members`/`documents`/`actions`/`simulated_tasks` 六張表在任何 LLM 失敗情境下完全不變。
- `llm_client.py` 的診斷訊息只記錄狀態字串與耗時數字，不記錄 prompt 或 response 內容，避免把專案資料寫進日誌。
- compose.yml 的 `environment:` 區塊使用 `${VAR:-default}` 語法，使用者可以用自己的 `.env` 覆寫，不會把任何密鑰寫死在檔案裡（本專案目前也沒有任何需要密鑰的外部服務）。
