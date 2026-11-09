#!/usr/bin/env bash
# waits for any other run_cases process (avoid concurrent Ollama load), then runs the 27B high-difficulty set
cd "$(dirname "$0")/../../.."
while pgrep -f "tools/run_cases.py" >/dev/null; do sleep 20; done
export OLLAMA_URL=http://127.0.0.1:11434 OLLAMA_MODEL=qwen3.6:27b
.venv/bin/python ai_progress/RISK_INTELLIGENCE_EVALUATION/tools/run_cases.py --cases ai_progress/RISK_INTELLIGENCE_EVALUATION/BENCHMARK_CASES/dev \
  --out ai_progress/RISK_INTELLIGENCE_EVALUATION/runs/baseline12_qwen3.6-27b --llm --only BB02,BB06,BB07,BB11,BB14,BB16,BB23 > /tmp/b27.log 2>&1
echo done >> /tmp/b27.log
