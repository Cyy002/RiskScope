# appFIXED_l (Claude A, 2026-11-09)

Snapshot taken immediately before this round's real-model smoke-check.
Diverges from `appFIXED_k3_frozen` by exactly one file, `chat.py`, with two
targeted fixes -- confirmed via SHA256 diff (all other files byte-identical).

## Fix 1: `_NEGATION_LOOKBACK_RE` gains `若`
Real K3 BB06 8B finding: `"可行（若無風險）"` (feasible, IF no risk) was
misread as an unhedged safety claim because `若` (if/conditional) was not in
the 6-char hedge lookback. Added `若` to the shared negation-lookback regex.
Verified no regression to the approval-claim check (a *conditional approval*
claim, e.g. `"若條件成立，本案已核准通過"`, must still be hard-rejected --
confirmed it still is, since in that phrasing `若` sits outside the 6-char
window before the actual claim phrase).

## Fix 2: `_SAFE_CLAIM_RE` soft-flags instead of hard-rejects on the generic path
Real K3 BB16 27B finding (claude-b flagged as a design question, not an
obvious bug): the model wrote `"硬性限制均符合規範"` after explicitly
comparing each grounded number against its stated limit in the reply body --
a REASONED conclusion from shown work, not a bare assertion. Unlike
motor_upgrade (a real deterministic engine exists to contradict), the
generic free-form path has no compliance engine of any kind for ANY focus to
contradict -- the same reasoning that already governs the 3 numeric-citation
checks (electrical/percentage/schedule-cost) when `check is None`. Extended
the identical soft-flag-not-reject treatment to `_SAFE_CLAIM_RE` specifically.
Every other high-risk CLAIM check (approval / verification / availability /
ranking / nameplate-change) remains an UNCONDITIONAL hard rejection on every
focus, generic included -- untouched by this fix.

## Investigated and NOT fixed (confirmed genuine model-capability limits, not app bugs)
- **BB14 (8B, r1 and r3)**: `m7_verdict.accepted == True` in both real K3 runs
  (M7 did not reject it) -- the low score (51/30) is because the 8B model
  itself miscalculated the SLO error budget (`14.4` or `432` instead of the
  correct `43.2` minutes). This is a real arithmetic error by the model, not
  a safety-layer or app defect. Per the 2026-11-09 directive to stop chasing
  model scores, left as-is.
- **BB16 (8B)**: also `m7_verdict.accepted == True` -- the low score (18/100)
  is because the 8B model fabricated an irrelevant reflection-coefficient
  calculation and reached a conclusion contradicting its own correctly-stated
  numbers (500m<600m, 6<16 nodes). Genuine model reasoning failure, not an
  app/M7 defect. Left as-is for the same reason.
- **BB16 (27B)**: THIS one *was* a real M7 false positive (old `_SAFE_CLAIM_RE`
  hard-rejected a correct, fully-grounded reply, forcing fallback to the
  deterministic template, which the judge then scored 20/100 -- it was
  judging the fallback text, not the model's real answer). Fixed by Fix 2
  above.

## Testing
Full suite (`pytest -q tests/`): 302 passed, 0 failed, 0 regressions.
Two new regression tests added to `tests/test_reasoning_integration.py`
using the real saved K3 BB06/BB16 text as fixtures:
`test_a_risk_table_row_conditioned_on_ruo_is_not_an_unhedged_safety_claim`,
`test_a_reasoned_compliance_conclusion_on_the_generic_path_is_kept_with_a_caveat_not_hard_rejected`,
plus `test_motor_upgrade_safe_claim_check_is_unchanged_by_the_generic_softening`
as an explicit no-regression guard on the one path that must stay strict.

## Next step
Bounded, single-run (not a full 3x8B+1x27B batch) real-model smoke-check of
just BB06/BB14/BB16 on qwen3:8b and qwen3.6:27b, to get real evidence the
BB16/27B fix actually changes the live app's behavior -- not a new full
acceptance round, per the "stop chasing model scores" instruction. After
that, no further model-score tuning is planned; remaining time goes to the
Podman/assignment-2 delivery work.
