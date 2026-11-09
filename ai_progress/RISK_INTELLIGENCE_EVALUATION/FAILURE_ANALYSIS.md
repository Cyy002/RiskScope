# FAILURE_ANALYSIS — why the answers have no decision value (claude-b; tags from tools/score_run.py + reading raw replies)
Counts below are over the 30 8B cases / 12 27B cases (`_scores.json` root_cause_tags).

| Root-cause class (user's list) | Evidence | 8B /30 | 27B /12 |
|---|---|---|---|
| **Generic advice / fixed 3-option scaffold** (≈ "生成空泛建議") | identical structured output (facts∅, risk R-UNVALIDATED-ANALYSIS, options G-A/B/C unverified) for every case | 30 | 12 |
| **Reasoning too shallow / no causal analysis** | no critical path, heat, budget, probability, sensitivity in any reply; dependency graph empty for `custom` focus | 30 | 12 |
| **Cannot compare options / no risk ranking** | options fixed & unverified; severity is a literal string | 30 | 12 |
| **Numeric derivation absent** (專業知識/數值推導) | required computed answers (10 週, 312.5 °C, −60 萬, 23.2 min, 29.6 h, 26.4 %, 2.67 年…) appear 0 times | 18 of those with answers not echoed | all |
| **Project data not used** (專案資料) | case documents retrieved only as `sources`; the LLM prompt (`safe_facts`) contains question + scaffold, **no document text**; deterministic synthesis reads only `project_signals` | all | all |
| **M7 over-rejection** | numbers copied from the user's own question/doc ("9週","30天","200萬元","8週") rejected as "no trusted source"; 27B rejected 11 of 13 turns (8B 7 of 33) | 5 | 4 |
| **Hard constraints not engaged** | constraint detection = 2 literal Chinese phrases; others (e.g. 壓測不可省略, 凍結 BOM, 人力不可增補) never used | 11 | 3 |
| **Contradiction undetected** | BB05/BB27 (14 vs 35 天; conflicting dates) never surfaced | 2 | 1 |
| **Multi-turn context not reflected** | BB06 second turn text identical to first; no previous-plan state outside the electrical module | all multi-turn | BB06 |
| **Extraction role confusion** | non-motor questions pass through the electrical extractor: "12V→5V,1.5A" recorded as supply/motor fields | 1 | 1 |
| Professional knowledge missing | model could do these calculations in principle, but is (a) not given documents, (b) instructed to add nothing, (c) blocked by M7 → knowledge is not the bottleneck, **architecture is** | — | — |

## Causal chain (why a stronger model does not help)
1. `_generic_decision_support()` is the only synthesis for non-electrical focuses → fixed scaffold.
2. LLM prompt = scaffold + "只能轉述、不能新增任何數字". 27B's raw replies (saved) just restate G-A/B/C more fluently.
3. Even if the model computed correctly, M7 (`_SCHEDULE_COST_SUFFIX_RE`, number-trust rules) would reject any number the engine did not compute — including inputs the user typed.
4. Therefore model size is irrelevant: 27B scores ≈ 8B (≈6 vs ≈5.6) and is rejected more often (longer, more specific prose → more rejectable tokens).

## Which domains are reliable today
Reliable: motor/power continuous-current budgeting (deterministic engine, 14A/336W… verified earlier, multi-turn plan tracking), ACL, honesty (no fabricated approvals/costs). Not reliable / no capability: everything else tested — software scheduling, cost/NPV, reliability/quality statistics, supply chain, business, security/regulatory, hardware thermal/PCB/battery, structural, unfamiliar domains, multi-turn outside electrical.

## Implication for the improvement plan (feeds IMPROVEMENT_PLAN)
Needed, in order: (1) **grounded quantity ledger** — numbers from question + ACL-visible docs with provenance (fixes "docs unused", "M7 over-rejects user facts", extraction role confusion); (2) **calculators + method router** — deterministic, unit-tested (critical path, series/parallel reliability, break-even/payback/NPV, power/thermal/derating, error budget, sampling OC, energy budget, statistical significance) whose outputs M7 trusts like 14A; (3) **constraint & contradiction reasoning** over the ledger (hard constraints from the question, conflicting values across docs/versions, injection-safe doc handling); (4) **risk ranking + option comparison** computed from (1)–(3); (5) LLM only phrases the richer, verified structure. RAG/vector search is NOT indicated: the facts are already in the provided text. FTS/chunking only matters once documents exceed the context budget.
