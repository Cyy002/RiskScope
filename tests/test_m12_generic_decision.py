"""M12: generic (domain-agnostic) decision-support scaffold for every focus
that has no dedicated engineering rule, plus the two new M7/Phase-4 guards
that keep the LLM's qualitative phrasing of it honest.

Fix under test:
- app.analyzer._generic_decision_support() / _read_project_signals(): the
  previously-empty `options`/`facts` for any non-motor/power focus are now
  populated from this project's REAL project_signals and trace_impact()
  output -- never from a per-focus hardcoded string -- and every option stays
  'unverified'. app.analyzer.analyze()'s result also carries an explicit
  `decision_structure` view (Decision Context / Evidence / Known-Unknown /
  Options / Consequences / Risk Comparison / Next Actions) built from the
  exact same fields, reusable by the next focus without any new code.
- app.chat._reply_is_trustworthy(): on the generic (non-engineering) focus
  path, a phrased reply stating a percentage/schedule/cost number with no
  trusted source (M8's one deterministic percentage, or a literal match in
  the user's message/an authorized document) is no longer rejected outright
  (superseded 2026-11-05, user-authorized -- see the two
  test_llm_reply_keeps_* tests below) -- it is kept with a visible
  "請自行核實" caveat instead. The high-risk CLAIM checks (approval/safety/
  verification/availability/ranking/nameplate-change) are untouched and
  still hard-reject the whole reply.
- app.chat._focus_mismatch_warning(): a cheap, deterministic keyword check
  that flags (never blocks, never auto-switches) a likely focus/question
  mismatch.

All tests use the isolated tmp_path database from tests/conftest.py; no
production runtime/credentials are touched. LLM-reply tests mock
app.chat.call_ollama directly -- no real Ollama call.
"""
from app import chat
from tests.conftest import ROOT


def _fake_call_ollama(reply_text):
    def fake(prompt, timeout=30, keep_alive='10m'):
        if '只負責從使用者訊息' in prompt:
            return '{}', {'status': 'success', 'elapsed_seconds': 0.01}
        return reply_text, {'status': 'success', 'elapsed_seconds': 0.01}
    return fake


def test_generic_options_and_decision_structure_for_supplier_focus(c, engineer):
    a = c.post(ROOT + '/analyze', headers=engineer,
               json={'question': '供應商交期變更', 'focus': 'supplier'}).json()
    assert a['checks'] == []
    assert len(a['options']) == 3
    assert all(o['hard_constraint'] == 'unverified' for o in a['options'])
    assert all('consequences' in o for o in a['options'])
    ds = a['decision_structure']
    assert ds['decision_context'] == {'question': a['question'], 'focus': 'supplier',
                                       'priorities': a['priorities']}
    assert ds['options'] == a['options']
    assert ds['risk_comparison'] == a['risks']
    assert ds['next_actions'] == a['questions_to_manager']
    assert len(ds['consequences']) == 3
    assert any(r['id'] == 'R-UNVALIDATED-ANALYSIS' for r in a['risks'])


def test_project_signals_feed_known_and_unknown_not_hardcoded(c, engineer):
    """demo-chamber's seed data (app/db.py) has supplier_lead_days='7' (known)
    and test_pass='unknown' (unknown) -- this asserts both actually reach the
    analysis output through the real project_signals table, not a fixture the
    test itself injects."""
    a = c.post(ROOT + '/analyze', headers=engineer,
               json={'question': '供應商交期變更', 'focus': 'supplier'}).json()
    assert any('supplier_lead_days = 7' in f['claim'] for f in a['facts'])
    assert any(u['topic'] == '專案訊號：test_pass' for u in a['unknowns'])
    assert any('test_pass' in q for q in a['questions_to_manager'])


def test_other_generic_focuses_also_get_the_same_scaffold(c, engineer):
    """Not hardcoded to 'supplier' specifically -- any focus with no
    dedicated engineering rule gets the same generic scaffold."""
    for focus in ('driver', 'firmware', 'mechanical', 'thermal', 'requirements', 'test_failure'):
        a = c.post(ROOT + '/analyze', headers=engineer,
                   json={'question': f'{focus} 情境評估', 'focus': focus}).json()
        assert a['checks'] == []
        assert len(a['options']) == 3
        assert all(o['hard_constraint'] == 'unverified' for o in a['options'])


def test_unrelated_focus_has_no_keyword_based_mismatch_warning(c, engineer):
    """'unrelated' is the dedicated negative-control focus (FOCUS_ROOTS'
    ISOLATED-01 root) -- it deliberately has no FOCUS_KEYWORDS entry, so it
    never triggers Phase 4's mismatch warning regardless of message content."""
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "今天天氣真好，要不要去買咖啡？", "session_id": "m12-unrelated",
        "focus": "unrelated", "use_local_llm": False,
    })
    assert resp.json()["focus_mismatch_warning"] is None


def test_focus_mismatch_warning_for_irrelevant_message_on_default_focus(c, engineer):
    """Reproduces M11.5's Case E bug: an irrelevant chit-chat message with the
    focus left at its default (motor_upgrade) must no longer silently run the
    motor calculation without any caveat."""
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "今天天氣真好，我想晚點去買一杯咖啡，你覺得拿鐵還是美式比較好？",
        "session_id": "m12-mismatch-a", "use_local_llm": False,
    })
    data = resp.json()
    assert data["focus_mismatch_warning"] is not None
    assert "馬達升級與負載" in data["focus_mismatch_warning"]
    assert data["reply"].startswith("提醒：")


def test_no_mismatch_warning_when_message_matches_selected_focus(c, engineer):
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "關鍵供應商交貨延遲，品質驗證尚未完成，但客戶交期不能延後。應該如何決策？",
        "session_id": "m12-mismatch-b", "focus": "supplier", "use_local_llm": False,
    })
    data = resp.json()
    assert data["focus_mismatch_warning"] is None
    assert not data["reply"].startswith("提醒：")


def test_llm_reply_keeps_a_fabricated_percentage_but_flags_it_as_unverified(c, engineer, monkeypatch):
    """Superseded 2026-11-05 (user-authorized, after real Batch G evidence
    that whole-reply rejection on any ungrounded number discarded the large
    majority of genuinely good analyses -- see ai_progress/
    RISK_INTELLIGENCE_EVALUATION/NEW_APP_ACCEPTANCE_RESULT.md): the supplier
    focus never computes any percentage, so "30%的機率" is still NOT a
    verified fact -- but a derived/estimated NUMBER is no longer grounds to
    discard the whole reply, only to flag it. This is a deliberate,
    authorized trade-off, not a regression: the high-risk CLAIM checks
    (approval/safety/verification/availability/ranking/nameplate-change,
    see the next test) are completely unaffected and remain hard rejections."""
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('根據分析，這個供應商延誤有大約 30% 的機率會影響交期。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "關鍵供應商交貨延遲，品質驗證尚未完成，但客戶交期不能延後。應該如何決策？",
        "session_id": "m12-pct", "focus": "supplier", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "llm_phrased"
    assert data["llm_diagnostic"]["reply"]["status"] == "success_with_unverified_numbers"
    assert "30%" in data["reply"] and "請自行核實" in data["reply"]


def test_llm_reply_keeps_a_fabricated_schedule_and_cost_but_flags_them_as_unverified(c, engineer, monkeypatch):
    """Same supersession as above, for schedule/cost figures."""
    monkeypatch.setattr(chat, 'call_ollama',
                         _fake_call_ollama('預計延誤 10 天，額外成本約新增 50萬元，建議先接受此風險。'))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "關鍵供應商交貨延遲，品質驗證尚未完成，但客戶交期不能延後。應該如何決策？",
        "session_id": "m12-cost", "focus": "supplier", "use_local_llm": True,
    })
    data = resp.json()
    assert data["reply_source"] == "llm_phrased"
    assert data["llm_diagnostic"]["reply"]["status"] == "success_with_unverified_numbers"
    assert "50萬元" in data["reply"] and "請自行核實" in data["reply"]


def test_existing_motor_baseline_percentage_still_trusted():
    """Regression guard, as a direct unit test (no API/extraction involved):
    M11.4's real, deterministically-computed baseline percentages (e.g.
    "超出 40%"/"超出 75%" from Case A's actual numbers) must still pass the
    new percent check -- it must reject FABRICATED percentages only, never a
    real one the engine actually computed."""
    result = {'checks': [{
        'status': 'fail',
        # M12.5.1: nameplate and actual-usable capacity are reported independently
        'numbers': {'total_current_a': '14', 'limit_current_a': '8',
                    'nameplate_limit_current_a': '10', 'actual_limit_current_a': '8',
                    'total_power_w': '336', 'limit_power_w': '192'},
    }]}
    text = ('新方案總電流 14A，電源額定 8A，總功率 336W，'
            '相對現有額定超出 40%，相對新方案本身額定超出 75%，仍需人工審核。')
    trustworthy, reason = chat._reply_is_trustworthy(text, result, None, None, None, '')
    assert trustworthy, reason


def test_fabricated_percentage_rejected_even_with_a_real_baseline():
    """Same baseline as above, but the reply states a THIRD, "超出"-anchored
    percentage (33%) that the engine never computed -- must still be
    rejected, distinctly from an unanchored claim (see
    test_fabricated_percentage_rejected_even_with_a_real_baseline's sibling
    test_llm_reply_rejected_for_fabricated_percentage, which covers the
    unanchored "機率" case with a different, generic rejection reason)."""
    result = {'checks': [{
        'status': 'fail',
        'numbers': {'total_current_a': '14', 'limit_current_a': '8',
                    'total_power_w': '336', 'limit_power_w': '192'},
        'baseline': {'numbers': {'total_current_a': '14', 'limit_current_a': '10',
                                  'total_power_w': '336', 'limit_power_w': '240'}},
    }]}
    text = '這個方案相對現有額定超出 33%，風險偏高，建議謹慎評估。'
    trustworthy, reason = chat._reply_is_trustworthy(text, result, None, None, None, '')
    assert not trustworthy
    assert '33' in reason


def test_supplier_scenario_two_options_no_fabrication_deterministic(c, engineer):
    """Phase 3's acceptance scenario, deterministic path (use_local_llm=False,
    no Ollama dependency, fast) -- real project_signals, real documents, real
    dependency trace, at least two conditional options, no fabricated day
    count, cost, or probability anywhere in the reply. The question's own
    "交期不能延後" constraint is expected to flag G-B (see
    test_options_flag_a_stated_conflicting_constraint) -- so options are
    'unverified' or 'conflicts_with_stated_constraint', never anything
    stronger (e.g. never 'confirmed'/'approved')."""
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "關鍵供應商交貨延遲，品質驗證尚未完成，但客戶交期不能延後。應該如何決策？",
        "session_id": "m12-supplier-e2e", "focus": "supplier", "use_local_llm": False,
    })
    data = resp.json()
    assert len(data["options"]) >= 2
    assert all(o["hard_constraint"] in ("unverified", "conflicts_with_stated_constraint")
               for o in data["options"])
    assert "unverified" in data["reply"]
    assert not chat._SCHEDULE_COST_SUFFIX_RE.search(data["reply"])
    assert not chat._SCHEDULE_COST_PREFIX_RE.search(data["reply"])
    assert not chat._ANY_PERCENT_RE.search(data["reply"])
    assert data["focus_mismatch_warning"] is None


def test_options_flag_a_stated_conflicting_constraint(c, engineer):
    """M12-05 (Codex independent review): the 3 generic options were
    previously byte-identical regardless of what the user's own question
    said -- two opposite, explicit constraints must now produce different
    options (never silently ignored), grounded only in the question's own
    text, never invented."""
    no_delay = c.post(ROOT + '/analyze', headers=engineer, json={
        'question': '供應商交貨延遲，交期不能延後，禁止替代供應商。', 'focus': 'supplier',
    }).json()
    delay_ok = c.post(ROOT + '/analyze', headers=engineer, json={
        'question': '供應商交貨延遲，可以延後交期，優先更換供應商。', 'focus': 'supplier',
    }).json()
    assert no_delay['options'] != delay_ok['options']
    by_id = {o['id']: o for o in no_delay['options']}
    assert by_id['G-B']['hard_constraint'] == 'conflicts_with_stated_constraint'
    assert by_id['G-C']['hard_constraint'] == 'conflicts_with_stated_constraint'
    assert all(o['hard_constraint'] == 'unverified' for o in delay_ok['options'])


def test_codex_probe_mismatch_is_stated_constraint_not_regression(c, engineer, monkeypatch):
    """M12.1: confirms the one remaining ai_progress/codex-review-m12/
    review_probes.py failure (test_unverified_qualitative_claim_cannot_
    become_confirmed, which asserts every option is literally 'unverified')
    is exactly the M12-05 constraint-flagging feature reacting to that
    probe's own default message -- '供應商交貨延遲，品質驗證尚未完成，交期不能延後。'
    contains the G-B trigger phrase '交期不能延後' -- and not a hidden
    regression. Reproduces that exact message and checks the three
    properties the user asked to confirm: (1) conflicts_with_stated_
    constraint appears where (and only where) the question's own text states
    a conflicting constraint; (2) a flagged option is never phrased as
    already-approved/recommended -- decision_status stays requires_human_
    review and the qualitative-fabrication claim in the mocked reply is still
    rejected; (3) an option the question says nothing about (G-A here) still
    keeps the plain 'unverified' status, not something stronger."""
    model_text = '品質驗證已完成，替代供應商已確認可用，方案G-C的成本最低。'
    monkeypatch.setattr(chat, 'call_ollama', _fake_call_ollama(model_text))
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "供應商交貨延遲，品質驗證尚未完成，交期不能延後。",
        "session_id": "m12-probe-repro", "focus": "supplier", "use_local_llm": True,
    })
    data = resp.json()
    by_id = {o['id']: o for o in data['options']}
    # (1) only G-B's trigger phrase is present -- G-B flagged, G-C is not
    # (the message never says anything about replacing the supplier).
    assert by_id['G-B']['hard_constraint'] == 'conflicts_with_stated_constraint'
    assert by_id['G-C']['hard_constraint'] == 'unverified'
    # (2) the LLM's fabricated "already confirmed/lowest cost" claim is still
    # rejected outright -- a conflicting OR unverified option is never
    # presented as approved/recommended.
    assert data['decision_status'] == 'requires_human_review'
    assert data['reply_source'] == 'deterministic_template'
    assert data['llm_diagnostic']['reply']['status'] == 'rejected_inconsistent'
    assert model_text not in data['reply']
    # (3) an option the question never mentions keeps plain 'unverified'.
    assert by_id['G-A']['hard_constraint'] == 'unverified'


def test_mismatch_suppresses_analysis_for_genuine_off_topic_message(c, engineer):
    """M12-07 (Codex independent review): a genuinely unrelated message
    (coffee/weather) must not receive a real engineering calculation at all,
    not just a warning on top of one. M12.1: a real GUI run found that even
    with checks==[], the reply still cited real "R-IMPACT-M-02"/"R-IMPACT-
    PS-01" risks (trace_impact() still ran for motor_upgrade's FOCUS_ROOTS and
    got folded into `risks`/`inferences`) -- leaking the mismatched focus's
    identifiers into an otherwise-withheld reply. Confirms that's now also
    withheld: no R-IMPACT-* risk and no impact-derived inference for a
    suppressed turn."""
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "拿鐵和美式咖啡哪個比較好？", "session_id": "m12-offtopic",
        "focus": "motor_upgrade", "use_local_llm": False,
    })
    data = resp.json()
    assert data["focus_mismatch_warning"]
    assert not any(r['id'].startswith('R-IMPACT-') for r in data['risks'])
    assert not any('已記錄的依賴顯示' in i for i in data['inferences'])
    # impact_step's raw lookup is still allowed to run (harmless, ACL-safe,
    # kept in result['impacts'] for audit) -- only folding it into the
    # user-facing risks/inferences is withheld.
    assert data['impacts']
    assert data["checks"] == []


def test_mismatch_warning_does_not_suppress_a_terse_on_topic_followup(c, engineer):
    """Regression guard for the false positive Codex's review warned about:
    a terse follow-up that never repeats a focus keyword (and isn't off-
    topic chit-chat either) must still get a real analysis underneath any
    warning -- this is exactly what broke several existing session-
    continuity/ACL tests the first time suppression was tried broadly."""
    resp = c.post(f"{ROOT}/chat", headers=engineer, json={
        "message": "請再確認一次結論就好。", "session_id": "m12-terse-followup",
        "focus": "motor_upgrade", "use_local_llm": False,
    })
    data = resp.json()
    assert data["checks"] != []
