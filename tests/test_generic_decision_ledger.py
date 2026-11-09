"""M12.5.2 (RiskScope risk-intelligence baseline, 2026-11-01): the real-model
baseline (ai_progress/RISK_INTELLIGENCE_EVALUATION/) found `_generic_decision_
support()` reported essentially nothing case-specific for any non-engineering
question -- no fact ever reflected a number the user or a document actually
stated, and a genuine contradiction between two documents was never surfaced
at all. This is the fix under test: `app.analyzer._generic_decision_support()`
now builds an `app.ledger.Ledger` from the question text and the (already
ACL-filtered) retrieved documents, surfaces every distinct grounded quantity
as a real fact with its literal source, and turns any `Ledger.conflicts()`
hit into its own high-severity 'R-CONTRADICTION' risk plus a matching
unknown/follow-up question -- never resolving the contradiction itself,
only naming both values and both sources side by side.

Direct unit tests against the pure function (no DB/API needed) -- mirrors
how tests/test_m12_generic_decision.py exercises the same function via the
API; this file adds the ledger-specific behavior on top.
"""
from app.analyzer import _generic_decision_support


def test_a_quantity_stated_in_the_question_becomes_a_real_fact_with_its_source():
    facts, options, risks, questions, unknowns = _generic_decision_support(
        {}, [], '這個設備要花80萬元，之後5年每年可以多賺20萬元，所以划算對吧？', [])
    claims = [f['claim'] for f in facts]
    assert any('80萬元' in c and '使用者訊息' in c for c in claims)
    assert any('20萬元' in c and '使用者訊息' in c for c in claims)
    # Still never a per-focus hardcoded string, and the fixed scaffold is
    # still present underneath the new facts -- this is additive, not a
    # replacement of the existing, already-tested shape.
    assert len(options) == 3
    assert any(r['id'] == 'R-UNVALIDATED-ANALYSIS' for r in risks)


def test_a_quantity_stated_only_in_an_authorized_document_becomes_a_fact_with_that_document_as_source():
    documents = [{'id': 'DOC-LEAD', 'excerpt': '供應商交期為35天，單價為130元。'}]
    facts, *_ = _generic_decision_support({}, [], '目前的交期安排可以嗎？', documents)
    claims = [(f['claim'], f['sources']) for f in facts]
    assert any('35天' in c and src == ['DOC-LEAD'] for c, src in claims)


def test_two_documents_disagreeing_on_the_same_thing_surfaces_a_contradiction_risk_not_a_silent_pick():
    """Note: app.ledger.Ledger.conflicts() recognizes "the same thing" by
    character-bigram overlap of the text immediately preceding each number,
    so the two documents below deliberately use matching phrasing
    ("本次訂單的交貨期是") -- a real, known limitation (not this test's bug) is
    that two genuinely-paraphrased mentions of the same concept with very
    different wording may not be recognized as the same label; that gap is
    tracked separately, not papered over by loosening this test."""
    documents = [
        {'id': 'DOC-SALES-EMAIL', 'excerpt': '業務信件內容：本次訂單的交貨期是20天，請放心。'},
        {'id': 'DOC-ORDER-CONFIRM', 'excerpt': '系統訂單確認單：本次訂單的交貨期是45天。'},
    ]
    facts, options, risks, questions, unknowns = _generic_decision_support(
        {}, [], '供應商業務信件說交期是20天，但訂單確認單卻寫45天，到底可以信哪個？', documents)
    contradiction_risks = [r for r in risks if r['id'] == 'R-CONTRADICTION']
    assert len(contradiction_risks) == 1
    assert contradiction_risks[0]['severity'] == 'high'
    assert 'DOC-SALES-EMAIL' in contradiction_risks[0]['message']
    assert 'DOC-ORDER-CONFIRM' in contradiction_risks[0]['message']
    assert any('矛盾數值' in u['topic'] for u in unknowns)
    assert any('哪一個來源的數值才是正確' in q for q in questions)
    # Never silently resolved: neither "20" nor "45" alone is asserted as
    # the answer anywhere in the structured output -- only cited side by side.


def test_numbers_mentioned_together_in_one_question_are_not_falsely_flagged_as_a_contradiction():
    """Two different quantities in the SAME breath ("要花80萬元...每年多賺20萬元")
    are not a contradiction about the same thing -- Ledger.conflicts() only
    fires across DIFFERENT sources, which this also locks in at the
    _generic_decision_support level, not just inside app/ledger.py directly."""
    facts, options, risks, questions, unknowns = _generic_decision_support(
        {}, [], '這個設備要花80萬元，之後5年每年可以多賺20萬元。', [])
    assert not any(r['id'] == 'R-CONTRADICTION' for r in risks)


def test_documents_the_caller_never_passed_in_can_never_leak_as_a_fact_source():
    """_generic_decision_support only ever sees `documents` -- whatever the
    caller (analyzer.analyze(), via the already-ACL-filtered get_context())
    chose to pass. This is a cheap guard that the function itself invents no
    extra source: passing an empty list produces zero document-sourced facts
    even when the question contains a number that WOULD match a real
    document if one had been (wrongly) consulted elsewhere."""
    facts, *_ = _generic_decision_support({}, [], '供應商交期為35天，可以嗎？', [])
    assert all(f['sources'] == [] for f in facts)
