# What the OLD integrated app actually sends to the model vs the direct prompt (claude-b, 2026-11-04) — evidence for the rework
Instrument: `tools/run_cases.py` now records every model call (`llm_calls`: full prompt, raw response, diagnostic). Probe: old app, qwen3:8b, BB01 + BB02, `runs/appPromptProbe_OLDapp_qwen3-8b/`. (Direct arm D/A1 = ONE call: guardrail/consultant prompt + full documents + question → free-form answer.)
## BB02 (120萬 / 45萬 payback; direct D scores 100: "回收期 = 120/45 = 2.67 年，前提錯誤")
| call | what it asks | what comes back |
|---|---|---|
| 1 (extraction, 25 s limit) | map the text onto six **electrical** fields (supply_voltage, motor current …) | `{}` — an irrelevant call for a financial question |
| 2 (structured reasoning) | "你是風險評估助理。你只能引用『已知數量』清單裡逐字列出的數字… 不能引用任何清單外的數字" + a 9-field JSON schema (refs `[qN]`, `meaning`, `unit`, schedule_analysis …). The task is *fill a form with only listed numbers*, not *analyse the question*. Documents are given only "供理解背景" after the form | `known_facts` = the inputs restated; `hard_constraints` = **the user's own claim** ("回收期不到兩年…") treated as a constraint; `unknowns` = 設備壽命; the one calculation it tried, `"(q1)/(q2)"`, uses the wrong notation → dropped (item-level filtering) |
| 3 (second stage) | "你只能轉述、不能新增任何數字、授權或結論" + the JSON | opens with "**目前仍缺少以下資訊，需要管理者或工程師補充…**" → "- 設備壽命" and the template's "本焦點沒有確定性工程規則…" |
Final: `deterministic_template` after M7 rejection; judged 35. The 2.67 never appears.
## BB01 (critical path; direct D 85–100 when correct)
Call 2 **timed out** (qwen3:8b default reply timeout = 45 s; the JSON generation needs more) → no reasoning at all → call 3 paraphrases the old scaffold ("規格定量判斷…") → 0.
## Findings (concrete, not inferred)
1. **The structured prompt replaces analysis by form-filling**: the model is forbidden to use any number it computes itself unless it formats it perfectly (`ref`/`meaning`/`unit`), so simple ratios vanish; required-calculation completion in the old app = **0.00** (direct D: 0.86).
2. **False "verified" label**: restated sentences are stored as `basis: tool:llm_reasoning_verified`; nothing was verified (sources `[]`). The label is wrong by construction.
3. **The second stage ("只能轉述") re-frames everything into "缺少資訊 / 需要補充"**; the user-visible text is dominated by it (9–10 of 12 replies).
4. **Wasted/irrelevant call 1** (electrical extractor on every question) and **time budgets sized for short calls** (45 s on 8B, 120 s on 27B) turn long structured generations into silent fallbacks.
5. The user's own premise ends up in `hard_constraints` — a semantic error of the form, which the direct prompt (which asks to check the user's premises) avoids.
## What the rework must change (matches Claude A's spec)
Generic focus: ACL docs → injection isolation → ONE free-form call with the guardrail prompt (documents in the prompt, "分析題目、必要時計算並寫出算式、核對硬限制、指出使用者前提錯誤") → return the text; no form, no paraphrase stage, no electrical extractor call for non-electrical questions, a time budget suited to long answers, and "verified" labels only where a deterministic tool really verified something.
