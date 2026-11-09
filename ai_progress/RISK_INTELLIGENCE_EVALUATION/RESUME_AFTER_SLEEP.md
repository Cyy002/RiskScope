# Safe stop at 23:20 (claude-b) — nothing is running; every completed output is preserved. Resume commands (run from project root, one batch at a time, ALWAYS via the queue gate)
State at stop: no pipeline/queue/model processes, lock released, models unloaded from Ollama, production :8000 and demo :8100 untouched. Claude A is rate-limited until 01:30.
## Completed & judged
- A1 direct Qwen: 8B 12/12, 27B 17/17 (raw answers saved) — NOT yet judged
- B-v1 (LLM-led, before binding fix): 8B 17 cases (judge mean 63.5), 27B 12 cases (judge mean 94.6, self-judged) — `runs/proto_*/_judge.json`
- A0 old RiskScope: 8B 30 / 27B 12 (mechanical scorer 5.6 / ≈6.5); LLM-judge NOT yet run
- Offline v1 replay binding metrics: `runs/proto_qwen3-8b/_binding_metrics_v1_replay.json`
## Interrupted
- B-v2 (binding-verified) 8B: 14/17 done in `runs/protoV2_qwen3-8b` (BB01..BB20); crashed at BB21 on a None value — FIXED (binding status order + renderer guard, test added). Remaining: BB21,BB23,BB27. v2 27B not started.
- Judging of A1/A0 and v2: not run (the earlier `judge-*` steps failed 22:07 on a relative path — fixed; later ones were stopped by this wrap-up).
## Resume (in this order; each is one queue-gated step; ~2.5 h total)
```
S=ai_progress/RISK_INTELLIGENCE_EVALUATION; Q=$S/tools/ollama_queue.sh; PY=.venv/bin/python; export OLLAMA_URL=http://127.0.0.1:11434 JUDGE_MODEL=qwen3.6:27b
IDS12=BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23; A5=BB03,BB17,BB20,BB21,BB27
OLLAMA_MODEL=qwen3:8b $Q v2-8b-rest $PY $S/tools/proto_llm_led_v2.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/protoV2_qwen3-8b --only BB21,BB23,BB27
$Q jd27 $PY $S/tools/judge_answers.py --kind direct --run $S/runs/direct_qwen3.6-27b --out $S/runs/direct_qwen3.6-27b/_judge.json
$Q jd8  $PY $S/tools/judge_answers.py --kind direct --run $S/runs/direct_qwen3-8b --out $S/runs/direct_qwen3-8b/_judge.json
$Q jrs27 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/baseline12_qwen3.6-27b --out $S/runs/baseline12_qwen3.6-27b/_judge.json
$Q jrs27b $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/claude-b_real_qwen3.6-27b_5cases_v2 --out $S/runs/claude-b_real_qwen3.6-27b_5cases_v2/_judge.json
$Q jrs8 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/_baseline_8b_all30 --out $S/runs/_baseline_8b_all30/_judge_subset.json --only $IDS12,$A5
$Q jv28 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/protoV2_qwen3-8b --out $S/runs/protoV2_qwen3-8b/_judge.json
OLLAMA_MODEL=qwen3.6:27b $Q v2-27b $PY $S/tools/proto_llm_led_v2.py --cases $S/BENCHMARK_CASES/dev --out $S/runs/protoV2_qwen3.6-27b --only $IDS12
$Q jv227 $PY $S/tools/judge_answers.py --kind riskscope --run $S/runs/protoV2_qwen3.6-27b --out $S/runs/protoV2_qwen3.6-27b/_judge.json
```
Then: `tools/binding_metrics.py` on v2 dirs, 3-way table (A0/A1/B-v1/B-v2), human spot-check ≥6 cases, adoption decision, Holdout only on a stable candidate (still sealed).
## Notes
- Judge for 27B answers is the same model → bias; deterministic caps + human spot-check required before any adoption claim.
- Claude A (back ~01:30) was mid-edit on app/reasoning.py (several of its tests fail mid-edit; not caused by app/binding.py/ledger.py).
- The two real-Ollama pytest flakes should be re-run when Ollama is idle.
