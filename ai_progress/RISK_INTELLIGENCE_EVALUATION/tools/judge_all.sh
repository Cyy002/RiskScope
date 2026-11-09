#!/usr/bin/env bash
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; export JUDGE_MODEL=qwen3.6:27b
# wait until every direct/benchmark producer is gone (A's waiter included), then judge through the shared queue
while pgrep -f "run_direct_qwen.py|direct_qwen_compare|tools/run_cases.py|run_direct_all.sh|wait_then_27b" >/dev/null; do sleep 30; done
J() { $S/tools/ollama_queue.sh "judge:$1" .venv/bin/python $S/tools/judge_answers.py "${@:2}"; }
J d27 --kind direct --run $S/runs/direct_qwen3.6-27b --out $S/runs/direct_qwen3.6-27b/_judge.json
J d8  --kind direct --run $S/runs/direct_qwen3-8b --out $S/runs/direct_qwen3-8b/_judge.json
J rs27 --kind riskscope --run $S/runs/baseline12_qwen3.6-27b --out $S/runs/baseline12_qwen3.6-27b/_judge.json
J rs27b --kind riskscope --run $S/runs/claude-b_real_qwen3.6-27b_5cases_v2 --out $S/runs/claude-b_real_qwen3.6-27b_5cases_v2/_judge.json
J rs8 --kind riskscope --run $S/runs/_baseline_8b_all30 --out $S/runs/_baseline_8b_all30/_judge_subset.json --only BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23,BB03,BB17,BB20,BB21,BB27
echo done
