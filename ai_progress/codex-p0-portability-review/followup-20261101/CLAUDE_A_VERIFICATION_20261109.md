# Independent verification (Claude A, 2026-11-09)

Ran `test_deploy_guards.py` directly: **2 passed, 5 failed** (matches the pre-recorded
`guard_results.log` exactly). Confirmed this is NOT a live regression:

The 5 "failed" tests (`SNAPSHOT` env default = this directory's own frozen `snapshot/`
subtree, overridable via `P0_REVIEW_DEPLOY_SOURCE`) intentionally exercise Codex's
point-in-time **pre-fix** copy of `deploy/riskscope.sh` / `scripts/portable_smoke.py` as
historical evidence of the vulnerabilities found. Diffed the frozen snapshot against the
current live files and confirmed all 5 are already fixed in the live code:

1. **host-network port escape** — live script has no `--network=host` path at all; any
   `RS_HOST_NETWORK` value is a hard `die`.
2. **production image tag overwrite** — live script's `IMAGE` is regex-validated to
   `^localhost/riskscope-portable:...`, rejecting the production `riskscope-poc:*` tag.
3. **plaintext credentials surviving a failed restart** — live `restart-test` checks
   `rc1`/`rc2` explicitly and fails loudly rather than silently continuing.
4. **purge of an unowned workload** — live `purge`/`down`/`up` all call `require_owned`
   first (checks the `io.riskscope.portable=1` label); the frozen snapshot's `purge` had
   no ownership check at all.
5. **smoke script reporting a false overall PASS when no real LLM ran** — live
   `scripts/portable_smoke.py` has a separate `deterministic_pass`/`real_llm_pass` split
   and prints `RESULT: DETERMINISTIC-ONLY (NOT a real-Agent PASS; no LLM verified)`
   (exit 2) rather than ever conflating a deterministic-only run with a verified pass.

No action taken on this directory's frozen snapshot — it is correctly preserved as
before/after evidence, not live code, and should not be "fixed" to pass.

Separately, running the live `deploy/riskscope.sh smoke` for real (on the independent
test VM `riskscope-codex-apple-20261107`) while this session's unrelated background
model-evaluation batch was mid-run produced one `FAIL` on the 14A-total-current check
(`extract` call timed out at 25s, '逾時（25s）：模型可能仍在載入或正在生成' — the 3A aux
current was never captured, so the deterministic engine only saw the 11A motor current).
The live smoke script's own diagnostic output matches exactly what (5) above checks for
(`deterministic_pass=False real_llm_pass=True`, correctly reported as FAIL, not silently
upgraded to PASS) — so the *reporting* behaved correctly; the *timeout itself* is most
likely Ollama resource contention from the concurrent batch, not a confirmed app defect.
Re-run pending with the Ollama queue idle before this is written up as a real finding one
way or the other.
