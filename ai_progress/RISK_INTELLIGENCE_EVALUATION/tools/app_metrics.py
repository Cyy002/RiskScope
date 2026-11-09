"""Integrated-app acceptance metrics (claude-b). usage: python tools/app_metrics.py <run_dir>... ; reads result + _judge.json per dir.
Per run: mean score, critical-case count, REQUIRED-CALCULATION completion (rubric derived numbers present in the final reply), template-fallback count (reply_source=deterministic_template),
'missing-information framing' count (reply opens with the old "目前仍缺少以下資訊" frame), M7-rejection count, injection safety (BB10 must not approve), mean model calls per turn."""
import json, glob, os, sys, re, statistics as st
for d in sys.argv[1:]:
    try: j = {x['id']: x for x in json.load(open(f'runs/{d}/_judge.json'))}
    except Exception: print(d, 'no judge file'); continue
    rows = []
    for f in sorted(glob.glob(f'runs/{d}/BB*.result.json')):
        r = json.load(open(f)); t = r['turns'][-1]; c = json.load(open(f"BENCHMARK_CASES/dev/{r['id']}.json"))
        need = [n for n in c['rubric'].get('required_numbers', [])]; given = (c.get('question') or '') + ' '.join(c.get('turns') or []) + ' '.join(x['body'] for x in c.get('documents', []))
        need = [n for n in need if n not in given]; reply = t.get('reply') or ''
        rows.append({'id': r['id'], 'score': j[r['id']]['total_100'], 'crit': bool(j[r['id']].get('judge_critical')), 'calc_done': (sum(n in reply for n in need) / len(need)) if need else None,
                     'template': t.get('reply_source') == 'deterministic_template', 'frame': reply.lstrip().startswith('目前仍缺少以下資訊') or '本焦點沒有預先驗證' in reply,
                     'm7_rej': (t.get('m7_verdict') or {}).get('accepted') is False,
                     'm7_all': sum((u.get('m7_verdict') or {}).get('accepted') is False for u in r['turns']), 'tmpl_all': sum(u.get('reply_source') == 'deterministic_template' for u in r['turns']), 'calls': len(t.get('llm_calls') or [])})
    cd = [x['calc_done'] for x in rows if x['calc_done'] is not None]
    bb10 = next((x['score'] for x in rows if x['id'] == 'BB10'), None)
    print(f"{d}: mean {st.mean(x['score'] for x in rows):.1f} | critical cases {sum(x['crit'] for x in rows)}/{len(rows)} | required-calc completion {st.mean(cd):.2f} ({len(cd)} cases) | template fallbacks {sum(x['template'] for x in rows)} | 'missing-info' frame {sum(x['frame'] for x in rows)} | M7 rejections (final turn) {sum(x['m7_rej'] for x in rows)} | M7 rejections (ALL turns) {sum(x['m7_all'] for x in rows)} | template turns (ALL turns) {sum(x['tmpl_all'] for x in rows)} | BB10 {bb10} | calls/turn {st.mean(x['calls'] for x in rows):.1f}")
