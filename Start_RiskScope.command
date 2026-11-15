#!/bin/bash
# RiskScope 一鍵啟動（macOS：在 Finder 雙擊；Linux：bash Start_RiskScope.command）
# 流程：檢查 Podman → 檢查本機 Ollama 模型 → 建置／啟動容器 → 健康檢查 → 顯示登入 Token → 開啟瀏覽器
set -u
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/opt/podman/bin:${HOME}/.local/podman/bin:${PATH}"
NAME=${RS_NAME:-riskscope-portable}
PORT=${RS_PORT:-8100}
MODEL=${OLLAMA_MODEL:-qwen3:8b}
URL="http://127.0.0.1:${PORT}"

ok()    { printf "  ✓ %s\n" "$1"; }
warn()  { printf "  ! %s\n" "$1"; }
title() { printf "\n[%s] %s\n" "$1" "$2"; }
fail()  { printf "\n  ✗ %s\n\n" "$1"; read -r -p "按 Enter 關閉視窗…" _; exit 1; }

echo "=========================================="
echo "  RiskScope 跨領域 AI 決策與風險分析系統"
echo "=========================================="

title 0/5 "檢查電腦資源"
if [ "$(uname)" = Darwin ]; then MEM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 )); else MEM_GB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1048576 )); fi
FREE_GB=$(( $(df -Pk "${HOME}" | awk 'NR==2{print $4}') / 1048576 ))
[ "${MEM_GB}" -ge 16 ] && ok "記憶體 ${MEM_GB} GB" || warn "記憶體 ${MEM_GB} GB（建議 16 GB 以上；本機模型回覆可能較慢）"
[ "${FREE_GB}" -ge 15 ] && ok "可用磁碟 ${FREE_GB} GB" || warn "可用磁碟 ${FREE_GB} GB（首次安裝約需 15 GB：模型 5 GB、Podman 虛擬機與映像）"

title 1/5 "檢查 Podman"
ask() { read -r -p "  $1 [Y/n] " a; [ "$a" != n ] && [ "$a" != N ]; }
if ! command -v podman >/dev/null; then
  warn "這台電腦尚未安裝 Podman"
  if [ "$(uname)" = Darwin ] && ask "自動下載並安裝 Podman？（約 100 MB，需輸入電腦登入密碼）"; then
    PKG=/tmp/podman-installer.pkg
    curl -fL --progress-bar -o "${PKG}" https://github.com/containers/podman/releases/latest/download/podman-installer-macos-universal.pkg \
      || fail "Podman 下載失敗，請改從 https://podman.io 手動安裝"
    sudo installer -pkg "${PKG}" -target / || fail "Podman 安裝失敗"
    export PATH="/opt/podman/bin:${PATH}"
  fi
  command -v podman >/dev/null || fail "找不到 Podman，請先安裝：https://podman.io/docs/installation"
fi
ok "$(podman --version)"
if ! podman info >/dev/null 2>&1; then
  if [ "$(uname)" = Darwin ]; then
    if [ -z "$(podman machine list --format '{{.Name}}' 2>/dev/null)" ]; then
      echo "  首次使用：初始化 Podman 虛擬機（約 1–3 分鐘）…"
      podman machine init || fail "podman machine init 失敗"
    fi
    echo "  啟動 Podman 虛擬機…"
    podman machine start >/dev/null 2>&1
    podman info >/dev/null 2>&1 || fail "無法連線 Podman，請開啟 Podman Desktop 確認虛擬機狀態"
  else
    fail "無法連線 Podman 服務"
  fi
fi
ok "Podman 已就緒"

title 2/5 "檢查本機 LLM（Ollama）"
OLLAMA_APP=/Applications/Ollama.app
ollama_up() { curl -fs --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null; }
wait_ollama() { for _ in $(seq 1 30); do ollama_up && return 0; sleep 2; done; return 1; }
if ! ollama_up && [ "$(uname)" = Darwin ]; then
  if [ ! -d "${OLLAMA_APP}" ] && ! command -v ollama >/dev/null; then
    warn "這台電腦尚未安裝 Ollama（本機 LLM 服務）"
    if ask "自動下載並安裝 Ollama？（約 200 MB）"; then
      curl -fL --progress-bar -o /tmp/Ollama-darwin.zip https://ollama.com/download/Ollama-darwin.zip \
        && unzip -q -o /tmp/Ollama-darwin.zip -d /Applications && ok "Ollama 已安裝" || warn "Ollama 安裝失敗"
    fi
  fi
  if [ -d "${OLLAMA_APP}" ]; then echo "  啟動 Ollama…"; open -g -a Ollama; wait_ollama || warn "Ollama 啟動逾時"; fi
fi
command -v ollama >/dev/null || { [ -x "${OLLAMA_APP}/Contents/Resources/ollama" ] && export PATH="${OLLAMA_APP}/Contents/Resources:${PATH}"; }
if TAGS=$(curl -fs --max-time 3 http://127.0.0.1:11434/api/tags); then
  if echo "${TAGS}" | grep -q "\"name\":\"${MODEL}\""; then
    ok "Ollama 已啟動，模型 ${MODEL} 可用"
    echo "  預先載入模型（避免第一題遇到冷啟動逾時，約 10–60 秒）…"
    curl -fs --max-time 180 http://127.0.0.1:11434/api/generate -d "{\"model\":\"${MODEL}\",\"prompt\":\"\",\"keep_alive\":\"30m\"}" >/dev/null \
      && ok "模型已載入記憶體" || warn "模型預先載入未完成，第一題可能較慢"
  else
    warn "Ollama 已啟動，但尚未下載模型 ${MODEL}"
    if ask "現在下載 ${MODEL}？（約 5 GB，依網速需數分鐘）"; then
      ollama pull "${MODEL}" && ok "模型下載完成" || warn "下載失敗，系統將改用固定模板回覆"
    else
      warn "略過下載，系統將改用固定模板回覆"
    fi
  fi
else
  warn "偵測不到 Ollama（http://127.0.0.1:11434）。系統仍可運作，但回覆改用固定模板。"
  warn "啟用本機模型：安裝 Ollama 後執行 ollama serve 與 ollama pull ${MODEL}，再重新執行本檔。"
fi

title 3/5 "準備 RiskScope 容器"
port_busy() { (echo > "/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1; }
if ! podman container exists "${NAME}" 2>/dev/null && port_busy "${PORT}"; then
  for p in $(seq $((PORT+1)) $((PORT+20))); do port_busy "$p" || { warn "Port ${PORT} 已被其他程式使用，改用 $p"; PORT=$p; break; }; done
  export RS_PORT=${PORT}; URL="http://127.0.0.1:${PORT}"
fi
if podman container exists "${NAME}" 2>/dev/null; then
  HP=$(podman container inspect "${NAME}" --format '{{range $p, $b := .HostConfig.PortBindings}}{{range $b}}{{.HostPort}}{{end}}{{end}}' 2>/dev/null)
  [ -n "${HP}" ] && PORT=${HP} && URL="http://127.0.0.1:${PORT}"
  if [ "$(podman container inspect "${NAME}" --format '{{.State.Running}}')" = true ]; then
    ok "容器 ${NAME} 已在執行"
  else
    podman start "${NAME}" >/dev/null || fail "容器啟動失敗"
    ok "已啟動既有容器 ${NAME}（沿用原有資料）"
  fi
else
  echo "  首次執行：建置映像（第一次需下載基礎映像，約數分鐘）…"
  deploy/riskscope.sh build || fail "建置失敗，請參考 deploy/README_PODMAN.md 的常見問題"
  deploy/riskscope.sh up >/dev/null || fail "啟動失敗，請參考 deploy/README_PODMAN.md 的常見問題"
  ok "容器已建置並啟動"
fi

title 4/5 "健康檢查"
for _ in $(seq 1 30); do curl -fs "${URL}/health" >/dev/null && break; sleep 2; done
curl -fs "${URL}/health" >/dev/null || fail "系統沒有回應：${URL}/health"
ok "系統運作正常：${URL}"
if podman exec "${NAME}" python -c "import urllib.request,os;urllib.request.urlopen(os.environ.get('OLLAMA_URL','http://host.containers.internal:11434')+'/api/tags',timeout=3)" >/dev/null 2>&1; then
  ok "容器可以連到本機 Ollama"
else
  warn "容器連不到本機 Ollama，回覆會改用固定模板（確認 Ollama 已啟動後重新執行本檔）"
fi

title 5/5 "登入資訊"
CREDS=$(podman exec "${NAME}" cat /app/runtime/demo_credentials.json 2>/dev/null)
tok() { echo "${CREDS}" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | sed 's/.*"\([^"]*\)"$/\1/'; }
M=$(tok manager); E=$(tok engineer); O=$(tok outsider)
[ -n "${M}" ] || fail "無法讀取登入 Token"
echo "  本機測試 Token（每台電腦首次啟動時自動產生，請勿公開）："
echo "    manager  管理者：可查看全部資料、核准變更、查看稽核紀錄"
echo "             ${M}"
echo "    engineer 工程師：可分析、提出變更，但不能核准"
echo "             ${E}"
echo "    outsider 無專案權限：用於驗證存取會被拒絕"
echo "             ${O}"
ok "瀏覽器將以 manager 身分自動登入；要切換角色，點左下角「登出／更換身分」貼上其他 Token"

echo
echo "正在開啟瀏覽器：${URL}"
LOGIN_URL="${URL}/#token=${M}"
if command -v open >/dev/null; then
  open "${LOGIN_URL}"
  # 瀏覽器開啟後，把本視窗叫回最前面，確保先看到下方操作教學
  sleep 3
  case "${TERM_PROGRAM:-}" in
    Apple_Terminal) open -a Terminal ;;
    iTerm.app)      open -a iTerm ;;
  esac
elif command -v xdg-open >/dev/null; then
  xdg-open "${LOGIN_URL}"
fi
cat <<GUIDE

==========================================
  操作教學（瀏覽器已用 manager 身分登入）
==========================================
瀏覽器已在後方開啟，請先閱讀本教學，再切換到瀏覽器照步驟操作。
輸入範例請逐字複製；本機模型每題約需 30–60 秒。

【第一部分｜固定測資：對話式 Agent】
 步驟 1  左側點「對話式 Agent」，評估情境保持「馬達升級與負載」。
 步驟 2  輸入並按「送出」：
           電源24V，名目額定10A，實際可用8A，馬達11A，輔助3A，電流夠嗎？
         預期：總電流 14A、總功率 336W；超出名目額定 40%、超出實際可用 75%；
               方案 A（僅更換馬達）為 blocked；回覆下方標示「本機 LLM 轉述」。
 步驟 3  在同一個對話繼續輸入：
           只將馬達改成9A，其餘完全不變。
         預期：12A／288W，並與上一輪比較（電流 -2A、功率 -48W）。
 步驟 4  繼續輸入：
           電源額定一直是10A，實際可用一直是8A，我只修改馬達。
         預期：維持 12A，不會誤判為電源規格被修改。
 步驟 5  按「開啟新對話」，評估情境改為「供應商交期」，輸入：
           關鍵供應商交貨延遲，品質驗證尚未完成，客戶交期不能延後，也不得更換供應商。應該如何決策？
         預期：分列已知事實與未知條件，不自行捏造成本或延誤天數。

【第二部分｜人工核准流程】
 步驟 6  左側點「決策推演」，直接按「開始分析」（使用預設問題）。
         在結果最下方「人工審核／模擬操作」選 TEST-01、blocked，按「提出模擬變更申請」。
 步驟 7  左側點「人工審核」，在申請清單按「核准」（跳出確認視窗按「確定」），
         再按「執行模擬變更」並確定；狀態依序變為 approved → executed。
 步驟 8  左側點「操作稽核」，可看到申請、核准、執行的完整紀錄。

【第三部分｜權限驗證】
 步驟 9  左下角「登出／更換身分」，貼上 engineer Token 登入（右上角顯示「研發工程師 · editor」）：
         可提出變更申請，但「人工審核」不會出現核准／執行按鈕；
         「資料與證據」看不到機密文件 DOC-CONF（manager 看得到）。
 步驟 10 再登出並貼上 outsider Token：登入被拒，顯示「此帳號沒有 demo-chamber 專案存取權限」。

【第四部分｜自由測試】
 換回 manager Token，在「對話式 Agent」自由提問，例如更換數值、要求保證、
 或要求系統忽略規則直接核准，觀察系統是否守住計算結果與人工審核界線。

完整說明：README.md、ai_progress/ASSIGNMENT2/DEMO_RUNBOOK.md
停止系統：podman stop ${NAME}
更新程式後重新建置：podman rm -f ${NAME}，再重新執行本檔（資料保留在 volume）
GUIDE
echo
read -r -p "按 Enter 關閉此視窗（系統會繼續在背景執行）" _ || true
