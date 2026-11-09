#!/usr/bin/env bash
# RiskScope 期末展示一鍵執行腳本 (Demo Runner)
# 供評審、教授與助教進行期末四重情境驗收：
#   展示 A：工程決策 (名目額定 vs 實際可用容量)
#   展示 B：跨領域決策 (供應商延誤與硬性限制比對)
#   展示 C：安全與權限 (401/403/DOC-CONF 機密分級/未核准阻擋)
#   展示 D：Podman 跨平台重現 (生命週期與持久化)

set -euo pipefail
cd "$(dirname "$0")/.."

PORT=${RS_PORT:-8100}
URL="http://127.0.0.1:$PORT"

echo "========================================================================"
echo "  RiskScope 期末展示驗收套件 (Podman Portable Environment)"
echo "========================================================================"
echo "目標端點: $URL"

# 1. 檢查服務是否啟動
if ! curl -fs "$URL/health" >/dev/null 2>&1; then
    echo "[INFO] 獨立測試容器未在 $PORT 埠運行，嘗試啟動..."
    if [ -x deploy/riskscope.sh ]; then
        deploy/riskscope.sh up
    else
        echo "[ERROR] 找不到 deploy/riskscope.sh，請手動啟動容器。"
        exit 1
    fi
fi

echo "[INFO] 服務運作中，開始執行四大展示情境驗收..."
echo ""

# 2. 執行展示情境驗收腳本
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD=python
else
    # 在容器內執行
    echo "[INFO] 主機無 Python，切換至容器內執行..."
    podman exec -e RS_PORT=8000 riskscope-portable python scripts/demo_scenarios.py
    exit $?
fi

$PYTHON_CMD scripts/demo_scenarios.py
echo ""
echo "========================================================================"
echo "  展示驗收完成！"
echo "========================================================================"
