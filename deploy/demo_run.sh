#!/usr/bin/env bash
# RiskScope 期末展示一鍵執行腳本 (Demo Runner)
# 供評審、教授與助教進行期末四重情境驗收：
#   展示 A：工程決策 (名目額定 vs 實際可用容量)
#   展示 B：跨領域決策 (供應商延誤與硬性限制比對)
#   展示 C：安全與權限 (401/403/DOC-CONF 機密分級/未核准阻擋)
#   展示 D：Podman 跨平台重現 (生命週期與持久化)

set -euo pipefail
cd "$(dirname "$0")/.."

NAME=${RS_NAME:-riskscope-portable}
PORT=${RS_PORT:-8100}
URL="http://127.0.0.1:$PORT"

echo "========================================================================"
echo "  RiskScope 期末展示驗收套件 (Podman Portable Environment)"
echo "========================================================================"
echo "目標端點: $URL  容器: $NAME"

# 1. 確保 image 已建置、容器已啟動並通過 /health
if ! podman image exists "${RS_IMAGE:-localhost/riskscope-portable:1.0}" 2>/dev/null; then
    echo "[INFO] 找不到 image，先建置..."
    deploy/riskscope.sh build
fi
if ! curl -fs "$URL/health" >/dev/null 2>&1; then
    echo "[INFO] 容器未在 $PORT 埠運行，啟動中..."
    deploy/riskscope.sh up
fi

echo "[INFO] 服務運作中，開始執行四大展示情境驗收..."
echo ""

# 2. scripts/demo_scenarios.py 的設計就是要在容器內執行（寫死連 127.0.0.1:8000
#    和容器內的 /app/runtime/demo_credentials.json），絕對不能在主機上直接跑
#    python，即使主機有 Python 也一樣會因為埠號與憑證路徑不符而失敗。
podman exec "$NAME" python scripts/demo_scenarios.py
rc=$?
echo ""
echo "========================================================================"
if [ $rc -eq 0 ]; then echo "  展示驗收完成！(FULL PASS)"; else echo "  展示驗收未全過，請查看上面輸出 (exit $rc)"; fi
echo "========================================================================"
exit $rc
