"""Reconcile the real MySQL sample API results with independent Python logic."""
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from database import engine
from explorer import overview, premium_equity
from sql_showcase import PARAMETERS, independent_results, check_rows


def check():
    if engine.url.database != 'healthpulse_sample':
        raise ValueError('This check requires the isolated sample database.')
    snapshot = json.loads((ROOT / 'frontend/public/demo/snapshot.json').read_text())
    summary = overview(date.fromisoformat(PARAMETERS['as_of']))
    counts = {row['name']: row['row_count'] for row in summary['tables']}
    assert counts == {name: len(rows) for name, rows in snapshot['sample'].items()}
    expected, enrollment_count, member_count = independent_results(snapshot['sample'], PARAMETERS)
    result = premium_equity(date.fromisoformat(PARAMETERS['as_of']), date.fromisoformat(PARAMETERS['claims_start']),
                            date.fromisoformat(PARAMETERS['claims_end']), PARAMETERS['minimum_peers'])['sql_showcase']
    assert result['eligible_enrollments'] == enrollment_count
    assert result['eligible_members'] == member_count
    for case in result['cases']:
        check_rows(case['rows'], expected[case['id']])
    print('All eight sample table counts and all three MySQL premium results reconcile with independent sample logic.')


if __name__ == '__main__':
    check()
