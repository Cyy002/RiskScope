"""Repeat-aware comparison (claude-b). usage: python tools/compare_runs.py 'A1=dirA,dirB' 'D=dirC,dirD,dirE' ... Reports run means/SD, per-case spread, per-case pass rate (>=80), judge-listed critical counts and a run-level permutation test for every pair.
Rule: a difference is only reported as an effect if it exceeds the within-arm run SD AND the permutation p < 0.1; otherwise 'not distinguishable'."""
import json, sys, statistics as st, random, itertools
IDS = 'BB01,BB02,BB04,BB05,BB06,BB07,BB10,BB11,BB13,BB14,BB16,BB23'.split(',')
arms = {}
for a in sys.argv[1:]:
    n, ds = a.split('='); runs = []
    for d in ds.split(','):
        try: runs.append({x['id']: x for x in json.load(open(f'runs/{d}/_judge.json'))})
        except Exception: print('missing judge for', d)
    arms[n] = runs
def means(rs): return [st.mean(r[i]['total_100'] for i in IDS if i in r) for r in rs]
for n, rs in arms.items():
    m = means(rs); pr = {i: sum(r[i]['total_100'] >= 80 for r in rs if i in r) / len(rs) for i in IDS}
    print(f"{n}: runs={[round(x,1) for x in m]} mean={st.mean(m):.1f} sd={(st.stdev(m) if len(m)>1 else float('nan')):.1f} | critical/run={[sum(1 for i in IDS if r.get(i,{}).get('judge_critical')) for r in rs]}")
    print('   per-case pass-rate(>=80):', {i: round(v, 2) for i, v in pr.items()})
random.seed(1)
for (a, ra), (b, rb) in itertools.combinations(arms.items(), 2):
    ma, mb = means(ra), means(rb); obs = st.mean(ma) - st.mean(mb); pool = ma + mb; c = 0
    for _ in range(20000):
        random.shuffle(pool); c += abs(st.mean(pool[:len(ma)]) - st.mean(pool[len(ma):])) >= abs(obs)
    sd = max([st.stdev(x) for x in (ma, mb) if len(x) > 1] or [0]); p = c / 20000
    print(f"{a} - {b}: diff {obs:+.1f} (p={p:.2f}, within-arm SD {sd:.1f}) -> {'EFFECT' if abs(obs) > sd and p < 0.1 else 'not distinguishable'}")
