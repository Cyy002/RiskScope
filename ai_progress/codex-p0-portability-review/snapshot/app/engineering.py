"""Deterministic dimensional and constraint checks. Never delegate arithmetic to an LLM."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from .retrieval import read_facts

UNIT_TABLE = {
    'A': ('current',Decimal('1')),
    'mA': ('current',Decimal('0.001')),
    'kA': ('current',Decimal('1000')),
    'V': ('voltage',Decimal('1')),
    'mV': ('voltage',Decimal('0.001')),
    'kV': ('voltage',Decimal('1000')),
    'W': ('power',Decimal('1')),
    'kW': ('power',Decimal('1000')),
}


def convert(value: str, unit: str, expected_dimension: str):
    if unit not in UNIT_TABLE:
        raise ValueError(f'不支援的單位：{unit}')
    dimension, scale = UNIT_TABLE[unit]
    if dimension != expected_dimension:
        raise ValueError(f'單位維度不相容：預期 {expected_dimension}，取得 {unit}')
    try:
        v = Decimal(str(value)) * scale
        if not v.is_finite() or v < 0 or v > Decimal('1000000000'):
            raise ValueError('數值必須為合理範圍內的非負有限數')
        return v
    except InvalidOperation:
        raise ValueError('無法解析數值')


def clean(d):
    return format(d.normalize(), 'f') if isinstance(d, Decimal) else d


#: fact_key -> physical dimension, for whichever caller validates a user-supplied
#: candidate before it ever reaches this module (see app/chat.py). Exposed here so
#: there is exactly one place that defines which keys this rule can accept.
#:
#: M12.5.1: `supply_actual_current` is a genuinely separate field from
#: `supply_continuous_current` -- Codex's independent review of M12.5 found
#: that conflating "nameplate rating" (always from a document, e.g. DOC-PS's
#: 10A) and "actual usable/de-rated capacity" (a user-supplied scenario
#: constraint, e.g. 8A) into the SAME field, modelled as a baseline-vs-
#: override pair, could never stop narrating the actual-capacity fact as "由
#: 10A改成8A" -- that framing is only ever appropriate for a genuine
#: nameplate replacement (a different, real supply). The two values are
#: simultaneously true facts about the SAME hardware, not a before/after
#: pair, so they now live in two independent keys. `supply_actual_current`
#: never has a document fact (see app/db.py's seed data), so it is always
#: 'missing' until the user states it -- power_continuous() below treats it
#: as optional, never required, and a plain supplied value naturally fills
#: that gap via the pre-existing 'missing facts accept a plain supplement'
#: rule, with no need for the forced-replace special case M12.5 depended on.
USER_SUPPLIABLE_KEYS = {
    'supply_voltage': 'voltage', 'supply_continuous_current': 'current',
    'supply_actual_current': 'current',
    'motor_voltage': 'voltage', 'motor_continuous_current': 'current',
    'aux_continuous_current': 'current',
}

#: M11.4: a human-readable Chinese description per key, purely to help the
#: LLM extraction prompt (app/chat.py) map varied free-text phrasing to the
#: right field -- "電源實際持續可用容量" has no lexical overlap with the bare
#: variable name `supply_continuous_current`, and M11.3's real-GUI run showed
#: the model inconsistently failing to make that connection without an
#: explicit hint. These are field descriptions, not example values -- they
#: never mention a specific number, so they generalize to any phrasing of the
#: same field rather than fitting one test case.
USER_SUPPLIABLE_KEY_DESCRIPTIONS = {
    'supply_voltage': '電源／供電的電壓',
    'supply_continuous_current': '電源／供電的名目／標稱連續額定電流（通常來自文件規格），不是降額後的實際可用容量',
    'supply_actual_current': '電源／供電「實際持續可用容量」或「降額後可用」的電流上限——是額定之外另一個獨立數值，'
                              '不是取代或修改名目額定，兩者可以同時存在、同時有效',
    'motor_voltage': '馬達的電壓',
    'motor_continuous_current': '馬達的連續電流，包含「新馬達」「替換馬達」「改用～馬達」等各種描述方式',
    'aux_continuous_current': '輔助／其他負載的連續電流',
}

#: canonical unit a combined/overridden fact's recomputed value is stored in,
#: so an 'add' candidate given in a different-but-compatible unit (e.g. mA
#: added to an A-denominated document fact) has one unambiguous result unit.
_BASE_UNIT = {'voltage': 'V', 'current': 'A'}


def power_continuous(conn, actor, project, simultaneous=True, user_supplied=None):
    """user_supplied: optional {fact_key: {'value':str,'unit':str,'mode':str}}.
    `mode` ('replace'/'add', set by app/chat.py only when the user's own text
    carries explicit change-intent language -- see chat._change_intent_mode)
    is what M8 adds: without it, an already-authorized ('ok') document fact is
    still never touched -- this function only fills genuine gaps
    (missing/stale/unauthorized), exactly as before M8. With explicit intent,
    an 'ok' fact CAN now be superseded for this one call -- 'replace' swaps in
    the caller's value (e.g. "馬達換成 11A 的新馬達"), 'add' sums it onto the
    existing authorized value (e.g. "輔助負載再新增 2A") -- modelling a
    user-proposed *scenario*, never a silent correction of the real spec: the
    result is labelled 'proposed_change' in evidence (never written to the
    `facts` table), and whenever any override happens this also recomputes and
    attaches the pure document baseline (`result['baseline']`, i.e. the exact
    result with no overrides at all) so a reply can show old-vs-proposed
    side by side instead of just replacing one number with another silently.
    The caller (app/chat.py) is expected to have already dimension- and
    grounding-validated these, but this function re-validates independently --
    a malformed or wrong-dimension candidate is simply never applied, never
    raises, and the key falls back to whatever status it already had.

    `mode='add'` with NO authorized baseline to add onto (the document fact
    is itself missing/stale/unauthorized) is a special case: the delta is
    never substituted in as if it WERE the whole load -- that fact stays
    exactly as unusable as before (still correctly 'unknown'), and the known
    increment is instead reported in `result['pending_additions']` so a reply
    can ask for the missing baseline instead of silently treating e.g. "新增
    2A" as a 2A total system current.

    M12.5.1: `supply_actual_current` (see USER_SUPPLIABLE_KEYS) is OPTIONAL --
    unlike the five required fields, it has no document fact at all, so a
    session that never mentions it is not "missing required data"; the
    circuit is simply evaluated against the nameplate rating alone, exactly
    as before M8 ever existed. When known, it becomes the BINDING limit
    (never looser than the nameplate) without replacing or overriding the
    nameplate field in any way -- both numbers are always reported
    independently in `numbers` (`nameplate_limit_current_a`/
    `actual_limit_current_a`), so a caller can show "超出額定X%／超出實際容量Y%"
    without the recursive baseline-vs-override machinery M12.5 needed."""
    required_keys = ['supply_voltage','supply_continuous_current','motor_voltage',
                      'motor_continuous_current','aux_continuous_current']
    optional_keys = ['supply_actual_current']
    keys = required_keys + optional_keys
    facts = read_facts(conn, actor, project, keys)
    user_supplied = user_supplied or {}
    overridden = []
    pending_additions = []
    for k in keys:
        if k not in user_supplied:
            continue
        candidate = user_supplied[k]
        mode = candidate.get('mode')
        is_ok = facts[k]['status'] == 'ok'
        if is_ok and mode not in ('replace', 'add'):
            # Defense in depth (M6/M7): a value merely restated, with no
            # explicit change-intent language from the user, can never
            # silently supersede an already-authorized document spec -- only
            # a genuine gap (missing/stale/unauthorized) accepts a plain
            # supplement, exactly as before M8.
            continue
        dimension = USER_SUPPLIABLE_KEYS[k]
        try:
            # Defense in depth: never trust a caller's claim that a value was
            # already validated. A malformed/wrong-dimension candidate is
            # simply not applied -- the key falls back to whatever status it
            # already had, it is never allowed to silently corrupt the
            # calculation.
            converted = convert(candidate['value'], candidate['unit'], dimension)
        except (ValueError, KeyError, TypeError):
            continue
        original = facts[k]
        if mode == 'add' and not is_ok:
            # No authoritative baseline to add onto -- the user's delta is
            # NOT the system's whole load, so it must never be substituted in
            # as if it were. `facts[k]` is left exactly as it was
            # (missing/stale/unauthorized, still correctly 'unknown' below);
            # the known increment is only recorded separately so a reply can
            # ask for the missing baseline instead of silently fabricating one.
            pending_additions.append({'fact_key':k,'added_value':candidate['value'],'added_unit':candidate['unit'],
                                       'reason':f"原始數值狀態為「{original['status']}」，沒有可供疊加的基準，"
                                                 f"無法只憑新增量 {candidate['value']}{candidate['unit']} 計算總量"})
            continue
        if mode == 'add':  # and is_ok
            try:
                base = convert(original['value'], original['unit'], dimension)
            except ValueError:
                continue
            facts[k] = {'status':'proposed_change','value':clean(base + converted),'unit':_BASE_UNIT[dimension],
                        'change_mode':'add','added_value':candidate['value'],'added_unit':candidate['unit'],
                        'baseline_value':original['value'],'baseline_unit':original['unit'],
                        'baseline_source_id':original.get('source_id'),'baseline_source_version':original.get('source_version')}
        elif is_ok:
            facts[k] = {'status':'proposed_change','value':candidate['value'],'unit':candidate['unit'],
                        'change_mode':'replace',
                        'baseline_value':original['value'],'baseline_unit':original['unit'],
                        'baseline_source_id':original.get('source_id'),'baseline_source_version':original.get('source_version')}
        else:
            facts[k] = {'status':'user_supplied', 'value':candidate['value'], 'unit':candidate['unit']}
        overridden.append(k)
    baseline = power_continuous(conn, actor, project, simultaneous, user_supplied=None) if overridden else None
    missing = [k for k in required_keys if facts[k]['status'] not in ('ok','user_supplied','proposed_change')]
    evidence = [({'fact_key':k,'source_id':f['source_id'],'source_version':f['source_version'],
                  'value':f['value'],'unit':f['unit'],'origin':'document','verified':True}
                 if f['status']=='ok' else
                 {'fact_key':k,'value':f['value'],'unit':f['unit'],
                  'origin':'proposed_change','verified':False,'change_mode':f.get('change_mode'),
                  'baseline_value':f.get('baseline_value'),'baseline_unit':f.get('baseline_unit'),
                  'baseline_source_id':f.get('baseline_source_id'),'baseline_source_version':f.get('baseline_source_version'),
                  'added_value':f.get('added_value'),'added_unit':f.get('added_unit')}
                 if f['status']=='proposed_change' else
                 {'fact_key':k,'value':f['value'],'unit':f['unit'],
                  'origin':'user_supplied_this_turn','verified':False})
                for k,f in facts.items() if f['status'] in ('ok','user_supplied','proposed_change')]
    extra = {}
    if baseline:
        extra['baseline'] = baseline
    if pending_additions:
        extra['pending_additions'] = pending_additions
    if missing:
        return {'rule':'continuous_power','status':'unknown', 'reason':'必要規格缺漏、過期或沒有授權',
                'unusable_facts':{k:facts[k]['status'] for k in missing}, 'evidence':evidence,
                'user_supplied_fact_keys':overridden,
                'assumptions':['馬達與其他負載同時持續運作'] if simultaneous else [], **extra}
    try:
        v_supply = convert(facts['supply_voltage']['value'], facts['supply_voltage']['unit'], 'voltage')
        v_motor = convert(facts['motor_voltage']['value'], facts['motor_voltage']['unit'], 'voltage')
        i_nameplate = convert(facts['supply_continuous_current']['value'], facts['supply_continuous_current']['unit'], 'current')
        i_motor = convert(facts['motor_continuous_current']['value'], facts['motor_continuous_current']['unit'], 'current')
        i_aux = convert(facts['aux_continuous_current']['value'], facts['aux_continuous_current']['unit'], 'current')
    except ValueError as exc:
        return {'rule':'continuous_power','status':'unknown','reason':str(exc),'evidence':evidence,
                'unusable_facts':{},'user_supplied_fact_keys':overridden,
                'assumptions':['馬達與其他負載同時持續運作'] if simultaneous else [], **extra}
    # M12.5.1: actual-usable capacity is optional and independent of the
    # nameplate -- when known it becomes the binding limit (never looser than
    # the nameplate), but the nameplate number itself is always reported too,
    # so a caller can state BOTH "超出額定X%" and "超出實際容量Y%" without any
    # recursive baseline comparison.
    i_actual = None
    actual_fact = facts.get('supply_actual_current') or {}
    if actual_fact.get('status') in ('user_supplied', 'proposed_change'):
        try:
            i_actual = convert(actual_fact['value'], actual_fact['unit'], 'current')
        except ValueError:
            i_actual = None
    i_limit = min(i_nameplate, i_actual) if i_actual is not None else i_nameplate
    if not simultaneous:
        return {'rule':'continuous_power','status':'unknown', 'reason':'未確認馬達與其他負載同時持續運作，不能直接相加評估峰值',
                'evidence':evidence,'user_supplied_fact_keys':overridden,
                'assumptions':['非同時負載仍待實測或取得控制策略'], **extra}
    total = i_motor + i_aux
    same_voltage = v_supply == v_motor
    status = 'fail' if (total > i_limit or not same_voltage) else 'pass'
    numbers = {'supply_voltage_v':clean(v_supply),'motor_voltage_v':clean(v_motor),
               'motor_current_a':clean(i_motor),'other_current_a':clean(i_aux),
               'total_current_a':clean(total),'limit_current_a':clean(i_limit),
               'nameplate_limit_current_a':clean(i_nameplate),
               'total_power_w':clean(v_supply*total), 'limit_power_w':clean(v_supply*i_limit),
               'nameplate_limit_power_w':clean(v_supply*i_nameplate),
               'over_current_a':clean(max(Decimal(0),total-i_limit))}
    if i_actual is not None:
        numbers['actual_limit_current_a'] = clean(i_actual)
        numbers['actual_limit_power_w'] = clean(v_supply*i_actual)
    return {'rule':'continuous_power','status':status,
            'reason':('電源與馬達額定電壓不相容' if not same_voltage else
                      '持續電流需求超過電源連續額定值' if status=='fail' else
                      '就已知指定工況，連續電流未超過額定值；其他限制仍待驗證'),
            'numbers':numbers,
            'formula':'I_total = I_motor + I_other；P = V × I',
            'evidence':evidence,'assumptions':['馬達與其他負載同時持續運作；數值為指定合成工況的連續值'],
            'user_supplied_fact_keys':overridden,
            'limitations':['超額不等於必然跳脫或損壞','未取得啟動電流、電源降額、驅動器/散熱/線材驗證']
                + (['本次計算包含使用者在對話中提供、尚未經管理者正式確認的數值（見 evidence 的 verified:false 項目）；'
                    '結果僅供本次對話參考，不可視為已確認規格'] if overridden else []), **extra}
