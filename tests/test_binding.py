"""app/binding.py: four verification levels, wrong-binding rejection, BB07 eager-pow root cause, critical path instead of summing."""
import json, pathlib
import pytest
from app.ledger import build_ledger
from app.binding import verify_calculation, safe_eval, critical_path

PLAN = {'id': 'D-PLAN', 'body': '任務（工期，週；前置）：A 設計 2週；B 後端 4週（A）；C 前端 3週（A）；D 整合 2週（B 與 C）；E 壓力測試 2週（D）。'}


def test_bb07_root_cause_large_right_operand_no_longer_overflows():
    assert safe_eval('Q2 * Q1', {'Q2': 100, 'Q1': 80000}) == 8_000_000        # old eager dict evaluated 100**80000 -> 'Result too large'
    assert safe_eval('a - b*c', {'a': 8e6, 'b': 70, 'c': 80000}) == 2_400_000
    with pytest.raises(ValueError): safe_eval('2 ** 500', {})
    with pytest.raises(ValueError): safe_eval('__import__("os")', {})


def test_all_inputs_bound_to_the_same_quantity_is_rejected_even_though_arithmetic_is_fine():       # the BB01 failure replayed
    L = build_ledger(['9 週內上線'], [PLAN])
    q1 = 'Q1'                                                                                       # "9 週" from the user's sentence
    r = verify_calculation({'formula': 'A + B + D + E', 'inputs': {'A': q1, 'B': q1, 'D': q1, 'E': q1}, 'unit': '週'}, L)
    assert r['levels']['arithmetic'] is True and r['status'] == 'REJECTED_BINDING' and r['value'] is None
    assert any('different variables' in i for i in r['issues'])


def test_correct_distinct_bindings_with_meanings_are_checked_but_professional_validity_stays_open():
    L = build_ledger(['9 週內上線'], [PLAN])
    qs = {q['label'][-2:]: f'Q{i}' for i, q in enumerate(L.items, 1)}
    spec = lambda ref, meaning: {'ref': ref, 'meaning': meaning, 'unit': '週'}
    r = verify_calculation({'formula': 'a + b', 'inputs': {'a': spec(qs['設計'], '設計工期'), 'b': spec(qs['後端'], '後端工期')}}, L)
    assert r['status'] == 'INPUTS_BOUND_AND_ARITHMETIC_CHECKED' and r['value'] == 6
    assert r['levels']['professional_validity'] == 'not_validated'


def test_declared_meaning_that_does_not_match_the_source_label_is_rejected():
    L = build_ledger([], [PLAN])
    q_design = next(f'Q{i}' for i, q in enumerate(L.items, 1) if q['label'].endswith('設計'))
    r = verify_calculation({'formula': 'a * 2', 'inputs': {'a': {'ref': q_design, 'meaning': '預算金額', 'unit': '週'}}}, L)
    assert r['status'] == 'REJECTED_BINDING'


def test_unit_dimension_conflict_is_rejected():
    L = build_ledger(['預算 300 萬元，工期 9 週'], [])
    qw = next(f'Q{i}' for i, q in enumerate(L.items, 1) if q['unit'] == '週')
    r = verify_calculation({'formula': 'a', 'inputs': {'a': {'ref': qw, 'unit': '元'}}}, L)
    assert r['status'] == 'REJECTED_BINDING'


def test_man_unit_is_expanded_not_used_raw():
    L = build_ledger(['年銷量 8 萬件，單價 100 元'], [])
    ids = {q['unit']: f'Q{i}' for i, q in enumerate(L.items, 1)}
    r = verify_calculation({'formula': 'q * p', 'inputs': {'q': ids['萬'], 'p': ids['元']}}, L)
    assert r['value'] == 8_000_000                                                              # 80,000 * 100, not 8 * 100


def test_literal_input_not_in_any_source_is_marked_assumed_never_checked():
    L = build_ledger(['單價 100 元'], [])
    r = verify_calculation({'formula': 'p * 0.9', 'inputs': {'p': 'Q1', 'x': 0.9}}, L)
    assert r['status'] == 'UNVERIFIED_ASSUMED_INPUT' and not r['levels']['presence']


def test_critical_path_not_sum_of_durations():
    t = [{'id': 'A', 'duration': 2}, {'id': 'B', 'duration': 4, 'after': ['A']}, {'id': 'C', 'duration': 3, 'after': ['A']},
         {'id': 'D', 'duration': 2, 'after': ['B', 'C']}, {'id': 'E', 'duration': 2, 'after': ['D']}, {'id': 'F', 'duration': 1, 'after': ['A']}]
    r = critical_path(t)
    assert r['total'] == 10 and r['critical_path'] == ['A', 'B', 'D', 'E'] and r['float']['C'] == 1 and r['float']['F'] == 7
    assert sum(x['duration'] for x in t) == 14                                                    # naive sum would be wrong
    with pytest.raises(ValueError): critical_path([{'id': 'A', 'duration': 1, 'after': ['B']}, {'id': 'B', 'duration': 1, 'after': ['A']}])


def test_assumed_input_with_unbound_variable_is_arithmetic_failed_not_crash():
    L = build_ledger(['單價 100 元'], [])
    r = verify_calculation({'formula': 'p * q', 'inputs': {'p': 'Q1', 'q': 'not-a-number'}}, L)
    assert r['status'] == 'ARITHMETIC_FAILED' and r['value'] is None


def test_critical_path_reports_three_separate_validity_layers_and_never_grants_conclusion_validity():
    r = critical_path([{'id': 'A', 'duration': 2}, {'id': 'B', 'duration': 3, 'after': ['A']}])
    assert r['method_validity'] == 'algorithm_checked'
    assert r['conclusion_validity'] == 'not_validated' and r['professional_validity'] == 'not_validated'
    assert 'caller_must_verify' in r['input_validity'] and r['assumptions']


# --- BB07 tracked as TWO separate issues -----------------------------------------------------------------------------------------------------------
# (U1) arithmetic overflow = evaluator evaluated unused operators (covered above); (U2) 元 / 萬元 / 萬 normalisation of INPUTS (below).
def test_u2_wan_yuan_input_normalisation_is_independent_of_the_overflow_fix():
    L = build_ledger(['預算 300 萬元，單價 100 元，銷量 8 萬件'], [])
    ids = {q['unit']: f'Q{i}' for i, q in enumerate(L.items, 1)}
    r = verify_calculation({'formula': 'budget / price', 'inputs': {'budget': {'ref': ids['萬元'], 'unit': '元'}, 'price': ids['元']}}, L)
    assert r['value'] == 30000                                   # 3,000,000 元 / 100 元, not 300 / 100
    r2 = verify_calculation({'formula': 'q', 'inputs': {'q': ids['萬']}}, L)
    assert r2['value'] == 80000


def test_u2_percent_is_kept_in_percent_points_and_not_silently_scaled():
    L = build_ledger(['緩衝 20% 的時間'], [])
    r = verify_calculation({'formula': 'p', 'inputs': {'p': 'Q1'}}, L)
    assert r['value'] == 20.0                                    # caller must divide by 100 explicitly; the tool never guesses


def test_chained_calculation_uses_only_verified_prior_results():
    L = build_ledger(['電壓差 7V，電流 1.5A，熱阻 25'], [])
    ids = {q['unit']: f'Q{i}' for i, q in enumerate(L.items, 1)}
    r1 = verify_calculation({'formula': 'dv * i', 'inputs': {'dv': ids['V'], 'i': ids['A']}}, L)
    assert r1['status'] == 'INPUTS_BOUND_AND_ARITHMETIC_CHECKED' and r1['value'] == 10.5
    r2 = verify_calculation({'formula': 'p * 25', 'inputs': {'p': {'from_calc': '損耗'}}}, L, results={'損耗': r1['value']})
    assert r2['value'] == 262.5 and r2['status'] == 'INPUTS_BOUND_AND_ARITHMETIC_CHECKED'
    r3 = verify_calculation({'formula': 'p * 25', 'inputs': {'p': {'from_calc': '損耗'}}}, L, results={})      # prior result missing/unverified
    assert r3['status'] == 'REJECTED_BINDING'


def test_explicit_assumption_input_is_allowed_but_never_called_verified():
    L = build_ledger(['單價 100 元'], [])
    r = verify_calculation({'formula': 'p * (1 - d)', 'inputs': {'p': 'Q1', 'd': {'assume': 0.1, 'meaning': '折扣率假設'}}}, L)
    assert r['status'] == 'UNVERIFIED_ASSUMED_INPUT' and abs(r['value'] - 90) < 1e-9 and any('explicit assumption' in i for i in r['issues'])
