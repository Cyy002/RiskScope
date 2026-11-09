#!/usr/bin/env bash
# Single sequential driver (claude-b). Order requested by the user: direct-8B (already running, held) -> 27B compare remainder -> unified judging
# -> new-architecture 8B/27B experiment (+judging). Each step: run under the shared lock with timeout, up to 2 attempts, result logged to /tmp/pipeline.log.
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline.log
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23; A5=BB03,BB17,BB20,BB21,BB27
step() { # label timeout cmd...
  local lab=$1 tt=$2; shift 2
  for try in 1 2; do $Q -t "$tt" -w 14400 "$lab#$try" "$@"; rc=$?; echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> $L; [ $rc = 0 ] && return 0; done
  echo "$(date +%H:%M:%S) STEP $lab FAILED after 2 tries -- continuing" >> $L; return 1; }
export OLLAMA_URL=http://127.0.0.1:11434
if [ -n "$HOLD_PID" ]; then $Q --hold-pid "$HOLD_PID" "hold-direct8"; echo "$(date +%H:%M:%S) direct8 (pid $HOLD_PID) finished" >> $L; fi
OLLAMA_MODEL=qwen3.6:27b step direct27-A5 3600 $PY $S/tools/run_direct_qwen.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/direct_qwen3.6-27b --only $A5
export JUDGE_MODEL=qwen3.6:27b
step judge-d27 5400 $PY $S/tools/judge_answers.py --kind direct --run $S/runs/direct_qwen3.6-27b --out $S/runs/direct_qwen3.6-27b/_judge.json
step judge-d8 3600 $PY $S/tools/judge_answers.py --kind direct --run $S/runs/direct_qwen3-8b --out $S/runs/direct_qwen3-8b/_judge.json
step judge-rs27 3600 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/baseline12_qwen3.6-27b --out $S/runs/baseline12_qwen3.6-27b/_judge.json
step judge-rs27b 3600 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/claude-b_real_qwen3.6-27b_5cases_v2 --out $S/runs/claude-b_real_qwen3.6-27b_5cases_v2/_judge.json
step judge-rs8 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/_baseline_8b_all30 --out $S/runs/_baseline_8b_all30/_judge_subset.json --only $IDS12,$A5
OLLAMA_MODEL=qwen3:8b step proto8 5400 $PY $S/tools/proto_llm_led.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/proto_qwen3-8b --only $IDS12,$A5
step judge-proto8 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/proto_qwen3-8b --out $S/runs/proto_qwen3-8b/_judge.json
OLLAMA_MODEL=qwen3.6:27b step proto27 10800 $PY $S/tools/proto_llm_led.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/proto_qwen3.6-27b --only $IDS12
step judge-proto27 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/proto_qwen3.6-27b --out $S/runs/proto_qwen3.6-27b/_judge.json
echo "$(date +%H:%M:%S) PIPELINE DONE" >> $L
