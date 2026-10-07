"""Attach a checked historical benchmark to the public demo."""
import hashlib
import json
from pathlib import Path

from benchmark_mysql import result_signature
from performance_evidence import REPORT, OPTIMIZATION_REPORT, COVERING_REPORT, ACTIVATION_REPORT, load_evidence
from sql_showcase import CASES, SQL_DIR
from sqlalchemy import text
from sqlalchemy.dialects.mysql import dialect

ROOT = Path(__file__).resolve().parents[1]


def publish():
    report = load_evidence()
    path = ROOT / 'frontend/public/demo/snapshot.json'
    snapshot = json.loads(path.read_text())
    counts = {row['name']: row['row_count'] for row in snapshot['overview']['tables']}
    if report['table_counts'] != counts:
        raise ValueError('Benchmark and saved dashboard cover different record counts.')
    showcase = snapshot['sql_showcase']
    if report['parameters'] != showcase['parameters']:
        raise ValueError('Benchmark and saved dashboard use different periods.')
    measured = {row['query']: row for row in report['results']}
    optimization = report.get('optimization')
    regional = next((r for r in optimization['results'] if r['candidate_name'] == 'regional_grouped'), None) if optimization else None
    verifications = {}
    for case in showcase['cases']:
        current_sql = (SQL_DIR / f"{case['id']}.sql").read_text()
        signature = result_signature(case['rows'])
        if case['id'] == 'regional_premiums' and regional and current_sql == regional['candidate']['sql']:
            before = regional['baseline']['repeated_uncached_ms']
            after = regional['candidate']['repeated_uncached_ms']
            if signature != regional['result_sha256'] or max(after) >= min(before):
                raise ValueError('Regional rewrite lacks consistent speed or result evidence.')
            case['sql'] = current_sql
            case['sha256'] = hashlib.sha256(current_sql.encode()).hexdigest()
            case['techniques'] = next(c[2] for c in CASES if c[0] == case['id'])
            verifications[case['id']] = {'measured_at': optimization['measured_at'],
                'sql_sha256': case['sha256'], 'result_sha256': signature,
                'report': 'benchmarks/mysql-optimization.json'}
            continue
        sql = str(text(case['sql']).compile(dialect=dialect(paramstyle='pyformat')))
        row = measured[case['id']]
        if current_sql != case['sql'] or sql != row['sql'] or signature != row['result_sha256']:
            raise ValueError('Saved premium results do not match the measured MySQL query.')
        verifications[case['id']] = {'measured_at': report['measured_at'], 'sql_sha256': case['sha256'],
                                    'result_sha256': signature, 'report': 'benchmarks/mysql-performance.json'}
        activation = report.get('covering_activation') if case['id'] == 'conditions_costs' else None
        if activation:
            if current_sql != activation['sql'] or signature != activation['result_sha256']:
                raise ValueError('Activation differs from the saved conditions results.')
            verifications[case['id']] = {'measured_at': activation['measured_at'], 'sql_sha256': case['sha256'],
                'result_sha256': signature, 'report': 'benchmarks/mysql-covering-index-applied.json'}
    showcase['mysql_verified'] = True
    showcase['mysql_verification'] = {
        'measured_at': report['measured_at'], 'mysql_version': report['mysql_version'],
        'report_sha256': hashlib.sha256(REPORT.read_bytes()).hexdigest(),
        'scope': 'All three SELECT result checksums match the saved full-source results. Original generation engine and date are preserved.',
        'queries': verifications,
    }
    snapshot['performance'] = report
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot, indent=2))
    temporary.replace(path)
    output = ROOT / 'frontend/public/benchmarks/mysql-performance.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    if optimization:
        output.with_name('mysql-optimization.json').write_bytes(OPTIMIZATION_REPORT.read_bytes())
    if report.get('covering_trial'):
        output.with_name('mysql-covering-index.json').write_bytes(COVERING_REPORT.read_bytes())
    if report.get('covering_activation'):
        output.with_name('mysql-covering-index-applied.json').write_bytes(ACTIVATION_REPORT.read_bytes())
    print('Saved MySQL timings validated; all three premium result checksums match.')


if __name__ == '__main__':
    publish()
