#!/usr/bin/env bash
# Batch F (claude-b 2026-11-04): app E2E with Claude A's patched reasoning.py (BB01 14-week fix), then noise-floor repeats (D x2, D2 x2, A1 x1 on 8B), then app E2E 27B (reply timeout raised to 300s -- 120s default timed out the 27B reasoning call on 2/12). Shared lock; new output dirs only.
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline_resume.log; export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23
step() { local lab=$1 tt=$2; shift 2; for try in 1 2; do $Q -t "$tt" -w 43200 "$lab#$try" "$@"; rc=$?; echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> $L; [ $rc = 0 ] && return 0; done; return 1; }
J() { step "$1" 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/$2 --out $S/runs/$2/_judge.json; }
OLLAMA_MODEL=qwen3:8b step app3-8b 7200 $PY $S/tools/run_cases.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/appE2E3patched_qwen3-8b --llm --only $IDS12
J japp3-8b appE2E3patched_qwen3-8b
for n in 2 3; do
  OLLAMA_MODEL=qwen3:8b step d-rep$n 5400 $PY $S/tools/proto_d_prompt.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/armDrep${n}_qwen3-8b --only $IDS12; J jd-rep$n armDrep${n}_qwen3-8b
  OLLAMA_MODEL=qwen3:8b step d2-rep$n 5400 $PY $S/tools/proto_d_prompt.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/armD2rep${n}_qwen3-8b --only $IDS12 --no-isolation; J jd2-rep$n armD2rep${n}_qwen3-8b
done
OLLAMA_MODEL=qwen3:8b step a1-rep 5400 $PY $S/tools/run_direct_qwen.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/direct_rep1_qwen3-8b --only $IDS12
step ja1-rep 5400 $PY $S/tools/judge_answers.py --kind direct --run $S/runs/direct_rep1_qwen3-8b --out $S/runs/direct_rep1_qwen3-8b/_judge.json
OLLAMA_MODEL=qwen3.6:27b step app3-27b 14400 env OLLAMA_REPLY_TIMEOUT_SECONDS=300 $PY $S/tools/run_cases.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/appE2E3patched_qwen3.6-27b --llm --only $IDS12
J japp3-27b appE2E3patched_qwen3.6-27b
echo "$(date +%H:%M:%S) BATCH F DONE" >> $L
