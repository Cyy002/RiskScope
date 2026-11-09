#!/usr/bin/env bash
# v2 (binding-verified) experiment, same cases / caps / judge as v1, same lock gate. Outputs to NEW dirs (v1 results untouched for Before/After).
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline.log; export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23; A5=BB03,BB17,BB20,BB21,BB27
step() { local lab=$1 tt=$2; shift 2; for try in 1 2; do $Q -t "$tt" -w 28800 "$lab#$try" "$@"; rc=$?; echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> $L; [ $rc = 0 ] && return 0; done; return 1; }
OLLAMA_MODEL=qwen3:8b step v2-proto8 5400 $PY $S/tools/proto_llm_led_v2.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/protoV2_qwen3-8b --only $IDS12,$A5
step v2-judge8 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/protoV2_qwen3-8b --out $S/runs/protoV2_qwen3-8b/_judge.json
OLLAMA_MODEL=qwen3.6:27b step v2-proto27 10800 $PY $S/tools/proto_llm_led_v2.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/protoV2_qwen3.6-27b --only $IDS12
step v2-judge27 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/protoV2_qwen3.6-27b --out $S/runs/protoV2_qwen3.6-27b/_judge.json
echo "$(date +%H:%M:%S) V2 DONE" >> $L
