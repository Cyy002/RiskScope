#!/usr/bin/env bash
cd "$(dirname "$0")/../../.."
while pgrep -f "tools/run_cases.py" >/dev/null; do sleep 20; done
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; IDS=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23
for M in qwen3.6:27b qwen3:8b; do N=$(echo $M | tr ':' '-'); OLLAMA_MODEL=$M .venv/bin/python $S/tools/run_direct_qwen.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/direct_$N --only $IDS; done > /tmp/direct.log 2>&1
echo done >> /tmp/direct.log
