#!/usr/bin/env bash
# Re-run of the judging steps that failed at 22:07 (cause: relative --cases default; fixed). Same lock gate, timeouts, 2 tries.
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline.log; export JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23; A5=BB03,BB17,BB20,BB21,BB27
step() { local lab=$1 tt=$2; shift 2; for try in 1 2; do $Q -t "$tt" -w 21600 "$lab#$try" "$@"; rc=$?; echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> $L; [ $rc = 0 ] && return 0; done; return 1; }
step judge-d27 5400 $PY $S/tools/judge_answers.py --kind direct --run $S/runs/direct_qwen3.6-27b --out $S/runs/direct_qwen3.6-27b/_judge.json
step judge-d8 3600 $PY $S/tools/judge_answers.py --kind direct --run $S/runs/direct_qwen3-8b --out $S/runs/direct_qwen3-8b/_judge.json
step judge-rs27 3600 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/baseline12_qwen3.6-27b --out $S/runs/baseline12_qwen3.6-27b/_judge.json
step judge-rs27b 3600 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/claude-b_real_qwen3.6-27b_5cases_v2 --out $S/runs/claude-b_real_qwen3.6-27b_5cases_v2/_judge.json
step judge-rs8 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/_baseline_8b_all30 --out $S/runs/_baseline_8b_all30/_judge_subset.json --only $IDS12,$A5
echo "$(date +%H:%M:%S) JUDGES DONE" >> $L
