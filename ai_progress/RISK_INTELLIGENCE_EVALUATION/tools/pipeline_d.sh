#!/usr/bin/env bash
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline_resume.log; export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23
step() { local lab=$1 tt=$2; shift 2; for try in 1 2; do $Q -t "$tt" -w 43200 "$lab#$try" "$@"; rc=$?; echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> $L; [ $rc = 0 ] && return 0; done; return 1; }
OLLAMA_MODEL=qwen3:8b step d8 5400 $PY $S/tools/proto_d_prompt.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/armD_qwen3-8b --only $IDS12
step jd8b 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/armD_qwen3-8b --out $S/runs/armD_qwen3-8b/_judge.json
OLLAMA_MODEL=qwen3.6:27b step d27 14400 $PY $S/tools/proto_d_prompt.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/armD_qwen3.6-27b --only $IDS12
step jd27b 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/armD_qwen3.6-27b --out $S/runs/armD_qwen3.6-27b/_judge.json
echo "$(date +%H:%M:%S) ARM D DONE" >> $L
