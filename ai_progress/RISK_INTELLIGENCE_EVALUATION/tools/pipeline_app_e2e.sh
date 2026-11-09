#!/usr/bin/env bash
# End-to-end arm "B-app": the INTEGRATED app (chat_turn -> app/reasoning.py with whole-draft rejection) on the same 12 cases, real models, via the shared lock.
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline_resume.log; export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23
step() { local lab=$1 tt=$2; shift 2; for try in 1 2; do $Q -t "$tt" -w 36000 "$lab#$try" "$@"; rc=$?; echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> $L; [ $rc = 0 ] && return 0; done; return 1; }
OLLAMA_MODEL=qwen3:8b step app8 7200 $PY $S/tools/run_cases.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/appE2E_qwen3-8b --llm --only $IDS12
step japp8 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/appE2E_qwen3-8b --out $S/runs/appE2E_qwen3-8b/_judge.json
OLLAMA_MODEL=qwen3.6:27b step app27 14400 $PY $S/tools/run_cases.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/appE2E_qwen3.6-27b --llm --only $IDS12
step japp27 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/appE2E_qwen3.6-27b --out $S/runs/appE2E_qwen3.6-27b/_judge.json
echo "$(date +%H:%M:%S) APP E2E DONE" >> $L
