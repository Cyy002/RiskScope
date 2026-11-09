"""claude-b independent verification of Claude A's M7 grounding fix (chat._grounded_in_context), now fixed by Claude A: a bare SUBSTRING
test used to let fabricated figures through whenever they were a substring of a real one ("30天" inside "130 天", "200萬元" inside
"1,200 萬元") and wrongly rejected a user figure written with a thousands separator ("1,200 萬元" quoted back as "1200萬元"). Fix: for any
unit app/ledger.py recognizes, grounding now goes through `Ledger.grounds()` (exact canonical-value match, handles the comma separator
and unit conversion) instead of a substring test; the substring fallback used for units ledger does not know is now boundary-aware
(`_boundary_aware_contains`), so it can no longer match a number embedded inside a longer one either. All three cases below have been
verified to flip from XFAIL to passing and the strict-xfail markers have been removed per this file's own original contract."""
from app import chat

MSG = '供應商目前交期是 130 天，預算 1,200 萬元。'
RESULT = {'documents': [], 'checks': [], 'facts': []}


def verdict(reply):
    return chat._reply_is_trustworthy(reply, RESULT, None, None, None, MSG)[0]


def test_real_user_figures_are_accepted():
    assert verdict('目前交期 130 天。')


def test_fabricated_figure_embedded_in_real_figure_is_rejected_days():
    assert not verdict('交期大約只要 30 天。')


def test_fabricated_figure_embedded_in_real_figure_is_rejected_money():
    assert not verdict('預算約 200 萬元。')


def test_thousands_separator_figure_is_recognised_as_the_users_own():
    assert verdict('預算 1200 萬元。')
