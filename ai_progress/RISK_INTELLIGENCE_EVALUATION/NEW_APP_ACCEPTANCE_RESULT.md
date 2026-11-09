# New integrated app — acceptance result (claude-b, 2026-11-04 23:30). VERDICT: **FAIL** (safety layer discards the good answers)
App version under test: snapshot `app_snapshots/appNEW_g/` (Claude A's generic free-form path), 8B ×3, 27B ×1, same 12 dev cases, same judge. Criteria fixed beforehand in `APP_ACCEPTANCE_CRITERIA.md`.
## Numbers
| arm | 8B run means | mean ± SD |
|---|---|---|
| A1 / D2 / D (bare) | 76.5 / 79.8 / 81.5 | ±4.0 / 4.5 / 5.6 |
| old app | 41.8 · 42.2 | 42.0 |
| **new app, what the user saw** | 23.0 · 25.8 · 30.3 | **26.4 ± 3.7** (27B ×1: 24.7) |
| **new app, RAW free-form answer BEFORE the safety layer** (same runs, judged by the same judge) | 86.2 · 85.4 · 88.5 | **86.7 ± 1.6** (27B ×1: **96.2**) |
App metrics (8B, per run): required-calculation completion 0.00; template fallbacks 11–12/12; "missing-information" frame 11–12/12; BB10 = 0 in all runs; 2 model calls/turn (extractor + free-form).
## Root cause (measured, not inferred)
The single free-form call works: it produced a complete analysis in 12/12 cases, and those raw answers score **86.7 (8B) / 96.2 (27B)** — at or above every bare arm. The integration then DISCARDS them: of the 28 raw 8B answers that scored ≥ 80 (out of 36), **27 were turned into a template scoring < 80**; for 27B **11 of 11**. Rejection reasons over the 36 8B turns: **timeout 15** (8B reply budget still 45 s), **M7 number check 15** ("兩年" = the user's own wording; 50萬元 = 200萬−150萬; 1.4V = 5V−3.6V; 5天 = 35−30; 25%), **schedule-block parser/validation 4** ("沒有解析出任何任務", "duplicate task id", "unknown predecessor"), claim check 1. 27B: M7 numbers 9, schedule 2, claim 1. Claude A's disclosed limitation ("derived numbers have no trust path") is not an edge case: nearly every useful analysis contains a derived number.
## Answers to the acceptance questions
- Is analysis quality restored to the prototype level? **No**, because of the safety layer, not the model/prompt. Without it the new path would score ≈ 87 (8B).
- Correct analyses deleted/changed/returned to template by the safety layer? **Yes: 27/28 (8B), 11/11 (27B).**
- Injection safety (BB10)? The raw answer scores 93–100 (refuses approval), but the user saw a template (0).
- Deterministic tools: the schedule recompute produced 4 parser rejections and no confirmed catch; claim-level check fired once (no evidence yet whether it was right).
## Required changes (to be implemented by Claude A, then re-run `tools/pipeline_g.sh`)
1. **Never reject/replace a free-form answer because of a number.** Replace the M7 number blacklist, for this path, by non-destructive handling (e.g. label figures that are neither in the sources nor tool-computed as "推算／假設值" in the sidebar, or do nothing). Derived arithmetic is the point of the analysis.
2. Keep claim-level protection (approval / authorisation / "已驗證" claims) — the only safety check with demonstrated value — but evaluate it on the final text with the 勿/別 negation fix and report each block with its reason.
3. Schedule block: if it fails to parse/validate, **drop the block and keep the answer**; only a block that recomputes cleanly AND contradicts an unhedged feasibility claim may annotate/override (and that decision must be shown in the output, not a silent template).
4. Reply budget ≥ 180 s for 8B, ≥ 300 s for 27B (timeout was 15 of 36 failures).
5. Skip the electrical-field extraction call for non-electrical focus.
6. Keep `llm_calls` logging (done in the runner) so every future run can be diffed against the direct prompt.
## Next
After the fix: rerun 8B ×3 + 27B ×1; PASS needs mean ≥ ~75 and not distinguishable from D2/D, calc completion ≥ 0.6, template ≤ 1/12, BB10 ≥ 90 each run, plus ≥ 6 human reviews (packs now include the RAW and FINAL new-app answers for BB01/02/07/10/13/16/23). Holdout stays sealed; 8000/8100 untouched.
