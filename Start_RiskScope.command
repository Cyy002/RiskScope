#!/bin/bash
# RiskScope 一鍵啟動（macOS：在 Finder 雙擊；Linux：bash Start_RiskScope.command）
# 流程：檢查 Podman → 檢查本機 Ollama 模型 → 建置／啟動容器 → 健康檢查 → 顯示登入 Token → 開啟瀏覽器
set -u
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/opt/podman/bin:$HOME/.local/podman/bin:$PATH"
NAME=${RS_NAME:-riskscope-portable}
PORT=${RS_PORT:-8100}
MODEL=${OLLAMA_MODEL:-qwen3:8b}
URL="http://127.0.0.1:$PORT"

ok()    { printf "  ✓ %s\n" "$1"; }
warn()  { printf "  ! %s\n" "$1"; }
title() { printf "\n[%s] %s\n" "$1" "$2"; }
fail()  { printf "\n  ✗ %s\n\n" "$1"; read -r -p "按 Enter 關閉視窗…" _; exit 1; }

echo "=========================================="
echo "  RiskScope 跨領域 AI 決策與風險分析系統"
echo "=========================================="

title 1/5 "檢查 Podman"
command -v podman >/dev/null || fail "找不到 Podman，請先安裝：https://podman.io/docs/installation"
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
if TAGS=$(curl -fs --max-time 3 http://127.0.0.1:11434/api/tags); then
  if echo "$TAGS" | grep -q "\"name\":\"$MODEL\""; then
    ok "Ollama 已啟動，模型 $MODEL 可用"
  else
    warn "Ollama 已啟動，但尚未下載模型 $MODEL"
    read -r -p "  現在下載 $MODEL（約 5 GB）？[y/N] " ans
    if [ "$ans" = y ] || [ "$ans" = Y ]; then
      ollama pull "$MODEL" && ok "模型下載完成" || warn "下載失敗，系統將改用固定模板回覆"
    else
      warn "略過下載，系統將改用固定模板回覆"
    fi
  fi
else
  warn "偵測不到 Ollama（http://127.0.0.1:11434）。系統仍可運作，但回覆改用固定模板。"
  warn "啟用本機模型：安裝 Ollama 後執行 ollama serve 與 ollama pull $MODEL，再重新執行本檔。"
fi

title 3/5 "準備 RiskScope 容器"
if podman container exists "$NAME" 2>/dev/null; then
  if [ "$(podman container inspect "$NAME" --format '{{.State.Running}}')" = true ]; then
    ok "容器 $NAME 已在執行"
  else
    podman start "$NAME" >/dev/null || fail "容器啟動失敗"
    ok "已啟動既有容器 $NAME（沿用原有資料）"
  fi
else
  echo "  首次執行：建置映像（第一次需下載基礎映像，約數分鐘）…"
  deploy/riskscope.sh build || fail "建置失敗，請參考 deploy/README_PODMAN.md 的常見問題"
  deploy/riskscope.sh up >/dev/null || fail "啟動失敗，請參考 deploy/README_PODMAN.md 的常見問題"
  ok "容器已建置並啟動"
fi

title 4/5 "健康檢查"
for _ in $(seq 1 30); do curl -fs "$URL/health" >/dev/null && break; sleep 2; done
curl -fs "$URL/health" >/dev/null || fail "系統沒有回應：$URL/health"
ok "系統運作正常：$URL"

title 5/5 "登入資訊"
CREDS=$(podman exec "$NAME" cat /app/runtime/demo_credentials.json 2>/dev/null)
tok() { echo "$CREDS" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | sed 's/.*"\([^"]*\)"$/\1/'; }
M=$(tok manager); E=$(tok engineer); O=$(tok outsider)
[ -n "$M" ] || fail "無法讀取登入 Token"
echo "  本機測試 Token（每台電腦首次啟動時自動產生，請勿公開）："
echo "    manager  管理者：可查看全部資料、核准變更、查看稽核紀錄"
echo "             $M"
echo "    engineer 工程師：可分析、提出變更，但不能核准"
echo "             $E"
echo "    outsider 無專案權限：用於驗證存取會被拒絕"
echo "             $O"
if command -v pbcopy >/dev/null; then
  printf %s "$M" | pbcopy && ok "manager Token 已複製到剪貼簿，在登入畫面直接貼上即可"
fi

echo
echo "正在開啟瀏覽器：$URL"
if command -v open >/dev/null; then open "$URL"; elif command -v xdg-open >/dev/null; then xdg-open "$URL"; fi
echo
echo "固定測試案例：ai_progress/ASSIGNMENT2/DEMO_RUNBOOK.md"
echo "停止系統：podman stop $NAME"
echo
read -r -p "按 Enter 關閉此視窗（系統會繼續在背景執行）" _
