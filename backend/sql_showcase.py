"""Shared full-population SQL execution and independent sample logic checks."""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / 'frontend/public/sql'
PARAMETERS = {'as_of': '2025-11-30', 'claims_start': '2024-11-01',
              'claims_end': '2025-12-01', 'minimum_peers': 2}
CASES = [
    ('regional_premiums', 'Do premiums differ by state within the same plan and coverage tier?',
     ['Preaggregation', 'SUM OVER', 'Weighted means', 'DENSE_RANK'], 'Enrollment'),
    ('housing_premiums', 'Do linked premiums differ by recorded housing insecurity within comparable coverage?',
     ['CTEs', 'Conditional aggregation', 'Common cell weights', 'NULLIF'], 'Member'),
    ('conditions_costs', 'How do linked premiums and claim spending vary with diagnosed conditions?',
     ['Preaggregation', 'COUNT DISTINCT', 'LEFT JOIN', 'COALESCE'], 'Member'),
]
ELIGIBLE = 'e.start_date <= :as_of AND (e.end_date IS NULL OR e.end_date >= :as_of) AND e.premium IS NOT NULL AND e.premium >= 0'


def full_showcase(read, table_counts, source, engine_name, mysql_verified, parameters=None):
    parameters = dict(parameters or PARAMETERS)
    cases = []
    for key, question, techniques, grain in CASES:
        sql = (SQL_DIR / f'{key}.sql').read_text()
        cases.append({'id': key, 'question': question, 'techniques': techniques, 'grain': grain,
                      'sql': sql, 'sha256': hashlib.sha256(sql.encode()).hexdigest(), 'rows': read(sql, parameters)})
    eligible_enrollments = read(f'SELECT COUNT(*) AS n FROM ENROLLMENT e WHERE {ELIGIBLE}', parameters)[0]['n']
    eligible_members = read(f'SELECT COUNT(*) AS n FROM MEMBERS m JOIN ENROLLMENT e ON e.Enrollment_ID = m.Enrollment_ID WHERE {ELIGIBLE}', parameters)[0]['n']
    direct_claims = read(f'''SELECT COUNT(*) AS claims, COALESCE(SUM(c.amount), 0) AS amount
        FROM CLAIMS c JOIN MEMBERS m ON m.member_id = c.member_id
        JOIN ENROLLMENT e ON e.Enrollment_ID = m.Enrollment_ID
        WHERE {ELIGIBLE} AND c.date >= :claims_start AND c.date < :claims_end''', parameters)[0]
    condition_rows = cases[2]['rows']
    assert sum(r['members'] for r in condition_rows) == eligible_members
    assert sum(r['claims'] for r in condition_rows) == direct_claims['claims']
    assert abs(sum(float(r['total_claim_amount']) for r in condition_rows) - float(direct_claims['amount'])) < 0.1
    regional = cases[0]['rows']
    regional_n = sum(Decimal(str(r['enrollments'])) for r in regional)
    assert regional_n <= eligible_enrollments
    if regional_n:
        weighted_index = sum(Decimal(str(r['premium_index'])) * Decimal(str(r['enrollments'])) for r in regional) / regional_n
        assert abs(weighted_index - Decimal('100')) <= Decimal('0.011')
    housing = cases[1]['rows'][0]
    assert housing['yes_members'] + housing['no_members'] <= eligible_members
    assert housing['overlap_weight'] <= min(housing['yes_members'], housing['no_members'])
    return {'parameters': parameters, 'cases': cases, 'scope': 'full', 'source': source,
            'engine': engine_name, 'target_dialect': 'MySQL 8', 'mysql_verified': mysql_verified,
            'total_members': table_counts['MEMBERS'], 'table_counts': table_counts,
            'eligible_members': eligible_members, 'eligible_enrollments': eligible_enrollments,
            'validation': 'Full-result member counts and claim totals reconcile with direct joins; regional indices reconcile to 100. SQL logic is independently checked on the connected sample and boundary fixtures.',
            'generated_at': datetime.now(timezone.utc).isoformat()}


def sample_database(sample):
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    definitions = {
        'MEMBERS': 'member_id INTEGER PRIMARY KEY, Enrollment_ID INTEGER, housing_insecurity INTEGER',
        'ENROLLMENT': 'Enrollment_ID INTEGER PRIMARY KEY, state TEXT, plan_id INTEGER, Coverage_tier TEXT, premium NUMERIC, start_date TEXT, end_date TEXT',
        'CLAIMS': 'claim_id INTEGER PRIMARY KEY, member_id INTEGER, amount NUMERIC, date TEXT',
        'MEMBER_CONDITION': 'Member_ID INTEGER, Condition_ID INTEGER, Diagnostic_date TEXT, PRIMARY KEY (Member_ID, Condition_ID, Diagnostic_date)',
    }
    for table, definition in definitions.items():
        connection.execute(f'CREATE TABLE {table} ({definition})')
        columns = [row['name'] for row in connection.execute(f'PRAGMA table_info({table})')]
        placeholders = ','.join('?' for _ in columns)
        connection.executemany(f'INSERT INTO {table} VALUES ({placeholders})',
                               [tuple(row[column] for column in columns) for row in sample[table]])
    return connection


def independent_results(sample, parameters):
    eligible = {e['Enrollment_ID']: e for e in sample['ENROLLMENT']
                if e['start_date'] <= parameters['as_of']
                and (e['end_date'] is None or e['end_date'] >= parameters['as_of'])
                and e['premium'] is not None and e['premium'] >= 0}
    peers = defaultdict(list)
    for e in eligible.values():
        peers[(e['plan_id'], e['Coverage_tier'])].append(e)
    states = defaultdict(list)
    for cell in peers.values():
        mean = sum(e['premium'] for e in cell) / len(cell)
        if len(cell) >= parameters['minimum_peers'] and mean > 0:
            for e in cell:
                states[e['state']].append((e['premium'], 100 * e['premium'] / mean))
    regional = [{'state': state, 'enrollments': len(rows),
                 'average_premium': round(sum(x[0] for x in rows) / len(rows), 2),
                 'premium_index': round(sum(x[1] for x in rows) / len(rows), 2)}
                for state, rows in states.items()]
    regional.sort(key=lambda row: (-row['premium_index'], row['state']))
    ranks = {value: i + 1 for i, value in enumerate(sorted({r['premium_index'] for r in regional}, reverse=True))}
    for row in regional:
        row['index_rank'] = ranks[row['premium_index']]
    members = [(m, eligible[m['Enrollment_ID']]) for m in sample['MEMBERS'] if m['Enrollment_ID'] in eligible]
    cells = defaultdict(lambda: {0: [], 1: []})
    for m, e in members:
        if m['housing_insecurity'] in (0, 1):
            cells[(e['plan_id'], e['Coverage_tier'])][m['housing_insecurity']].append(e['premium'])
    matched = [groups for groups in cells.values() if groups[0] and groups[1]]
    weight = sum(min(len(g[0]), len(g[1])) for g in matched)
    means = {flag: sum(min(len(g[0]), len(g[1])) * sum(g[flag]) / len(g[flag]) for g in matched) / weight if weight else None for flag in (0, 1)}
    gap = means[1] - means[0] if weight else None
    housing = [{'matched_cells': len(matched), 'yes_members': sum(len(g[1]) for g in matched),
                'no_members': sum(len(g[0]) for g in matched), 'overlap_weight': weight,
                'yes_premium': round(means[1], 2) if weight else None,
                'no_premium': round(means[0], 2) if weight else None,
                'premium_difference': round(gap, 2) if gap is not None else None,
                'difference_pct': round(100 * gap / means[0], 2) if weight and means[0] else None}]
    diagnoses = defaultdict(set)
    for d in sample['MEMBER_CONDITION']:
        if d['Diagnostic_date'] <= parameters['as_of']:
            diagnoses[d['Member_ID']].add(d['Condition_ID'])
    claims = defaultdict(list)
    for c in sample['CLAIMS']:
        if parameters['claims_start'] <= c['date'] < parameters['claims_end']:
            claims[c['member_id']].append(c['amount'])
    groups = defaultdict(list)
    for m, e in members:
        groups[min(len(diagnoses[m['member_id']]), 3)].append((e['premium'], claims[m['member_id']]))
    conditions = []
    for n, rows in sorted(groups.items()):
        total = sum(sum(amounts) for _, amounts in rows)
        conditions.append({'conditions': str(n) if n < 3 else '3+', 'members': len(rows),
                           'members_with_claims': sum(bool(amounts) for _, amounts in rows),
                           'claims': sum(len(amounts) for _, amounts in rows),
                           'total_claim_amount': round(total, 2),
                           'average_claim_amount': round(total / len(rows), 2),
                           'average_premium': round(sum(p for p, _ in rows) / len(rows), 2)})
    return {'regional_premiums': regional, 'housing_premiums': housing, 'conditions_costs': conditions}, len(eligible), len(members)


def check_rows(actual, expected):
    assert len(actual) == len(expected), 'Output row counts differ.'
    for a, b in zip(actual, expected):
        assert a.keys() == b.keys()
        for key in a:
            if isinstance(a[key], (float, int)) and isinstance(b[key], (float, int)):
                assert abs(a[key] - b[key]) <= 0.011, f'Different result for {key}: {a[key]} / {b[key]}'
            else:
                assert a[key] == b[key], f'Different result for {key}'


def build_showcase(sample, parameters=None):
    parameters = dict(parameters or PARAMETERS)
    expected, eligible_enrollments, eligible_members = independent_results(sample, parameters)
    cases = []
    with sample_database(sample) as connection:
        for key, question, techniques, grain in CASES:
            sql = (SQL_DIR / f'{key}.sql').read_text()
            rows = [dict(row) for row in connection.execute(sql, parameters)]
            check_rows(rows, expected[key])
            cases.append({'id': key, 'question': question, 'techniques': techniques, 'grain': grain,
                          'sql': sql, 'sha256': hashlib.sha256(sql.encode()).hexdigest(), 'rows': rows})
    return {'parameters': parameters, 'cases': cases, 'source': 'Connected synthetic demo sample',
            'engine': f'SQLite {sqlite3.sqlite_version}', 'target_dialect': 'MySQL 8',
            'mysql_verified': False, 'sample_members': len(sample['MEMBERS']),
            'eligible_members': eligible_members, 'eligible_enrollments': eligible_enrollments,
            'validation': 'Every result independently recomputed from source records in Python.',
            'generated_at': datetime.now(timezone.utc).isoformat()}


def enrich_demo():
    from export_full_sql import export_full
    export_full()


if __name__ == '__main__':
    enrich_demo()
