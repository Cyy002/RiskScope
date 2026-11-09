#!/usr/bin/env bash
# judge the RAW free-form answers (before the app safety layer) to quantify correct analyses discarded by M7/schedule checks/timeouts
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline_resume.log; export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
for d in appNEW_g_r1_qwen3-8b_RAWFREEFORM appNEW_g_r2_qwen3-8b_RAWFREEFORM appNEW_g_r3_qwen3-8b_RAWFREEFORM appNEW_g_r1_qwen3.6-27b_RAWFREEFORM; do
  $Q -t 5400 -w 43200 "jraw-$d" $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/$d --out $S/runs/$d/_judge.json; echo "$(date +%H:%M:%S) STEP jraw-$d rc=$?" >> $L
done
echo "$(date +%H:%M:%S) RAW JUDGE DONE" >> $L; afplay /System/Library/Sounds/Glass.aiff 2>/dev/null; say "原始回答評分完成" 2>/dev/null
