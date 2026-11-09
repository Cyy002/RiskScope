# RiskScope — 最終使用者驗收指南(整合 Podman 容器部署版本)

時間：2026-10-19 16:30(Asia/Taipei)。撰寫者：Claude。
取代 `ai_progress/90_USER_ACCEPTANCE_GUIDE.md`（那份是互動式 Agent 剛完成時、尚未有 Podman 部署的版本，保留作歷史紀錄，之後請以這份為準）。

本指南涵蓋 10 個驗收步驟：開啟 Podman Desktop → 確認容器狀態 → 開啟網頁 → 登入 → 自然語言分析 → 主動追問 → 工程數值補充 → Session 延續 → 分析依據與人工審核 → 資料持久化。**全程不包含任何真實 Token**，請自己依指示讀取。

## 0. 目前狀態摘要(操作前先知道)

- RiskScope 目前跑在 **Podman 容器**裡，容器名稱 `riskscope`，網址 **http://127.0.0.1:8000**。
- Podman Machine 名稱 `riskscope-machine`，資料存在 Podman volume `riskscope_runtime`（不是本機 `.venv` 專案目錄下的 `runtime/`，兩者是獨立的儲存位置）。
- 若要用**本機（非容器）**方式開啟，見第十一節，兩種方式資料互相獨立，不會互相覆寫。

## 一、開啟 Podman Desktop

打開 Launchpad 或 `/Applications`，啟動「**Podman Desktop**」。開啟後應該能在左側看到：
- **Machines** 分頁：`riskscope-machine`，狀態應顯示為運作中。
- **Containers** 分頁：`riskscope`，狀態應顯示為 running，連接埠 `8000`。

> 這一步**我沒有實際操作確認過**（這個執行環境沒有可互動的畫面），需要你自己打開確認畫面顯示正常。如果畫面空白或找不到 machine/container，請先不要重新安裝或重建，直接回報畫面實際顯示的內容。

## 二、確認容器狀態(終端機，選用，用來對照 Podman Desktop 畫面)

```sh
export PATH="$HOME/.local/podman/bin:$PATH"   # 新開的 Terminal.app 視窗通常已自動生效
podman ps
```
應該看到 `riskscope` 這一行，`STATUS` 顯示 `Up ...`。如果容器不在了：

> **⚠️ 下面這條指令已過時**：`riskscope-poc:0.1` 與 `--rm` 都不是目前建議的做法——`--rm` 正是 M12.2 查明的「podman machine 停止/重啟後容器被自動移除」的根因。最新已通過隔離驗收的映像是 `riskscope-poc:0.4`（M12.3，尚待授權正式部署）；正式操作請改看 `ai_progress/60_NEXT_HANDOFF.md`「容器生命週期與部署建議（M12.3）」一節。

```sh
podman machine start riskscope-machine   # 如果機器本身也停了
podman run --name riskscope --rm -d -p 127.0.0.1:8000:8000 \
  -e OLLAMA_URL=http://host.containers.internal:11434 \
  -e OLLAMA_MODEL=qwen3:8b \
  -v riskscope_runtime:/app/runtime \
  riskscope-poc:0.1
```
資料會從 `riskscope_runtime` volume 讀回，不會遺失。

## 三、開啟 RiskScope 網頁

瀏覽器打開 **http://127.0.0.1:8000**。應該看到登入畫面。

## 四、使用示範帳號登入

Token 不會出現在這份文件或任何對話紀錄裡,請自己執行：
```sh
podman exec riskscope cat /app/runtime/demo_credentials.json
```
會看到 `manager`／`engineer`／`outsider` 三組 Token，複製其中一組貼到登入畫面。一般驗收建議先用 **manager** 登入看全貌，再切換 **engineer** 測試權限邊界。

## 五、測試自然語言分析

登入後點左側選單「**對話式 Agent**」。直接用口語輸入,例如：
> 我想升級目前設備的馬達，請分析現有電源供應器是否能承受升級後的負載，並說明可能的風險與計算依據

送出後等待（本機 LLM 回覆通常需要 10-30 秒，視當下運算負載，偶爾會更久，若逾時系統會自動改用一樣詳細的確定性模板,不是錯誤)。應該看到具體列出：已確認工程條件、11A/264W 這類實際計算結果、風險、分析依據、尚未確定的條件、建議下一步——不會是籠統的一句話。

## 六、測試主動追問

預設示範資料是完整的，直接問不會觸發追問。要讓 Agent 真的因為缺資料而追問,需要先製造一個缺漏：

1. 用 **manager** Token 登入 **http://127.0.0.1:8000/docs**（FastAPI 內建的 API 操作介面，本機工具，非外部服務）。
2. 找到 `PATCH /api/projects/{project}/documents/{doc_id}/access`，`project` 填 `demo-chamber`，`doc_id` 填 `DOC-MOTOR`，body 填 `{"user_id":"engineer","enabled":false}`，執行。
3. 回網頁用 **engineer** 登入，進「對話式 Agent」，輸入「我想評估馬達升級，目前資料夠嗎？」送出。
   → 應該看到 Agent 回覆缺少授權相關資訊，列出建議追問，對話狀態顯示「持續中」。

## 七、測試工程數值補充

承接上一步（同一個對話，不要按「開啟新對話」），直接輸入一句包含數值的話，例如：
> 我量到的馬達連續電流大約是 8A

送出後應該看到：Agent 記錄了這個數值（註明「尚未經管理者正式確認」），並說明還缺少哪個欄位（例如電壓）。

## 八、測試 Session 延續

1. 回 `/docs`，把剛剛的 `DOC-MOTOR` 權限用同一個 PATCH 改回 `enabled:true`。
2. 回「對話式 Agent」頁面，**保持同一個對話**（頁面上會顯示目前的 session_id，不用手動改），輸入「權限已經恢復，請繼續分析」。
   → 應該看到 Agent 回覆「已確認解決」，對話狀態變成「本輪已完成」，且計算結果用的是文件裡的真實數值，**不是你剛才口頭提供的那個暫時值**（如果兩者剛好一樣，文件本身的值本來就是 8A，這是正常的，重點是文件被授權後優先權高於口頭暫存值）。

## 九、檢查分析依據與人工審核

在剛剛的分析結果畫面（或 API `/docs` 的 `GET /api/projects/demo-chamber/analyses/{analysis_id}`）往下找「facts」「checks」「risks」等欄位，確認每個數字都標註了來源文件 ID 與版本（例如 `DOC-PS v1`）。

測試人工審核：
1. 在分析結果畫面下方的「人工審核／模擬操作」區塊，提出一個模擬變更申請。
2. 用 **engineer** 身分嘗試自行核准——應該被拒絕（只有 manager 能核准）。
3. 用 **manager** 身分核准、再執行——應該成功，且 `simulated_tasks` 的狀態才會改變，不會在申請階段就被執行。

## 十、確認既有資料持久化

> **⚠️ 下面這條指令已過時**，理由同第二節；`podman stop riskscope` 若容器是用 `--rm` 啟動會直接消失，之後只能重新 `podman run`。改用無 `--rm` 的啟動方式後，`podman stop riskscope` / `podman start riskscope` 就能原地暫停/恢復同一個容器，不需要每次都重新 `run`。

```sh
podman stop riskscope
podman run --name riskscope --rm -d -p 127.0.0.1:8000:8000 \
  -e OLLAMA_URL=http://host.containers.internal:11434 \
  -e OLLAMA_MODEL=qwen3:8b \
  -v riskscope_runtime:/app/runtime \
  riskscope-poc:0.1
```
重新整理網頁，用同一個帳號登入，先前的對話紀錄、分析結果、審核過的動作應該都還在——因為資料存在 `riskscope_runtime` volume，不會因為容器重啟而消失。

## 十一、本機（非容器）方式，作為備援

```sh
cd /Users/haochenglin/Documents/RiskScope_work/CrossDomainRiskAgent
export OLLAMA_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen3:8b
.venv/bin/python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```
**注意**：這個方式用的是本機專案目錄下的 `runtime/`，跟容器的 `riskscope_runtime` volume 是兩份完全獨立的資料，不會互通。兩種方式不要同時佔用 `8000` 連接埠（容器已經在用的話，本機方式請改用別的埠號，例如 `--port 8001`）。

## 十二、已知限制(照實說，不誇大)

- 自由文字還不能讓 Agent 自己判斷要分析哪個固定主題（`focus`），由畫面下拉選單或呼叫端指定。
- 本機 LLM 只負責轉述確定性結果，絕不負責計算、授權或執行；逾時會自動退回確定性模板，畫面會標示來源（「本機 LLM 轉述」或「確定性模板」）。
- 聊天框打的任何文字都不會變成正式規格，只在當輪暫時使用；真正要讓系統採信某個數值，必須由 manager 透過 `/docs` 的既有 API 正式操作。
- Podman Desktop GUI 畫面本身未經我本人操作確認（見第一節）。
- 這次用 `podman build`/`podman run` 直接指令部署，不是 `podman compose`（本機缺 compose provider），效果相同但指令不同於 `compose.yml` 裡寫的。
- 安裝方式不是標準流程（手動展開官方 `.pkg`，使用 `applehv` provider），相容性/維護風險待 Codex 獨立審查。

## 十三、驗收後如何關閉

```sh
podman stop riskscope          # 停止容器（資料保留在 volume）
podman machine stop riskscope-machine   # 連 Podman machine 也一起停止（選用）
```
下次要用時，照第二節重新啟動即可，資料都會保留。
