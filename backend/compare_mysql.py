"""Compare candidate SELECTs with current queries before adopting a rewrite."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from benchmark_mysql import result_signature
from performance_evidence import load_report
from sql_showcase import PARAMETERS, SQL_DIR

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'benchmarks/mysql-optimization.json'


def candidates():
    conditions = (SQL_DIR / 'conditions_costs.sql').read_text()
    return [
        ('regional_grouped', 'regional_premiums', (ROOT / 'sql_candidates/regional_grouped.sql').read_text()),
        ('conditions_primary_diagnoses', 'conditions_costs', conditions.replace(
            'FROM MEMBER_CONDITION\n', 'FROM MEMBER_CONDITION USE INDEX (PRIMARY)\n')),
        ('conditions_primary_scans', 'conditions_costs', conditions.replace(
            'FROM MEMBER_CONDITION\n', 'FROM MEMBER_CONDITION USE INDEX (PRIMARY)\n').replace(
            'FROM CLAIMS\n', 'FROM CLAIMS USE INDEX (PRIMARY)\n')),
    ]


def compare(connection, baseline, candidate, parameters, repeats=3, clock=perf_counter_ns):
    if not 3 <= repeats <= 20:
        raise ValueError('Repeat count must be from 3 to 20.')
    queries = {'baseline': baseline, 'candidate': candidate}
    readings = {key: [] for key in queries}
    signatures = set()
    for trial in range(repeats + 1):
        order = ('baseline', 'candidate') if trial % 2 == 0 else ('candidate', 'baseline')
        for key in order:
            start = clock()
            rows = [dict(row) for row in connection.execute(text(queries[key]), parameters).mappings()]
            elapsed = (clock() - start) / 1_000_000
            readings[key].append(round(elapsed, 3))
            signatures.add(result_signature(rows))
            if len(signatures) != 1:
                raise ValueError('Candidate and baseline results differ, or data changed. No rewrite adopted.')
            print(f'{key}, trial {trial + 1}: {elapsed / 1000:.2f} s', flush=True)
    result = {'result_sha256': signatures.pop(), 'results_equal': True}
    for key, sql in queries.items():
        compiled = text(sql).compile(dialect=connection.dialect)
        plan = '\n'.join(str(row[0]) for row in connection.exec_driver_sql('EXPLAIN ANALYZE ' + str(compiled), parameters))
        trials = readings[key][1:]
        result[key] = {'sql': sql, 'sql_sha256': hashlib.sha256(sql.encode()).hexdigest(), 'plan': plan,
                       'first_read_ms': readings[key][0], 'repeated_uncached_ms': trials,
                       'median_repeated_ms': round(median(trials), 3)}
    before, after = [result[key]['median_repeated_ms'] for key in ('baseline', 'candidate')]
    result['speedup'] = round(before / after, 3) if after else None
    result['change_pct'] = round((after - before) / before * 100, 2) if before else None
    return result


def run(engine, repeats=3):
    original = load_report()
    if engine.dialect.name != 'mysql':
        raise ValueError('MySQL is required.')
    with engine.connect() as connection:
        version = connection.scalar(text('SELECT VERSION()'))
        if version != original['mysql_version']:
            raise ValueError('MySQL version differs from the baseline report.')
        connection.rollback()
        connection.execute(text('SET SESSION MAX_EXECUTION_TIME = 300000'))
        connection.execute(text('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
        connection.execute(text('SET TRANSACTION READ ONLY'))
        connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT'))
        try:
            counts = {name: connection.scalar(text(f'SELECT COUNT(*) FROM `{name}`'))
                      for name in ('MEMBERS', 'CLAIMS', 'ENROLLMENT', 'FACILITY', 'CONDITION', 'INSURANCE', 'PLAN', 'MEMBER_CONDITION')}
            if counts != original['table_counts']:
                raise ValueError('Table counts differ from the original baseline.')
            results = []
            for name, query, sql in candidates():
                archived = SQL_DIR / 'baselines' / f'{query}.sql'
                reference = archived if archived.exists() else SQL_DIR / f'{query}.sql'
                print(f'Comparing {name} with the reference {query} query...', flush=True)
                measured = compare(connection, reference.read_text(), sql, PARAMETERS, repeats)
                results.append({'candidate_name': name, 'query': query, **measured})
                print(f"Comparison: {measured['change_pct']}% change; result checksums equal", flush=True)
            return {'measured_at': datetime.now(timezone.utc).isoformat(), 'mysql_version': version,
                    'table_counts': counts, 'parameters': PARAMETERS, 'repeats': repeats,
                    'connection': 'local' if engine.url.host in ('localhost', '127.0.0.1', '::1') else 'remote', 'results': results,
                    'method': 'One client in one read-only consistent snapshot. Current queries and candidates alternate execution order. Medians exclude the first pair. Timings include fetching; no application cache, HTTP, or browser rendering. Buffers are not flushed; background load is not controlled. No data, indexes, or dashboard queries are changed.'}
        finally:
            connection.rollback()


def main():
    from database import engine
    try:
        result = run(engine, int(os.getenv('HEALTHPULSE_BENCHMARK_RUNS', '3')))
        temporary = OUTPUT.with_suffix('.tmp')
        temporary.write_text(json.dumps(jsonable_encoder(result), indent=2))
        temporary.replace(OUTPUT)
        print(f'Comparison saved: {OUTPUT}')
        return 0
    except SQLAlchemyError:
        print('MySQL could not complete the comparison. No report or dashboard query was replaced.')
        return 1
    except (ValueError, OSError) as exc:
        print(f'Comparison not saved: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
