"""app/reasoning.py: the LLM-led structured reasoning path (architecture
pivot authorized 2026-11-01) and its deterministic grounding/verification --
all pure functions, no Ollama, no DB. These tests exercise the SAFETY
properties that make it acceptable to let an LLM draft facts/risks/options
at all: every number must be grounded or independently re-derived, never
trusted on the LLM's say-so, and the whole structure is rejected wholesale
on the first violation.

Calculation/schedule verification itself is NOT reimplemented here -- it
delegates to app/binding.py (claude-b), which has its own dedicated test
suite (tests/test_binding.py) for safe_eval, the four verification levels,
and critical_path(). These tests only check that app/reasoning.py wires
into that module correctly (accepts a good calc, rejects BB01-style
binding failures end to end) and keeps its OWN responsibilities (structural
validation, free-text number grounding, severity/feasibility enum checks,
risk ranking) correct.
"""
from decimal import Decimal
from app import reasoning
from app.ledger import build_ledger


def _ledger_for(question, documents=None):
    return build_ledger([question], documents or [])


def ref(r, meaning):
    return {'ref': r, 'meaning': meaning}


# --- verify_derived_calculations (delegates to app/binding.py) ------------

def test_derived_calculation_with_correctly_bound_inputs_passes():
    L = _ledger_for('馬達11A、輔助3A，合計多少？')
    results, dropped = reasoning.verify_derived_calculations(
        [{'name': '總電流', 'formula': 'a + b', 'inputs': {'a': ref('q1', '馬達電流'), 'b': ref('q2', '輔助')}}], L)
    assert not dropped, dropped
    assert results['總電流'] == Decimal('14')


def test_bb01_pattern_reusing_one_quantity_for_several_different_tasks_is_rejected():
    """The exact real-model failure this module exists to close: four
    distinct tasks (q1-q4) but the draft reuses q1 for all four `meaning`
    claims instead of citing q2/q3/q4 -- arithmetic over q1 four times
    would be "correct" (9*4=36) but the BINDING is wrong, and
    app/binding.py's L2 check rejects it before arithmetic even runs."""
    L = _ledger_for('任務A工期9週，任務B工期3週，任務C工期5週，任務D工期2週，依序執行需要多久？')
    results, dropped = reasoning.verify_derived_calculations(
        [{'name': '總工期', 'formula': 'a + b + c + d',
          'inputs': {'a': ref('q1', '任務A工期'), 'b': ref('q1', '任務B工期'),
                     'c': ref('q1', '任務C工期'), 'd': ref('q1', '任務D工期')}}], L)
    assert not results
    assert dropped[0]['name'] == '總工期' and dropped[0]['status'] == 'REJECTED_BINDING'


def test_derived_calculation_with_an_ungrounded_assumed_input_is_rejected():
    """app/binding.py itself only marks this UNVERIFIED_ASSUMED_INPUT rather
    than hard-rejecting (so a caller COULD choose to show it clearly
    labeled) -- app/reasoning.py's own policy is stricter: the whole
    reasoning draft is rejected wholesale, never partially trusted, matching
    '不得給出已驗證標記' applied to the entire structure."""
    L = _ledger_for('馬達11A。')
    results, dropped = reasoning.verify_derived_calculations(
        [{'name': '總電流', 'formula': 'a + b', 'inputs': {'a': ref('q1', '馬達電流'), 'b': 999}}], L)
    assert not results
    assert dropped[0]['status'] == 'UNVERIFIED_ASSUMED_INPUT'


def test_naive_sum_of_several_task_durations_via_derived_calculations_is_rejected():
    """Confirmed real-model failure (2026-11-04, found investigating why the
    app-integration selection-phase run scored far below the bare-prompt Arm D
    prototype on the same question): the model cited "總工期計算為14週" (the
    naive sum of every task's duration, 2+4+3+2+2+1) as a tool-verified fact
    instead of the correct dependency-aware critical path (10週). Each
    individual duration IS correctly bound -- binding.py's L1-L3 checks all
    pass -- so a plain sum like this must be caught here as a POLICY matter:
    any derived_calculations entry that purely adds >=2 distinct
    time-dimensioned inputs is exactly the schedule_analysis/critical_path
    case, not a trustworthy schedule total."""
    L = _ledger_for('任務A工期2週，任務B工期4週，任務C工期3週，任務D工期2週，任務E工期2週，任務F工期1週。')
    results, dropped = reasoning.verify_derived_calculations(
        [{'name': '總工期', 'formula': 'a + b + c + d + e + f',
          'inputs': {'a': ref('q1', '任務A工期'), 'b': ref('q2', '任務B工期'), 'c': ref('q3', '任務C工期'),
                     'd': ref('q4', '任務D工期'), 'e': ref('q5', '任務E工期'), 'f': ref('q6', '任務F工期')}}], L)
    assert not results
    assert dropped[0]['status'] == 'SCHEDULE_SUM_MUST_USE_SCHEDULE_ANALYSIS'


def test_a_two_term_subtraction_between_durations_is_not_treated_as_a_schedule_sum():
    """The new rule only targets a PURE ADDITIVE chain -- a legitimate
    comparison like "35天-30天" (BB23's real shape: deadline gap, not a
    multi-task schedule total) must still pass."""
    L = _ledger_for('完整測試需35天，法規期限30天。')
    results, dropped = reasoning.verify_derived_calculations(
        [{'name': '超期天數', 'formula': 'a - b', 'inputs': {'a': ref('q1', '完整測試天數'), 'b': ref('q2', '法規期限')}}], L)
    assert not dropped, dropped
    assert results['超期天數'] == Decimal('5')


def test_derived_calculation_with_unit_dimension_conflict_is_rejected():
    L = _ledger_for('工期9週。')
    results, dropped = reasoning.verify_derived_calculations(
        [{'name': '誤用單位', 'formula': 'a', 'inputs': {'a': {'ref': 'q1', 'unit': '元'}}}], L)
    assert not results
    assert dropped[0]['status'] == 'REJECTED_BINDING'


# --- verify_schedule_analysis (P1 item 6: 不能直接假定所有工期相加) -----------

def test_schedule_analysis_uses_critical_path_not_a_flat_sum():
    L = _ledger_for('任務A工期2週，任務B工期4週，任務C工期3週，任務D工期2週，任務E工期2週。')
    tasks = [
        {'id': 'A', 'duration': ref('q1', '任務A工期')},
        {'id': 'B', 'duration': ref('q2', '任務B工期'), 'after': ['A']},
        {'id': 'C', 'duration': ref('q3', '任務C工期'), 'after': ['A']},
        {'id': 'D', 'duration': ref('q4', '任務D工期'), 'after': ['B', 'C']},
        {'id': 'E', 'duration': ref('q5', '任務E工期'), 'after': ['D']},
    ]
    result, reasons = reasoning.verify_schedule_analysis(tasks, L)
    assert result is not None, reasons
    assert result['total'] == 10  # NOT 2+4+3+2+2=13 -- C runs in parallel with B
    assert result['critical_path'] == ['A', 'B', 'D', 'E']
    # claude-b/user review 2026-11-03: method validity != input validity != conclusion validity; the algorithm result never grants professional validity
    assert result['method_validity'] == 'algorithm_checked' and result['conclusion_validity'] == 'not_validated' and result['professional_validity'] == 'not_validated'


def test_schedule_analysis_rejects_a_tasks_duration_that_is_not_field_bound():
    """Same BB01 shape, but for schedule_analysis specifically: a task's
    duration must be a real, correctly-bound quantity, not an assumed bare
    number -- this reuses binding.verify_calculation for each task instead
    of a separate, parallel check."""
    L = _ledger_for('任務A工期2週。')
    tasks = [{'id': 'A', 'duration': ref('q1', '任務A工期')}, {'id': 'B', 'duration': 999, 'after': ['A']}]
    result, reasons = reasoning.verify_schedule_analysis(tasks, L)
    assert result is None
    assert 'B' in reasons[0]


def test_schedule_analysis_rejects_a_dependency_cycle():
    L = _ledger_for('任務A工期2週，任務B工期3週。')
    tasks = [{'id': 'A', 'duration': ref('q1', '任務A工期'), 'after': ['B']},
             {'id': 'B', 'duration': ref('q2', '任務B工期'), 'after': ['A']}]
    result, reasons = reasoning.verify_schedule_analysis(tasks, L)
    assert result is None


def test_empty_schedule_analysis_is_a_harmless_no_op():
    L = _ledger_for('沒有工期資訊。')
    result, reasons = reasoning.verify_schedule_analysis([], L)
    assert result is None and reasons == []
    result, reasons = reasoning.verify_schedule_analysis(None, L)
    assert result is None


# --- validate_reasoning (full structural + grounding check) ----------------

def _valid_struct(**overrides):
    base = {
        'known_facts': ['目前月費8萬元'], 'unknowns': [], 'hard_constraints': [],
        'derived_calculations': [], 'risk_causal_chain': [],
        'risks': [{'id': 'R-1', 'severity': 'medium', 'message': '目前月費8萬元，需留意成長趨勢'}],
        'options': [{'id': 'O-1', 'title': '維持現狀', 'feasibility': 'unverified', 'rationale': '尚待確認'}],
        'next_actions': ['取得更多資料'],
    }
    base.update(overrides)
    return base


def test_a_fully_grounded_valid_struct_passes():
    L = _ledger_for('目前每月流量成長15%，目前月費8萬元。')
    ok, cleaned, reason = reasoning.validate_reasoning(_valid_struct(), L)
    assert ok, reason
    assert cleaned is not None


def test_missing_required_key_is_rejected():
    L = _ledger_for('目前月費8萬元。')
    struct = _valid_struct()
    del struct['unknowns']
    ok, cleaned, reason = reasoning.validate_reasoning(struct, L)
    assert not ok
    assert 'unknowns' in reason


def test_an_ungrounded_fact_is_dropped_but_other_content_survives():
    """PER-ITEM degradation (2026-11-03, directly answering the user's point
    #1): real saved drafts showed a whole-draft-rejects-on-any-failure
    policy discarded 65-72% of analyses even when most content was fine.
    One ungrounded sentence must only remove ITSELF, never the rest of a
    draft that is otherwise grounded."""
    L = _ledger_for('目前月費8萬元。')
    struct = _valid_struct(known_facts=['目前月費8萬元，預估明年會漲到999萬元'])
    ok, cleaned, reason = reasoning.validate_reasoning(struct, L)
    assert ok, reason
    assert cleaned['known_facts'] == []  # the bad sentence is dropped wholesale, never edited
    assert any(d['category'] == 'known_facts' and '999萬元' in d['reason'] for d in cleaned['_dropped'])
    # _valid_struct()'s default risks/options are grounded and untouched
    assert cleaned['risks'] and cleaned['options']


def test_validate_reasoning_falls_back_to_full_rejection_when_nothing_survives_filtering():
    """The ONLY case `validate_reasoning` still returns ok=False for a
    structurally-valid draft: every known_facts/hard_constraints/risks/
    options item is ungrounded, so there is nothing left to prefer over the
    old fixed scaffold."""
    L = _ledger_for('目前月費8萬元。')
    struct = _valid_struct(
        known_facts=['明年會漲到999萬元'],
        hard_constraints=['預算上限999萬元'],
        risks=[{'id': 'R-1', 'severity': 'medium', 'message': '預估損失999萬元'}],
        options=[{'id': 'O-1', 'title': 'X', 'feasibility': 'unverified', 'rationale': '成本999萬元，尚待確認'}])
    ok, cleaned, reason = reasoning.validate_reasoning(struct, L)
    assert not ok and cleaned is None
    assert '999' in reason or '過濾後沒有任何可信內容' in reason


def test_one_bad_derived_calculation_is_dropped_while_a_good_calculation_and_facts_survive():
    """The core behavioral claim of the per-item redesign, proven end to
    end: a draft with one BB01-shaped bad binding and one genuinely correct
    calculation keeps the good calculation's result (and the rest of the
    draft), dropping only the bad one."""
    L = _ledger_for('馬達11A、輔助3A，任務A工期9週，任務B工期3週，任務C工期5週，任務D工期2週。')
    struct = _valid_struct(
        known_facts=['馬達11A，輔助3A'],
        derived_calculations=[
            {'name': '總電流', 'formula': 'a + b', 'inputs': {'a': ref('q1', '馬達電流'), 'b': ref('q2', '輔助')}},
            {'name': '總工期', 'formula': 'a + b + c + d',
             'inputs': {'a': ref('q3', '任務A工期'), 'b': ref('q3', '任務B工期'),
                        'c': ref('q3', '任務C工期'), 'd': ref('q3', '任務D工期')}},
        ])
    ok, cleaned, reason = reasoning.validate_reasoning(struct, L)
    assert ok, reason
    dropped_calcs = {d['item']: d for d in cleaned['_dropped'] if d['category'] == 'derived_calculations'}
    assert '總工期' in dropped_calcs and 'REJECTED_BINDING' in dropped_calcs['總工期']['reason']
    assert '總電流' not in dropped_calcs
    assert cleaned['known_facts']  # the rest of the draft is unaffected


def test_all_numbers_grounded_rejects_a_prose_number_that_slips_to_the_wrong_scale():
    """BB07's U3 sub-issue (claude-b, 2026-11-03): a real 27B reply wrote a
    conclusion at the wrong order of magnitude ('10件' when the grounded
    quantity was actually '10萬件'). Checking (value, unit) together instead
    of bare digits alone catches this -- '10件' is dimension 'count',
    the ledger only grounds dimension 'amount_wan' at that value."""
    L = _ledger_for('損益平衡點為10萬件。')
    grounded, bad_num = reasoning._all_numbers_grounded('損益平衡點為10件', L, {})
    assert not grounded and bad_num == '10件'
    grounded_ok, _ = reasoning._all_numbers_grounded('損益平衡點為10萬件', L, {})
    assert grounded_ok


def test_a_number_only_valid_via_a_verified_derived_calculation_is_accepted():
    """app/binding.py always expands money to elementary units (20萬元 ->
    200000) to close the exact BB07 "萬 unit" confusion it was built to fix
    -- so a derived result citing that computation must also be stated in
    elementary units (1,000,000元, i.e. 100萬元) to be recognized as the
    SAME number by the free-text grounding check."""
    L = _ledger_for('設備80萬元，每年省20萬元，5年。')
    struct = _valid_struct(
        known_facts=['5年總共可節省1000000元'],
        risks=[{'id': 'R-1', 'severity': 'medium', 'message': '設備80萬元，需留意回收期'}],
        options=[{'id': 'O-1', 'title': '維持現狀', 'feasibility': 'unverified', 'rationale': '每年省20萬元，尚待確認其他成本'}],
        derived_calculations=[{'name': '5年總節省', 'formula': 'a * b',
                               'inputs': {'a': ref('q2', '每年省的錢'), 'b': 'q3'}}])
    ok, cleaned, reason = reasoning.validate_reasoning(struct, L)
    assert ok, reason


def test_a_number_only_valid_via_schedule_analysis_total_is_accepted():
    L = _ledger_for('任務A工期2週，任務B工期4週，任務C工期3週，依序執行。')
    struct = _valid_struct(
        known_facts=['任務依序執行，總工期為9週'],
        risks=[{'id': 'R-1', 'severity': 'medium', 'message': '任務A工期2週'}],
        options=[{'id': 'O-1', 'title': '維持現狀', 'feasibility': 'unverified', 'rationale': '任務B工期4週，尚待確認資源'}],
        schedule_analysis=[
            {'id': 'A', 'duration': ref('q1', '任務A工期')},
            {'id': 'B', 'duration': ref('q2', '任務B工期'), 'after': ['A']},
            {'id': 'C', 'duration': ref('q3', '任務C工期'), 'after': ['B']},
        ])
    ok, cleaned, reason = reasoning.validate_reasoning(struct, L)
    assert ok, reason


def test_schedule_analysis_wrong_type_is_rejected():
    L = _ledger_for('目前月費8萬元。')
    struct = _valid_struct(schedule_analysis='not a list')
    ok, cleaned, reason = reasoning.validate_reasoning(struct, L)
    assert not ok
    assert 'schedule_analysis' in reason


def test_invalid_severity_label_is_dropped_but_other_content_survives():
    L = _ledger_for('目前月費8萬元。')
    struct = _valid_struct(risks=[{'id': 'R-1', 'severity': 'super-bad', 'message': '目前月費8萬元'}])
    ok, cleaned, reason = reasoning.validate_reasoning(struct, L)
    assert ok, reason
    assert cleaned['risks'] == []
    assert any(d['category'] == 'risks' and 'severity' in d['reason'] for d in cleaned['_dropped'])
    assert cleaned['known_facts'] and cleaned['options']  # _valid_struct()'s defaults survive


def test_invalid_feasibility_label_is_dropped_but_other_content_survives():
    L = _ledger_for('目前月費8萬元。')
    struct = _valid_struct(options=[{'id': 'O-1', 'title': 'X', 'feasibility': 'maybe', 'rationale': '目前月費8萬元'}])
    ok, cleaned, reason = reasoning.validate_reasoning(struct, L)
    assert ok, reason
    assert cleaned['options'] == []
    assert any(d['category'] == 'options' and 'feasibility' in d['reason'] for d in cleaned['_dropped'])
    assert cleaned['known_facts'] and cleaned['risks']


def test_non_dict_input_is_rejected_not_crashed():
    L = _ledger_for('目前月費8萬元。')
    ok, cleaned, reason = reasoning.validate_reasoning(['not', 'a', 'dict'], L)
    assert not ok and cleaned is None


# --- parse_reasoning_json ---------------------------------------------------

def test_parse_reasoning_json_strips_markdown_fences():
    text = '```json\n{"a": 1}\n```'
    assert reasoning.parse_reasoning_json(text) == {'a': 1}


def test_parse_reasoning_json_returns_none_on_garbage():
    assert reasoning.parse_reasoning_json('this is not json at all') is None


# --- render_reasoning_as_result_fields --------------------------------------

def test_render_reasoning_produces_the_existing_result_shape():
    struct = _valid_struct(hard_constraints=['45天內必須到貨'], risk_causal_chain=['延遲 -> 違約'])
    facts, options, risks, questions, unknowns = reasoning.render_reasoning_as_result_fields(struct)
    assert any('45天內必須到貨' in f['claim'] for f in facts)
    assert any('延遲 -> 違約' in f['claim'] for f in facts)
    assert options[0]['hard_constraint'] == 'unverified'
    assert risks[0]['severity'] == 'medium'
    assert questions == ['取得更多資料']


# --- build_reasoning_prompt sanity ------------------------------------------

def test_build_reasoning_prompt_includes_question_and_ledger_facts():
    L = _ledger_for('目前月費8萬元。')
    prompt = reasoning.build_reasoning_prompt(L, '目前月費8萬元，會超支嗎？', [], {})
    assert '目前月費8萬元，會超支嗎？' in prompt
    assert '8萬元' in prompt


def test_build_reasoning_prompt_surfaces_conflicts_explicitly():
    documents = [
        {'id': 'DOC-A', 'excerpt': '本次訂單的交貨期是20天。'},
        {'id': 'DOC-B', 'excerpt': '本次訂單的交貨期是45天。'},
    ]
    L = build_ledger([''], documents)
    prompt = reasoning.build_reasoning_prompt(L, '交期是多少？', documents, {})
    assert 'DOC-A' in prompt and 'DOC-B' in prompt
    assert '矛盾' in prompt


def test_build_reasoning_prompt_lists_bare_numbers_too():
    """BB01's real root cause (per claude-b): task durations listed under a
    table header with no inline unit. app/ledger.py's `Ledger.bare` captures
    these; the prompt must still show them (with a distinct, honest label)
    so the LLM can cite them via their own [bN] ref."""
    documents = [{'id': 'D-PLAN', 'excerpt': '任務（工期，週）：A 設計 2；B 後端 4（A）。'}]
    L = build_ledger([''], documents)
    assert L.bare  # sanity: this scenario really does produce bare numbers
    prompt = reasoning.build_reasoning_prompt(L, '工期是多少？', documents, {})
    assert any(f"[{q['ref']}]" in prompt for q in L.bare)


# --- rank_risks (deterministic severity ordering, P1 item 4) --------------

def test_rank_risks_orders_critical_first_and_stable_on_ties():
    risks = [
        {'id': 'R-1', 'severity': 'low'},
        {'id': 'R-2', 'severity': 'critical'},
        {'id': 'R-3', 'severity': 'high'},
        {'id': 'R-4', 'severity': 'critical'},
    ]
    ranked = reasoning.rank_risks(risks)
    assert [r['id'] for r in ranked] == ['R-2', 'R-4', 'R-3', 'R-1']
    assert [r['priority_rank'] for r in ranked] == [0, 1, 2, 3]


def test_render_reasoning_sorts_risks_by_severity():
    struct = _valid_struct(risks=[
        {'id': 'R-1', 'severity': 'low', 'message': '目前月費8萬元'},
        {'id': 'R-2', 'severity': 'critical', 'message': '目前月費8萬元'},
    ])
    facts, options, risks, questions, unknowns = reasoning.render_reasoning_as_result_fields(struct)
    assert risks[0]['id'] == 'R-2' and risks[0]['priority_rank'] == 0
    assert risks[1]['id'] == 'R-1' and risks[1]['priority_rank'] == 1
