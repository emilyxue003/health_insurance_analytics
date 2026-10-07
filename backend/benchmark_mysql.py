"""Measure full-data SELECTs on MySQL and retain exact queries and plans."""
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
from statistics import median
from time import perf_counter_ns

from fastapi.encoders import jsonable_encoder
from sqlalchemy import MetaData, Table, func, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

from dashboard_queries import claims_trend_statement, members_by_state_statement
from explorer import TABLE_NAMES, member_statement, coverage_statement, page_statement
from population_health import health_statement
from sql_showcase import CASES, PARAMETERS, SQL_DIR

REPORT = Path(__file__).resolve().parent / 'benchmarks/mysql-performance.json'


def result_signature(rows):
    normalized = [json.dumps(jsonable_encoder(row), sort_keys=True, separators=(',', ':')) for row in rows]
    return hashlib.sha256('\n'.join(sorted(normalized)).encode()).hexdigest()


def measure(read, repeats=3, clock=perf_counter_ns):
    """Fully consume each result; reject inconsistent repeat results."""
    if repeats < 3 or repeats > 20:
        raise ValueError('Repeat count must be from 3 to 20.')
    samples = []
    reference = None
    returned_rows = None
    for _ in range(repeats + 1):
        start = clock()
        rows = read()
        elapsed = (clock() - start) / 1_000_000
        signature = result_signature(rows)
        if reference is not None and signature != reference:
            raise ValueError('Query results changed between timing trials.')
        reference, returned_rows = signature, len(rows)
        samples.append(elapsed)
    return {'first_read_ms': round(samples[0], 3), 'repeated_uncached_ms': [round(x, 3) for x in samples[1:]],
            'median_repeated_ms': round(median(samples[1:]), 3),
            'min_repeated_ms': round(min(samples[1:]), 3), 'max_repeated_ms': round(max(samples[1:]), 3),
            'returned_rows': returned_rows, 'result_sha256': reference}


def run(engine, repeats=3, group='all'):
    if group not in ('all', 'dashboard', 'premium'):
        raise ValueError('Benchmark group must be all, dashboard, or premium.')
    if engine.dialect.name != 'mysql':
        raise ValueError('This benchmark requires MySQL. SQLite results cannot substitute.')
    with engine.connect() as connection:
        version = connection.scalar(text('SELECT VERSION()'))
        match = re.match(r'(\d+)\.(\d+)\.(\d+)', version)
        if not match or tuple(map(int, match.groups())) < (8, 0, 18) or 'MariaDB' in version:
            raise ValueError('MySQL 8.0.18 or later is required for EXPLAIN ANALYZE.')
        connection.rollback()
        connection.execute(text('SET SESSION MAX_EXECUTION_TIME = 300000'))
        connection.execute(text('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
        connection.execute(text('SET TRANSACTION READ ONLY'))
        connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT'))
        try:
            tables = {name: Table(name, MetaData(), autoload_with=connection, resolve_fks=False) for name in TABLE_NAMES}
            counts = {name: connection.scalar(select(func.count()).select_from(table)) for name, table in tables.items()}
            indexes = {name: inspect(connection).get_indexes(name) for name in TABLE_NAMES}
            primary_keys = {name: list(table.primary_key.columns.keys()) for name, table in tables.items()}
            cutoff = date.fromisoformat(PARAMETERS['as_of'])
            statements = [
                ('member_demographics', member_statement(tables['MEMBERS'], cutoff)),
                ('coverage_summary', coverage_statement(tables['ENROLLMENT'], cutoff)),
                ('population_health', health_statement(tables['MEMBERS'])),
                ('monthly_claims', claims_trend_statement(tables['CLAIMS'])),
                ('members_by_state', members_by_state_statement(tables['MEMBERS'])),
                ('member_lookup', select(tables['MEMBERS']).where(tables['MEMBERS'].c.member_id == 1).limit(1)),
                ('members_first_page', page_statement(tables['MEMBERS'], 25)),
            ]
            queries = []
            if group in ('all', 'dashboard'):
                for name, statement in statements:
                    compiled = statement.compile(dialect=engine.dialect)
                    queries.append((name, str(compiled), compiled.params))
            if group in ('all', 'premium'):
                for name, _, _, _ in CASES:
                    compiled = text((SQL_DIR / f'{name}.sql').read_text()).compile(dialect=engine.dialect)
                    queries.append((name, str(compiled), PARAMETERS))
            results = []
            for name, sql, parameters in queries:
                print(f'Measuring {name} on the full database...', flush=True)
                def read():
                    return [dict(row) for row in connection.exec_driver_sql(sql, parameters).mappings()]
                timing = measure(read, repeats)
                plan = '\n'.join(str(row[0]) for row in connection.exec_driver_sql('EXPLAIN ANALYZE ' + sql, parameters))
                results.append({'query': name, 'sql': sql, 'parameters': jsonable_encoder(parameters),
                                'sql_sha256': hashlib.sha256(sql.encode()).hexdigest(), 'plan': plan, **timing})
                print(f"{name}: median {timing['median_repeated_ms']:.3f} ms; {timing['returned_rows']} output rows", flush=True)
            return {'source': 'Full MySQL database', 'scope': 'full', 'mysql_version': version,
                    'measured_at': datetime.now(timezone.utc).isoformat(), 'table_counts': counts,
                    'indexes': indexes, 'primary_keys': primary_keys, 'parameters': PARAMETERS,
                    'client_environment': {'machine': platform.machine(), 'logical_cpus': os.cpu_count()},
                    'connection': 'local' if engine.url.host in ('localhost', '127.0.0.1', '::1') else 'remote',
                    'method': 'One client, read-only consistent snapshot. One initial execution plus repeated direct database reads. Timing includes result transfer and fetching, excludes connection setup, EXPLAIN, application caching, HTTP, and rendering. Row-count scans occur before timing. Database buffers are not flushed; first read is not a cold-disk measurement. Background load is not controlled.',
                    'repeats': repeats, 'results': results}
        finally:
            connection.rollback()


def main():
    from database import engine
    try:
        report = run(engine, int(os.getenv('HEALTHPULSE_BENCHMARK_RUNS', '3')),
                     os.getenv('HEALTHPULSE_BENCHMARK_GROUP', 'all'))
        REPORT.parent.mkdir(exist_ok=True)
        temporary = REPORT.with_suffix('.tmp')
        temporary.write_text(json.dumps(jsonable_encoder(report), indent=2))
        temporary.replace(REPORT)
        print(f'Benchmark saved: {REPORT}')
        return 0
    except SQLAlchemyError:
        print('MySQL could not complete the benchmark. Check database access and query support. No report was replaced.')
        return 1
    except (ValueError, OSError) as exc:
        print(f'Benchmark not saved: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
