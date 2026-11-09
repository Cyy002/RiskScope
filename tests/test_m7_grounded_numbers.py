"""M7 fix (RiskScope risk-intelligence baseline, 2026-11-01): a generic-focus
question has no deterministic engine computation at all (analyzer.py's
_generic_decision_support never calls power_continuous()), so M7's schedule/
cost/percentage checks previously rejected EVERY such number a reply could
possibly state -- including a number the user had just typed themselves,
word for word, in their own question. The real baseline run reproduced this
across multiple unrelated domains (ai_progress/RISK_INTELLIGENCE_EVALUATION/
BASELINE_8B_REPORT_claudeA.md): a reply quoting "...這個設備要花80萬元..." back
from the user's own message was rejected as "沒有可信來源，可能是虛構內容".

Fix: `_grounded_in_context()` trusts a bare numeric/percentage/schedule/cost
figure ALSO when it is a literal substring of the user's current message or
of an (already ACL-filtered) document in `result['documents']` -- never an
LLM self-report, and the approval/safety/ranking/nameplate-change CLAIM
checks earlier in `_reply_is_trustworthy` are completely untouched by this.
These tests must prove both directions: a genuinely user/document-grounded
number is no longer wrongly rejected, AND a number that is neither computed
nor grounded anywhere is still correctly rejected -- the fix must not become
a blanket "trust anything" rule.
"""
from app import chat


def _result(facts=None, documents=None, checks=None):
    return {'facts': facts or [], 'documents': documents or [], 'checks': checks or []}


def test_cost_figure_quoted_from_the_users_own_message_is_no_longer_rejected():
    message = '這個設備要花80萬元，之後5年每年可以多賺20萬元，總共賺100萬元，比投入的80萬多，所以這個投資划算，對吧？'
    text = '本輪問題：「這個設備要花80萬元，之後5年每年可以多賺20萬元」目前未提供其他可驗證資料。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, message)
    assert trustworthy, reason


def test_cost_figure_with_no_computed_source_and_not_in_message_or_documents_still_rejected():
    message = '這個設備要花80萬元，之後5年每年可以多賺20萬元，所以划算對吧？'
    text = '依評估，這筆投資其實要花350萬元才夠。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, message)
    assert not trustworthy
    assert '350' in reason


def test_percentage_quoted_from_the_users_own_message_is_no_longer_rejected():
    message = '每個任務負責人都在自己的任務時程上多估了20%當緩衝，這樣應該很保險吧？'
    text = '每個任務的20%緩衝是各自獨立的，不代表整體專案有等量的總緩衝保護。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, message)
    assert trustworthy, reason


def test_percentage_with_no_computed_source_and_not_grounded_anywhere_still_rejected():
    message = '每個任務負責人都在自己的任務時程上多估了20%當緩衝，這樣應該很保險吧？'
    text = '依經驗，這種串聯緩衝大約有65%的機率會被用掉。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, message)
    assert not trustworthy
    assert '65' in reason


def test_figure_grounded_in_an_authorized_document_rather_than_the_message_is_trusted():
    documents = [{'id': 'DOC-X', 'excerpt': '供應商交期為35天，單價為130元。'}]
    text = '依文件，供應商交期為35天。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(documents=documents), None, None, None, '目前的交期安排可以嗎？')
    assert trustworthy, reason


def test_figure_absent_from_message_and_from_every_authorized_document_still_rejected():
    documents = [{'id': 'DOC-X', 'excerpt': '供應商交期為35天，單價為130元。'}]
    text = '依文件，供應商交期為99天。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(documents=documents), None, None, None, '目前的交期安排可以嗎？')
    assert not trustworthy
    assert '99' in reason


# --- RiskScope selection-phase app-E2E findings (claude-b, 2026-11-04) -----
# Same family of bug as above, for the V/A/W-unit check: without a
# deterministic engineering `check` (i.e. any focus other than
# motor_upgrade), _trusted_numbers_by_dimension(None, ...) is ALL EMPTY sets,
# so a reply faithfully quoting a real voltage from the user's own message or
# an authorized document was always rejected as "與確定性計算結果不一致" --
# nothing was ever computed to be inconsistent WITH. Fixed by falling back to
# the same literal grounding other dimensions already use when check is None.

def test_voltage_quoted_from_a_document_with_no_engineering_check_is_no_longer_rejected():
    documents = [{'id': 'D-IF', 'excerpt': 'MCU GPIO：3.3V 邏輯，輸入最大額定 3.6V，非 5V 耐受。感測器輸出高準位 5V。'}]
    text = '感測器輸出 5V，但 MCU 額定只有 3.6V，直接接會超出額定。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(documents=documents), None, None, None,
                                                       '感測器輸出 5V 邏輯準位，要接到 MCU 的 GPIO，可以直接接嗎？')
    assert trustworthy, reason


def test_voltage_with_no_engineering_check_and_not_grounded_anywhere_is_still_rejected():
    text = '電源電壓其實是 42V。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, '可以直接接嗎？')
    assert not trustworthy
    assert '42' in reason


def test_motor_upgrade_engine_consistency_check_is_unchanged_when_check_exists():
    """The one domain with a real deterministic engine keeps the STRICT
    engine-only comparison -- no grounding fallback -- exactly as before."""
    check = {'status': 'pass', 'numbers': {'supply_voltage_v': '24'}}
    text = '電源電壓是 30V。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(checks=[check]), None, None, None, '電源電壓是 24V 嗎？')
    assert not trustworthy
    assert '30' in reason and '確定性計算' in reason


# --- RiskScope selection-phase app-E2E finding (claude-b, 2026-11-04) ------
# A real 27B reply wrote "請勿直接視為已核准的結論" (please do NOT treat this as
# approved) -- "勿" (a formal prohibition particle) was missing from
# _NEGATION_LOOKBACK_RE, so the hedge was not recognized and the whole reply
# was wrongly rejected as an unhedged approval claim.

def test_formal_prohibition_particle_vu_correctly_negates_an_approval_claim():
    text = '請勿直接視為已核准的結論，仍須經人工審核後方可執行。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, '這個方案可以核准嗎？')
    assert trustworthy, reason


def test_colloquial_prohibition_particle_bie_correctly_negates_an_approval_claim():
    text = '別把這個當成已核准的結論。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, '這個方案可以核准嗎？')
    assert trustworthy, reason


def test_an_actual_unhedged_approval_claim_is_still_rejected():
    text = '本次採購已核准。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, '這筆採購可以核准嗎？')
    assert not trustworthy
    assert '核准' in reason


# --- Overnight fix (2026-11-07), real Batch I finding --------------------
# BB10's 8B reply correctly REFUSED approval of the main question, but its
# own "未知" section asked "是否有其他未列的預算用途或已核准的採購項目" (is
# there some OTHER, unrelated, already-approved item?) -- a question about a
# different thing, not a claim that THIS purchase is approved. The 6-char
# negation lookback can't reach "是否" (well outside the window), so this
# correct, injection-resistant answer was wrongly discarded.

def test_an_interrogative_mention_of_an_unrelated_approved_item_is_not_an_approval_claim():
    text = '結論：無法核准這筆採購，因預算餘額不足。\n未知：是否有其他未列的預算用途或已核准的採購項目？'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, '這筆採購可以核准嗎？')
    assert trustworthy, reason


def test_interrogative_framing_does_not_suppress_a_real_affirmation_later_in_the_reply():
    """The clause-scoping must not be so wide that an unrelated question
    earlier in a long reply hides a genuine, separate affirmation later on."""
    text = '是否有其他未列的採購項目，目前不清楚。另外，本次採購已核准，可以直接執行。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, '這筆採購可以核准嗎？')
    assert not trustworthy
    assert '核准' in reason


def test_grounding_fix_never_touches_the_approval_safety_ranking_checks():
    """Regression guard: the new grounding path only ever applies to bare
    numeric/percentage/schedule/cost figures -- a fabricated APPROVAL claim
    must still be rejected even if the literal word "已核准" happens to
    appear in the user's own message (e.g. asking about an approval that
    does not actually exist for this conversation)."""
    message = '請問 TEST-01 已核准了嗎？'
    text = 'TEST-01 已核准，可以立即執行。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, message)
    assert not trustworthy
    assert '核准' in reason


def test_unit_conversion_grounding_via_ledger_9_weeks_grounds_63_days():
    """app/ledger.py (claude-b): unit-conversion-aware grounding, not just a
    literal character match -- a reply saying "63天" must be recognized as
    grounded when the user's own message said "9週" (9*7=63), the same way
    `_same_requested_value()` already treats 8A and 8000mA as the same
    engineering quantity."""
    message = '這個專案團隊說需要9週才能完成，客戶要求的交期是8週，來得及嗎？'
    text = '團隊估計約63天才能完成，而客戶要求的交期是56天，恐怕來不及。'
    trustworthy, reason = chat._reply_is_trustworthy(text, _result(), None, None, None, message)
    assert trustworthy, reason
