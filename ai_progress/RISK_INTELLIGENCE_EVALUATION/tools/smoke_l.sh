#!/usr/bin/env bash
# Batch L smoke-check (Claude A, 2026-11-09): NOT a new full acceptance round.
# Bounded, single-run-per-model check of exactly the 3 cases touched by this
# session's _NEGATION_LOOKBACK_RE / _SAFE_CLAIM_RE fixes (BB06, BB14, BB16),
# to get real evidence before moving on to Podman/delivery work, per the
# explicit "stop chasing model scores" instruction -- this is a targeted
# regression smoke-check, not another score-maximizing batch.
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline_resume.log
ABS_PY="$(cd "$(dirname "$PY")" && pwd)/$(basename "$PY")"
export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS=BB06,BB14,BB16

step() {
  local lab=$1 tt=$2; shift 2
  for try in 1 2; do
    "$Q" -t "$tt" -w 21600 "$lab#$try" "$@"; rc=$?
    echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> "$L"
    [ $rc = 0 ] && return 0
  done
  echo "$(date +%H:%M:%S) STEP $lab FAILED after 2 tries -- not retrying further" >> "$L"
  return 1
}

run_and_judge() {
  local lab=$1 model=$2 tt=$3 reply_to=$4 outdir=$5
  if [ -f "$S/runs/$outdir/_judge.json" ]; then
    echo "$(date +%H:%M:%S) SKIP $lab (already judged)" >> "$L"; return 0
  fi
  OLLAMA_MODEL=$model step "$lab" "$tt" env OLLAMA_REPLY_TIMEOUT_SECONDS=$reply_to \
    "$ABS_PY" "$S/tools/run_cases.py" --cases "$S/BENCHMARK_CASES/dev" --out "$S/runs/$outdir" --llm --only $IDS || return 1
  step "j$lab" 3600 "$ABS_PY" "$S/tools/judge_answers.py" --kind riskscope --run "$S/runs/$outdir" --out "$S/runs/$outdir/_judge.json" || return 1
}

echo "$(date +%H:%M:%S) BATCH L SMOKE START" >> "$L"
OK=1
run_and_judge "appl-8b" qwen3:8b 3600 180 "appFIXED_l_qwen3-8b" || OK=0
run_and_judge "appl-27b" qwen3.6:27b 5400 300 "appFIXED_l_qwen3.6-27b" || OK=0

if [ "$OK" = 1 ]; then
  echo "$(date +%H:%M:%S) BATCH L SMOKE DONE -- see runs/appFIXED_l_qwen3-8b and runs/appFIXED_l_qwen3.6-27b" >> "$L"
  afplay /System/Library/Sounds/Glass.aiff 2>/dev/null
  say "小範圍模型驗證跑完了" 2>/dev/null
else
  echo "$(date +%H:%M:%S) BATCH L SMOKE FAILED" >> "$L"
  afplay /System/Library/Sounds/Basso.aiff 2>/dev/null
  say "小範圍模型驗證失敗，需要人工檢查" 2>/dev/null
  exit 1
fi
