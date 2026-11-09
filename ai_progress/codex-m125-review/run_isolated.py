"""Reproducible source snapshot or current-disk run; no production/network access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', choices=('baseline', 'completed', 'current'), default='completed')
parser.add_argument('--output', default='completed-results')
parser.add_argument('--only', help='Run one named independent case without repeating passing regressions')
args = parser.parse_args()
SOURCE = ROOT if args.source == 'current' else HERE / (args.source + '_source')
OUT = HERE / args.output
assert OUT.resolve().is_relative_to(HERE)
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(SOURCE))
sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['M125_OUTPUT'] = str(OUT)
box = tempfile.TemporaryDirectory(prefix='riskscope-m125-')
BASE = Path(box.name).resolve()
os.environ['AGENT_DB_PATH'] = str(BASE / 'default.sqlite3')
os.environ['AGENT_CREDENTIALS_PATH'] = str(BASE / 'credentials.json')
os.environ['OLLAMA_URL'] = ''

def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (root / 'app').glob('*.py')}

before = hashes(SOURCE)
db_paths, blocked = set(), []

def guard(event, values):
    if event == 'sqlite3.connect':
        path = Path(str(values[0])).resolve()
        if not path.is_relative_to(BASE):
            blocked.append('sqlite_outside_isolation')
            raise RuntimeError('Database outside isolated fixture')
        db_paths.add(str(path.relative_to(BASE)))
    if event == 'open' and isinstance(values[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(values[0])).resolve()
        if path.is_relative_to(ROOT / 'runtime') or path.is_relative_to(ROOT / 'ai_progress/backups'):
            blocked.append('production_data_access')
            raise RuntimeError('Production data access forbidden')
    if event == 'socket.connect' and isinstance(values[1], tuple):
        blocked.append('network_connect')
        raise RuntimeError('Real network forbidden')

sys.addaudithook(guard)
import pytest

regressions = [
    'test_llm_value_grounding.py::test_a_fabricated_values_with_no_numbers_in_message_are_rejected',
    'test_llm_value_grounding.py::test_e_formal_document_value_is_never_overridden_by_user_supplied',
    'test_llm_approval_linkage.py::test_approved_action_a_does_not_leak_into_discussion_of_unapproved_action_b',
    'test_llm_approval_linkage.py::test_m7_safety_and_numeric_fallback_still_work_unchanged',
    'test_session_continuity.py::test_session_transcript_redacts_reply_after_source_revocation',
    'test_session_continuity.py::test_approval_pipeline_unreachable_from_analyze_or_session',
    'test_m114_condition_updates.py::test_llm_cannot_omit_the_failed_change_warning',
]
reference = SOURCE / 'tests/test_m125_supply_capacity_semantics.py'
if reference.exists():
    regressions.append('test_m125_supply_capacity_semantics.py')
selected = [str(HERE / 'review_probes.py') + ('::' + args.only if args.only else '')]
if not args.only:
    selected += [str(SOURCE / 'tests' / test) for test in regressions]
code = pytest.main(['-q', '--tb=short', '-p', 'no:cacheprovider',
    '--basetemp', str(BASE / 'pytest'), '--junitxml', str(OUT / 'results.xml'),
    *selected])
after = hashes(SOURCE)
result = {'source': args.source, 'exit_code': int(code), 'source_unchanged_during_run': before == after,
          'source_hashes_before': before, 'source_hashes_after': after,
          'temporary_databases': len(db_paths), 'blocked_access_attempts': blocked,
          'real_llm_calls': 0, 'tests': selected}
(OUT / 'isolation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if not k.startswith('source_hashes')}, ensure_ascii=False))
sys.exit(code)
