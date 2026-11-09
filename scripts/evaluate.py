"""Fixed synthetic evaluation (12 hand-annotated reference cases, not real-world data)."""
from __future__ import annotations
import json
from pathlib import Path
from app.db import init_db
from app.impact import trace_impact,direct_links
from app.engineering import power_continuous

GOLD = Path(__file__).resolve().parents[1]/'data'/'evaluation_cases.json'

def prefixes(terminals):
    return {tuple(path[:i]) for path in terminals for i in range(2,len(path)+1)}

def stats(true_set,predicted):
    tp=len(true_set & predicted)
    return {'true_positive':tp,'predicted':len(predicted),'reference':len(true_set),
            'recall':round(tp/len(true_set),4) if true_set else (1.0 if not predicted else 0.0),
            'precision':round(tp/len(predicted),4) if predicted else (1.0 if not true_set else 0.0)}

def evaluate(conn):
    cases=json.loads(GOLD.read_text(encoding='utf-8'))
    output=[]
    for row in cases:
        gold=prefixes(row['reference_terminal_paths'])
        actual={tuple(p['nodes']) for p in trace_impact(conn,'manager','demo-chamber',row['root'])['paths']}
        before={tuple((row['root'],link['to'])) for link in direct_links(conn,'manager','demo-chamber',row['root'])['links']}
        entry={'case':row['id'],'topic':row['topic'],'baseline_direct_only':stats(gold,before),
               'multi_hop':stats(gold,actual)}
        if 'expected_constraint' in row:
            entry['constraint_correct']=power_continuous(conn,'manager','demo-chamber')['status']==row['expected_constraint']
        output.append(entry)
    aggregate={}
    for key in ('baseline_direct_only','multi_hop'):
        tp=sum(r[key]['true_positive'] for r in output)
        ref=sum(r[key]['reference'] for r in output)
        pred=sum(r[key]['predicted'] for r in output)
        aggregate[key]={'path_recall':round(tp/ref,4) if ref else None,
                        'path_precision':round(tp/pred,4) if pred else None,
                        'true_positive':tp,'reference':ref,'predicted':pred}
    return {'scope':'synthetic reference graph only','cases':output,'aggregate':aggregate,
            'warning':'此成績測試已人工建立的合成依賴；不可推論真實工程推演、LLM 判斷或商業效益。'}

if __name__=='__main__':
    c=init_db()
    try:
        print(json.dumps(evaluate(c),ensure_ascii=False,indent=2))
    finally:
        c.close()
