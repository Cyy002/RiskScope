#!/usr/bin/env bash
# Batch G = acceptance of the REWORKED integrated app (start ONLY after Claude A reports the generic-path rewrite done + tests green). Shared lock; new dirs only.
# 8B x3 (same 12 cases, same judge) + 27B x1 (preliminary, not a statistic). Log /tmp/pipeline_resume.log
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline_resume.log; export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23; TAG=${1:-g}
step() { local lab=$1 tt=$2; shift 2; for try in 1 2; do $Q -t "$tt" -w 43200 "$lab#$try" "$@"; rc=$?; echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> $L; [ $rc = 0 ] && return 0; done; return 1; }
J() { step "$1" 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/$2 --out $S/runs/$2/_judge.json; }
for n in 1 2 3; do
  OLLAMA_MODEL=qwen3:8b step app$TAG-8b-r$n 7200 $PY $S/tools/run_cases.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/appNEW_${TAG}_r${n}_qwen3-8b --llm --only $IDS12
  J japp$TAG-8b-r$n appNEW_${TAG}_r${n}_qwen3-8b
done
OLLAMA_MODEL=qwen3.6:27b step app$TAG-27b 14400 env OLLAMA_REPLY_TIMEOUT_SECONDS=300 $PY $S/tools/run_cases.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/appNEW_${TAG}_r1_qwen3.6-27b --llm --only $IDS12
J japp$TAG-27b appNEW_${TAG}_r1_qwen3.6-27b
echo "$(date +%H:%M:%S) BATCH G ($TAG) DONE" >> $L
afplay /System/Library/Sounds/Glass.aiff 2>/dev/null; say "RiskScope 整合 App 驗收批次跑完了" 2>/dev/null
