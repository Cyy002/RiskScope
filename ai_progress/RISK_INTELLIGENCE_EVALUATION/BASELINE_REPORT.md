# BASELINE_REPORT — current RiskScope (pre-improvement), real local models (claude-b, 2026-11-01)
Code under test = disk version of app/ at run time (= baseline_snapshot lineage; no reasoning layer yet). Runner `tools/run_cases.py --llm` (throwaway DB per case, in-process `chat_turn`, no mock, production/8000/8100 untouched). Holdouts (HA01–HA08, + any later) were NOT run or read. Rubrics are not shown to the Agent. Scoring: `tools/score_run.py` (reproducible, judge-free; see method) + manual reading of replies.

## Coverage
- qwen3:8b: all 30 dev cases (BB01–BB30; 33 turns incl. 3 multi-turn). Merged from 3 run dirs → `runs/_baseline_8b_all30/` (+ `_scores.json`). Sources: Claude A's `baseline30_qwen3-8b` (21 cases) and `realmodel_check_*` (BB02,03,06,09,13), my `claude-b_real_qwen3-8b_5cases_v2` (BB01,04,05,10).
- qwen3.6:27b: **12 high-difficulty cases** = BB01,04,05,10,13 (`runs/claude-b_real_qwen3.6-27b_5cases_v2`) + BB02,06,07,11,14,16,23 (`runs/baseline12_qwen3.6-27b`), each with `_scores.json`.
- Every turn records: input, full reply, structured facts/risks/options, model, elapsed, llm_diagnostic, reply_source, **raw model reply + M7 verdict**, llm_state ∈ {ACCEPTED, M7-REJECTED, NOT-CALLED/FAILED}.

## Headline (strict)
| Set | cases | LLM turn states | template-only replies | mean score /100 | max | derived answers produced |
|---|---|---|---|---|---|---|
| qwen3:8b, 30 dev cases | 30 | 26 accepted / 7 M7-rejected | **30/30** | **5.6** | 11 | **0 / 28** required numbers |
| qwen3.6:27b, 12 cases | 12 | 2 accepted / 11 M7-rejected (13 turns) | **12/12** | **≈ 6.5** | 9 | **0 / 11** |
Critical failures by deterministic rule (forbidden phrase/approval/fabrication): 0. Judgemental Critical failure noted manually: BB04 (wrong-field "已記錄" record; both models). No fabricated approval/cost/schedule appeared — the template says nothing.
Target ≥85 → the current system is ~80 points short. **It is not a "weak decision engine"; outside electrical-current budgets there is effectively none** (fixed G-A/G-B/G-C "unverified" scaffold for every domain).

## Method notes / honesty
- Score = facts(≤5 for a template, from echo of known numbers) + reasoning(derived required numbers actually present; inputs merely echoed from the user text do NOT count — fixed after BB16 false positive) + priority 0 + options 0 (fixed unverified options) + constraints (0 if hard constraints exist and none engaged) + uncertainty 3 (generic admission) + traceability ≤1. Non-template replies would be flagged `manual_review` (none occurred) — they would need a semantic judge; that judge does not exist yet and must be independent of the Agent (human or separate model).
- The mechanical rubric is deliberately harsh on templates; a manual read agrees (earlier hand scores 8–15 vs 4–11 here). Ranking among templates is therefore noise: **the information is "all ≈ floor", not "BB04 is better than BB17".**
- Run-to-run variance exists (8B BB01: accepted once, rejected once) — outcome classes, not exact states, are the evidence.

## Per-case table (8B; A=ACCEPTED, R=M7-REJECTED per turn)
| id | domain | turns | derived answer found | score |
|---|---|---|---|---|
| BB01 | 軟體工程/專案管理 | R | 0/1 | 4.0 |
| BB02 | 成本與預算 | A | 0/1 | 6.0 |
| BB03 | 品質可靠度 | A | 0/1 | 6.0 |
| BB04 | 硬體研發 | R | 0/2 | 11.0 |
| BB05 | 供應鏈 | R | 0/0 | 6.0 |
| BB06 | 專案管理/多輪 | AA | 0/1 | 6.0 |
| BB07 | 商業決策 | R | 0/2 | 6.0 |
| BB08 | 陌生領域(醫藥冷鏈) | A | 0/0 | 6.0 |
| BB09 | 軟體工程/資料庫 | A | 0/0 | 6.0 |
| BB10 | 採購/安全 | R | 0/1 | 6.0 |
| BB11 | 系統整合 | A | 0/0 | 4.0 |
| BB12 | 品質可靠度 | A | 0/2 | 6.0 |
| BB13 | 跨領域(法規+硬體+時程) | A | 0/1 | 6.0 |
| BB14 | 軟體工程/可靠度 | A | 0/2 | 6.0 |
| BB15 | 硬體研發 | A | 0/3 | 6.0 |
| BB16 | 系統整合 | A | 0/0 | 9 |
| BB17 | 軟體工程／成本 | A | 0/1 | 4.0 |
| BB18 | 供應鏈 | A | 0/0 | 4.0 |
| BB19 | 專案管理 | A | 0/1 | 4.0 |
| BB20 | 成本與預算 | R | 0/1 | 4.0 |
| BB21 | 品質可靠度 | A | 0/3 | 4.0 |
| BB22 | 商業決策 | A | 0/2 | 6.0 |
| BB23 | 跨領域風險（資安＋法規） | A | 0/0 | 4.0 |
| BB24 | 陌生領域（結構工程） | A | 0/0 | 4.0 |
| BB25 | 硬體研發（PCB設計） | A | 0/0 | 4.0 |
| BB26 | 軟體工程／多輪容量規劃 | AA | 0/2 | 6.0 |
| BB27 | 供應鏈（矛盾文件） | A | 0/0 | 6.0 |
| BB28 | 專案管理（時程緩衝） | R | 0/0 | 6.0 |
| BB29 | 商業決策（併購／供應商整合） | A | 0/1 | 6.0 |
| BB30 | 品質可靠度（多輪／統計顯著性） | AA | 0/0 | 6.0 |
