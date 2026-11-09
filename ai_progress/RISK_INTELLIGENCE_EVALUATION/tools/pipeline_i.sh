#!/usr/bin/env bash
# Batch I (Claude A, overnight 2026-11-07): acceptance of the FIXED integrated app
# (soft-flagged numeric citations instead of whole-reply rejection; schedule-conflict
# banner instead of silent template fallback; 8B/27B free-form timeout 180s/300s;
# electrical-field extraction skipped for non-motor_upgrade focus; CJK-numeral grounding
# fix). App version snapshotted at app_snapshots/appFIXED_i/ before this ran.
#
# Resumable: each run+judge PAIR is skipped if its _judge.json already exists (idempotent --
# safe to re-invoke after an interruption without redoing finished work). Bounded retry:
# step() tries at most twice (same convention as claude-b's pipeline_g.sh). All model calls
# go through tools/ollama_queue.sh's shared lock. New output dirs only -- never overwrites
# appNEW_g_* or any earlier run.
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline_resume.log
export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23; TAG=${1:-i}

step() {
  local lab=$1 tt=$2; shift 2
  for try in 1 2; do
    "$Q" -t "$tt" -w 43200 "$lab#$try" "$@"; rc=$?
    echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> "$L"
    [ $rc = 0 ] && return 0
  done
  echo "$(date +%H:%M:%S) STEP $lab FAILED after 2 tries -- not retrying further" >> "$L"
  return 1
}

run_and_judge() {
  # $1=label $2=model $3=timeout $4=reply_timeout_env_or_empty $5=outdir
  local lab=$1 model=$2 tt=$3 reply_to=$4 outdir=$5
  if [ -f "$S/runs/$outdir/_judge.json" ]; then
    echo "$(date +%H:%M:%S) SKIP $lab (already judged: runs/$outdir/_judge.json exists)" >> "$L"
    return 0
  fi
  if [ -n "$reply_to" ]; then
    OLLAMA_MODEL=$model step "$lab" "$tt" env OLLAMA_REPLY_TIMEOUT_SECONDS=$reply_to \
      "$PY" "$S/tools/run_cases.py" --cases "$S/BENCHMARK_CASES/dev" --out "$S/runs/$outdir" --llm --only $IDS12 || return 1
  else
    OLLAMA_MODEL=$model step "$lab" "$tt" \
      "$PY" "$S/tools/run_cases.py" --cases "$S/BENCHMARK_CASES/dev" --out "$S/runs/$outdir" --llm --only $IDS12 || return 1
  fi
  step "j$lab" 5400 "$PY" "$S/tools/judge_answers.py" --kind riskscope --run "$S/runs/$outdir" --out "$S/runs/$outdir/_judge.json" || return 1
}

echo "$(date +%H:%M:%S) BATCH I ($TAG) START" >> "$L"

for n in 1 2 3; do
  run_and_judge "app$TAG-8b-r$n" qwen3:8b 7200 "" "appFIXED_${TAG}_r${n}_qwen3-8b" || { echo "$(date +%H:%M:%S) BATCH I ($TAG) STOPPED -- run r$n failed twice" >> "$L"; exit 1; }
done
run_and_judge "app$TAG-27b" qwen3.6:27b 14400 300 "appFIXED_${TAG}_r1_qwen3.6-27b" || { echo "$(date +%H:%M:%S) BATCH I ($TAG) STOPPED -- 27B run failed twice" >> "$L"; exit 1; }

echo "$(date +%H:%M:%S) BATCH I ($TAG) METRICS" >> "$L"
ABS_PY="$(cd "$(dirname "$PY")" && pwd)/$(basename "$PY")"
METRICS_OK=1
( cd "$S" && "$ABS_PY" tools/app_metrics.py "appFIXED_${TAG}_r1_qwen3-8b" "appFIXED_${TAG}_r2_qwen3-8b" "appFIXED_${TAG}_r3_qwen3-8b" "appFIXED_${TAG}_r1_qwen3.6-27b" >> "/tmp/pipeline_i_metrics_${TAG}.txt" 2>&1 ) || METRICS_OK=0
( cd "$S" && "$ABS_PY" tools/compare_runs.py "A1=direct_qwen3-8b,direct_rep1_qwen3-8b" "D2=armD2promptonly_qwen3-8b,armD2rep2_qwen3-8b,armD2rep3_qwen3-8b" "D=armD_qwen3-8b,armDrep_qwen3-8b,armDrep2_qwen3-8b,armDrep3_qwen3-8b" "new_app_fixed=appFIXED_${TAG}_r1_qwen3-8b,appFIXED_${TAG}_r2_qwen3-8b,appFIXED_${TAG}_r3_qwen3-8b" >> "/tmp/pipeline_i_metrics_${TAG}.txt" 2>&1 ) || METRICS_OK=0

# Overnight fix (2026-11-07, user-flagged): the script used to print DONE
# unconditionally even if the metrics step itself failed (e.g. the earlier
# venv-path bug) -- a silent "success" label on top of a real failure is
# exactly the kind of false reporting this project explicitly forbids. The
# run+judge results themselves are correct and kept either way; only the
# DONE/FAILED label and chime message reflect whether metrics computation
# itself actually succeeded.
if [ "$METRICS_OK" = 1 ]; then
  echo "$(date +%H:%M:%S) BATCH I ($TAG) DONE -- metrics in /tmp/pipeline_i_metrics_${TAG}.txt" >> "$L"
  afplay /System/Library/Sounds/Glass.aiff 2>/dev/null; afplay /System/Library/Sounds/Glass.aiff 2>/dev/null
  say "修補後的驗收批次跑完了" 2>/dev/null
else
  echo "$(date +%H:%M:%S) BATCH I ($TAG) RUNS DONE BUT METRICS FAILED -- check /tmp/pipeline_i_metrics_${TAG}.txt" >> "$L"
  afplay /System/Library/Sounds/Basso.aiff 2>/dev/null
  say "驗收批次的模型測試跑完了，但統計步驟失敗，需要人工檢查" 2>/dev/null
  exit 1
fi
