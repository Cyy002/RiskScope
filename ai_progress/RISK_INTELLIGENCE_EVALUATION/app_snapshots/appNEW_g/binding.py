"""Input-binding verification for model-proposed calculations (claude-b; NEW module).

Lesson from the first LLM-led prototype (ai_progress/RISK_INTELLIGENCE_EVALUATION, BB01): a calculation can be arithmetically perfect and
still be wrong because its inputs are bound to the wrong thing (every task duration bound to the same "9週" -> "36 weeks" stamped
"工具驗算"). Four SEPARATE verification levels are therefore reported and never conflated:
  L1 presence   - the number really occurs in a source (ledger quantity found by id or by value)
  L2 binding    - the number is bound to the right entity/attribute/unit: id exists, dimension matches the declared unit, the declared meaning
                  overlaps the quantity's own label/context, and ONE quantity is not reused for several differently-meant variables
  L3 arithmetic - the formula is recomputed by a safe evaluator (model-stated results are ignored)
  L4 professional validity - NEVER granted by this module except for a registered deterministic method (critical_path); otherwise
                  the result carries 'professional_validity: not_validated'.
A result whose binding fails is REJECTED (value withheld), not merely tagged.
"""
from __future__ import annotations
import ast, math, re
from decimal import Decimal

_FN = {'exp': math.exp, 'log': math.log, 'sqrt': math.sqrt, 'min': min, 'max': max, 'sum': sum, 'round': round, 'ceil': math.ceil, 'floor': math.floor, 'abs': abs}


def safe_eval(expr, env):
    """Arithmetic only. Evaluates ONLY the selected operator (an earlier prototype computed every operator eagerly, so `100 * 80000`
    also evaluated `100 ** 80000` and failed with 'Result too large' -- the BB07 root cause)."""
    def ev(n):
        if isinstance(n, ast.Expression): return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool): return n.value
        if isinstance(n, ast.Name):
            if n.id in env and env[n.id] is not None: return env[n.id]
            raise ValueError('unbound variable ' + n.id)
        if isinstance(n, ast.BinOp):
            l, r = ev(n.left), ev(n.right); op = type(n.op)
            if op is ast.Add: return l + r
            if op is ast.Sub: return l - r
            if op is ast.Mult: return l * r
            if op is ast.Div:
                if r == 0: raise ValueError('division by zero')
                return l / r
            if op is ast.Pow:
                if abs(r) > 100 or (abs(l) > 1 and abs(r) * math.log10(abs(l)) > 30): raise ValueError('power out of safe range')
                return l ** r
            raise ValueError('disallowed operator')
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)): return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FN and not n.keywords: return _FN[n.func.id](*[ev(x) for x in n.args])
        if isinstance(n, (ast.List, ast.Tuple)): return [ev(x) for x in n.elts]
        raise ValueError('disallowed expression')
    return ev(ast.parse(str(expr).replace('^', '**').replace('×', '*').replace('÷', '/'), mode='eval'))


def _grams(t): t = re.sub(r'\s+', '', str(t or '')); return {t[i:i + 2] for i in range(len(t) - 1)} | ({t} if len(t) == 1 else set())
_DIM = {'週': 'time', '周': 'time', '天': 'time', '日': 'time', '月': 'time', '個月': 'time', '年': 'time', '元': 'money', '萬元': 'money', '%': 'percent',
        '件': 'count', '人': 'count', '個': 'count', 'V': 'voltage', 'A': 'current', 'W': 'power', '小時': 'hour', 'h': 'hour', '分鐘': 'minute', '°C': 'temp'}
_TIME_DAYS = {'週': 7, '周': 7, '天': 1, '日': 1, '月': 30, '個月': 30, '年': 365}


def _resolve(ref, ledger):
    """-> (list of candidate ledger quantities, how) ; ref is 'Q3' (id), or a literal number/string looked up by value."""
    items = getattr(ledger, 'all_items', ledger.items); ids = {f'Q{i}': q for i, q in enumerate(items, 1)}
    if isinstance(ref, dict): ref = ref.get('ref')
    if isinstance(ref, str) and ref in ids: return [ids[ref]], 'id'
    if isinstance(ref, str) and hasattr(ledger, 'by_ref') and ledger.by_ref(ref): return [ledger.by_ref(ref)], 'ref'
    try: v = Decimal(str(ref).replace(',', ''))
    except Exception: return [], 'unresolvable'
    hits = [q for q in items if Decimal(q['value'].replace(',', '')) == v or Decimal(q['canonical']) == v]
    return hits, ('value' if hits else 'none')


def _numeric(q, declared_unit):
    """Elementary numeric value of a ledger quantity. 萬/萬元/億 always expand to the elementary number; time converts to declared unit if same dimension."""
    if q['dimension'] in ('money', 'amount_wan'): return float(Decimal(q['canonical']))
    if q['dimension'] == 'time' and declared_unit in _TIME_DAYS and q['unit'] in _TIME_DAYS:
        return float(Decimal(q['value'].replace(',', '')) * _TIME_DAYS[q['unit']] / _TIME_DAYS[declared_unit])
    return float(Decimal(q['value'].replace(',', '')))


def verify_calculation(calc, ledger, results=None):
    """calc: {'name','formula','inputs':{var: 'Q3' | 12 | {'ref':'Q3','meaning':'任務B後端工期','unit':'週'}},'unit','meaning'}.
    Returns dict(status, levels{presence,binding,arithmetic,professional_validity}, issues[], value|None, inputs[])."""
    issues, env, rows = [], {}, []
    presence = True; binding_ok = True; assumed = False
    used_by_q = {}
    results = results or {}
    for var, spec in (calc.get('inputs') or {}).items():
        # chained input: the VERIFIED result of an earlier calculation (never an unverified one) / explicit assumption (always flagged, never "verified")
        if isinstance(spec, dict) and spec.get('from_calc') is not None:
            prev = results.get(spec['from_calc'])
            if prev is None: binding_ok = False; issues.append(f"{var}: prior result '{spec['from_calc']}' is missing or was itself not verified")
            else: env[var] = float(prev); rows.append({'var': var, 'grounded': True, 'from_calc': spec['from_calc'], 'used_value': float(prev)})
            continue
        if isinstance(spec, dict) and spec.get('assume') is not None:
            assumed = True; presence = False; issues.append(f"{var}: explicit assumption {spec['assume']} ({spec.get('meaning', '')}) -- not from a source")
            try: env[var] = float(spec['assume'])
            except (TypeError, ValueError): env[var] = None
            rows.append({'var': var, 'grounded': False, 'assumed': True}); continue
        meaning = spec.get('meaning') if isinstance(spec, dict) else None
        dunit = spec.get('unit') if isinstance(spec, dict) else None
        hits, how = _resolve(spec, ledger)
        if not hits:
            presence = False; assumed = True; issues.append(f'{var}: no source quantity (assumed input, not grounded)')
            try: env[var] = float(str((spec.get('ref') if isinstance(spec, dict) else spec)).replace(',', ''))
            except ValueError: env[var] = None
            rows.append({'var': var, 'grounded': False}); continue
        q = hits[0]
        if len(hits) > 1:
            binding_ok = False; issues.append(f'{var}: ambiguous binding, value matches {len(hits)} source quantities ({", ".join(sorted({h["source_id"] + ":" + h["label"] for h in hits}))})')
        if q['dimension'] == 'bare' and dunit: issues.append(f'{var}: source states no unit; declared unit {dunit} is the model\'s assumption')
        if dunit and dunit in _DIM and q['dimension'] != 'bare' and _DIM[dunit] != q['dimension'] and not ({_DIM[dunit], q['dimension']} <= {'money', 'amount_wan', 'count'}):
            binding_ok = False; issues.append(f'{var}: declared unit {dunit} ({_DIM[dunit]}) conflicts with source {q["value"]}{q["unit"]} ({q["dimension"]})')
        if meaning and (_grams(meaning) & (_grams(q['label']) | _grams(q['context']))) == set():
            binding_ok = False; issues.append(f'{var}: declared meaning "{meaning}" does not match the source label/context "{q["label"]}｜{q["context"]}"')
        used_by_q.setdefault((q['source_id'], q['span']), []).append((var, (meaning or '').strip()))
        env[var] = _numeric(q, dunit)
        rows.append({'var': var, 'qid': f"Q{getattr(ledger, 'all_items', ledger.items).index(q) + 1}", 'unit_inferred': bool(q.get('unit_inferred')), 'source': q['source_id'], 'stated': q['value'] + q['unit'], 'used_value': env[var], 'how_resolved': how, 'grounded': True})
    for k, uses in used_by_q.items():
        ms = {m for _, m in uses}
        if len(uses) > 1 and (len(ms) != 1 or '' in ms):   # reuse is allowed only when every use declares the SAME non-empty meaning
            binding_ok = False; issues.append('one source quantity bound to %d different variables (%s) without an identical declared meaning -- inputs of different items must come from different sources' % (len(uses), ', '.join(v for v, _ in uses)))
    value, arithmetic = None, False
    try: value = safe_eval(calc.get('formula', ''), env); arithmetic = True
    except Exception as e: issues.append('arithmetic: ' + str(e))
    if not presence and not binding_ok: status = 'REJECTED_BINDING'
    elif not binding_ok: status = 'REJECTED_BINDING'
    elif not arithmetic: status = 'ARITHMETIC_FAILED'
    elif assumed: status = 'UNVERIFIED_ASSUMED_INPUT'
    else: status = 'INPUTS_BOUND_AND_ARITHMETIC_CHECKED'
    return {'status': status, 'levels': {'presence': presence, 'binding': binding_ok and presence, 'arithmetic': arithmetic, 'professional_validity': 'not_validated'},
            'issues': issues, 'value': value if status in ('INPUTS_BOUND_AND_ARITHMETIC_CHECKED', 'UNVERIFIED_ASSUMED_INPUT') else None, 'inputs': rows}


def critical_path(tasks):
    """Deterministic scheduling method (professional-validity eligible): tasks=[{'id','duration':number,'after':[ids]}]. Returns
    total duration, critical path (ids) and float per task. Raises ValueError on cycles/unknown predecessors. Durations are NOT summed blindly."""
    byid = {t['id']: t for t in tasks}
    if len(byid) != len(tasks): raise ValueError('duplicate task id')
    es, ef, order, state = {}, {}, [], {}
    def visit(i):
        if state.get(i) == 1: raise ValueError('cycle at ' + i)
        if state.get(i) == 2: return
        state[i] = 1
        for p in byid[i].get('after', []):
            if p not in byid: raise ValueError('unknown predecessor ' + p)
            visit(p)
        state[i] = 2; order.append(i)
    for i in byid: visit(i)
    for i in order:
        es[i] = max([ef[p] for p in byid[i].get('after', [])] or [0]); ef[i] = es[i] + float(byid[i]['duration'])
    total = max(ef.values()); lf, ls = {}, {}
    for i in reversed(order):
        succ = [j for j in byid if i in byid[j].get('after', [])]
        lf[i] = min([ls[j] for j in succ] or [total]); ls[i] = lf[i] - float(byid[i]['duration'])
    flt = {i: round(ls[i] - es[i], 9) for i in byid}
    path, cur = [], [i for i in byid if ef[i] == total and flt[i] == 0][:1]
    while cur:
        path.append(cur[0]); preds = [p for p in byid[cur[0]].get('after', []) if flt[p] == 0 and ef[p] == es[cur[0]]]; cur = preds[:1]
    # THREE separate validity layers (never merged): (1) METHOD -- the algorithm is unit-tested and recomputed deterministically; (2) INPUT -- whether each
    # duration/dependency is bound to its source is decided by the CALLER (verify_calculation per duration) and is NOT implied here; (3) CONCLUSION -- whether the
    # schedule decision is professionally valid is never granted: the result only holds while the listed assumptions hold.
    return {'total': total, 'critical_path': list(reversed(path)), 'float': flt,
            'method_validity': 'algorithm_checked',
            'input_validity': 'caller_must_verify_each_duration_and_dependency',
            'conclusion_validity': 'not_validated',
            'professional_validity': 'not_validated',
            'assumptions': ['durations are single-point estimates (no uncertainty)', 'dependency list is complete and correct', 'finish-to-start only, no lags/overlaps',
                            'resources are not constrained (no resource levelling)']}
