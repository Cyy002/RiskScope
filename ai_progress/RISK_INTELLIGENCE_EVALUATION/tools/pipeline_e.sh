#!/usr/bin/env bash
# Selection-phase batch (claude-b, 2026-11-04): ablation (prompt-only), D repeat (noise estimate), app E2E re-run after Claude A's per-item filtering. Shared lock, 2 tries, log /tmp/pipeline_resume.log.
cd "$(dirname "$0")/../../.."
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; L=/tmp/pipeline_resume.log; export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23
step() { local lab=$1 tt=$2; shift 2; for try in 1 2; do $Q -t "$tt" -w 43200 "$lab#$try" "$@"; rc=$?; echo "$(date +%H:%M:%S) STEP $lab try$try rc=$rc" >> $L; [ $rc = 0 ] && return 0; done; return 1; }
J() { step "$1" 5400 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/$2 --out $S/runs/$2/_judge.json; }
OLLAMA_MODEL=qwen3:8b step d2-8b 5400 $PY $S/tools/proto_d_prompt.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/armD2promptonly_qwen3-8b --only $IDS12 --no-isolation
J jd2-8b armD2promptonly_qwen3-8b
OLLAMA_MODEL=qwen3:8b step drep-8b 5400 $PY $S/tools/proto_d_prompt.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/armDrep_qwen3-8b --only $IDS12
J jdrep-8b armDrep_qwen3-8b
OLLAMA_MODEL=qwen3:8b step app2-8b 7200 $PY $S/tools/run_cases.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/appE2E2peritem_qwen3-8b --llm --only $IDS12
J japp2-8b appE2E2peritem_qwen3-8b
OLLAMA_MODEL=qwen3.6:27b step d2-27b 14400 $PY $S/tools/proto_d_prompt.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/armD2promptonly_qwen3.6-27b --only $IDS12 --no-isolation
J jd2-27b armD2promptonly_qwen3.6-27b
OLLAMA_MODEL=qwen3.6:27b step app2-27b 14400 $PY $S/tools/run_cases.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/appE2E2peritem_qwen3.6-27b --llm --only $IDS12
J japp2-27b appE2E2peritem_qwen3.6-27b
echo "$(date +%H:%M:%S) SELECTION BATCH DONE" >> $L
