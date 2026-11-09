#!/usr/bin/env bash
# Resume driver (claude-b, 2026-11-03). Only the NOT-yet-done steps listed in RESUME_AFTER_SLEEP.md; every step through the shared lock; 2 tries; log /tmp/pipeline_resume.log.
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline_resume.log
export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23; A5=BB03,BB17,BB20,BB21,BB27
step() { local lab=$1 tt=$2; shift 2; for try in 1 2; do $Q -t "$tt" -w 28800 "$lab#$try" "$@"; rc=$?; echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> $L; [ $rc = 0 ] && return 0; done; echo "$(date +%H:%M:%S) STEP $lab FAILED after 2 tries -- continuing" >> $L; return 1; }
step real-ollama-pytest 900 env OLLAMA_URL=http://127.0.0.1:11434 OLLAMA_MODEL=qwen3:8b $PY -m pytest -q -p no:cacheprovider tests/test_chat_agent.py::test_chat_opportunistically_exercises_real_local_ollama_if_available tests/test_user_supplied_values.py::test_opportunistic_real_llm_extraction_if_available
OLLAMA_MODEL=qwen3:8b step v2-8b-rest 3600 $PY $S/tools/proto_llm_led_v2.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/protoV2_qwen3-8b --only BB21,BB23,BB27
step jd27 5400 $PY $S/tools/judge_answers.py --kind direct --run $S/runs/direct_qwen3.6-27b --out $S/runs/direct_qwen3.6-27b/_judge.json
step jd8 3600 $PY $S/tools/judge_answers.py --kind direct --run $S/runs/direct_qwen3-8b --out $S/runs/direct_qwen3-8b/_judge.json
step jrs27 3600 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/baseline12_qwen3.6-27b --out $S/runs/baseline12_qwen3.6-27b/_judge.json
step jrs27b 3600 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/claude-b_real_qwen3.6-27b_5cases_v2 --out $S/runs/claude-b_real_qwen3.6-27b_5cases_v2/_judge.json
step jrs8 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/_baseline_8b_all30 --out $S/runs/_baseline_8b_all30/_judge_subset.json --only $IDS12,$A5
step jv28 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/protoV2_qwen3-8b --out $S/runs/protoV2_qwen3-8b/_judge.json
OLLAMA_MODEL=qwen3.6:27b step v2-27b 10800 $PY $S/tools/proto_llm_led_v2.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/protoV2_qwen3.6-27b --only $IDS12
step jv227 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/protoV2_qwen3.6-27b --out $S/runs/protoV2_qwen3.6-27b/_judge.json
echo "$(date +%H:%M:%S) RESUME PIPELINE DONE" >> $L
