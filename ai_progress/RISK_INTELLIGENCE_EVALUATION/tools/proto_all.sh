#!/usr/bin/env bash
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; IDS=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23
until grep -q "^done" /tmp/judge_all.log 2>/dev/null; do sleep 30; done
Q() { $S/tools/ollama_queue.sh "$1" "${@:2}"; }
OLLAMA_MODEL=qwen3:8b Q proto8 .venv/bin/python $S/tools/proto_llm_led.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/proto_qwen3-8b --only $IDS
JUDGE_MODEL=qwen3.6:27b Q judge_proto8 .venv/bin/python $S/tools/judge_answers.py --kind riskscope --run $S/runs/proto_qwen3-8b --out $S/runs/proto_qwen3-8b/_judge.json
OLLAMA_MODEL=qwen3.6:27b Q proto27 .venv/bin/python $S/tools/proto_llm_led.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/proto_qwen3.6-27b --only $IDS
JUDGE_MODEL=qwen3.6:27b Q judge_proto27 .venv/bin/python $S/tools/judge_answers.py --kind riskscope --run $S/runs/proto_qwen3.6-27b --out $S/runs/proto_qwen3.6-27b/_judge.json
echo done
