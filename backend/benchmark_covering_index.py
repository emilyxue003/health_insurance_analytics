"""Explicitly opt in to a covering index, then measure it without promoting it."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from time import perf_counter_ns

from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from compare_mysql import compare
from performance_evidence import load_report
from sql_showcase import PARAMETERS, SQL_DIR

INDEX_NAME = 'ix_claims_member_date_amount_hp'
INDEX_COLUMNS = ['member_id', 'date', 'amount']
OUTPUT = Path(__file__).resolve().parent / 'benchmarks/mysql-covering-index.json'
CREATE_SQL = f'CREATE INDEX `{INDEX_NAME}` ON `CLAIMS` (`member_id`, `date`, `amount`) INVISIBLE ALGORITHM=INPLACE LOCK=NONE'


def select_index(indexes, allow_create=False):
    for index in indexes:
        if index['name'] == INDEX_NAME and index['column_names'] != INDEX_COLUMNS:
            raise ValueError('The experiment index name already has a different definition.')
    for index in indexes:
        if index['column_names'] == INDEX_COLUMNS and not index.get('dialect_options', {}).get('mysql_length'):
            if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', index['name']):
                raise ValueError('Unexpected covering index name.')
            return index['name'], False
    if not allow_create:
        raise ValueError('Creating the covering index requires HEALTHPULSE_CREATE_COVERING_INDEX=1. This adds an invisible index and consumes storage; records are unchanged.')
    return INDEX_NAME, True


def scan_query(sql, index_name):
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', index_name) or sql.count('FROM CLAIMS\n') != 1:
        raise ValueError('Unexpected index or claims query definition.')
    return sql.replace('FROM CLAIMS\n', f'FROM CLAIMS USE INDEX (`{index_name}`)\n')


def run(engine, repeats=3, allow_create=False):
    if engine.dialect.name != 'mysql' or not 3 <= repeats <= 20:
        raise ValueError('MySQL and 3 to 20 repeats are required.')
    original = load_report()
    sql = (SQL_DIR / 'conditions_costs.sql').read_text()
    with engine.connect() as connection:
        version = connection.scalar(text('SELECT VERSION()'))
        if version != original['mysql_version']:
            raise ValueError('MySQL version differs from the original report.')
        inspector = inspect(connection)
        if inspector.get_table_options('CLAIMS').get('mysql_engine', '').lower() != 'innodb':
            raise ValueError('This index experiment requires InnoDB.')
        indexes = inspector.get_indexes('CLAIMS')
        if not any(index['name'] == 'ix_claims_member_date' and index['column_names'] == ['member_id', 'date'] for index in indexes):
            raise ValueError('The reference claims index is missing or changed.')
        index_name, create = select_index(indexes, allow_create)
        reference = scan_query(sql, 'ix_claims_member_date')
        candidate = scan_query(sql, index_name)
        previous_switch = connection.scalar(text('SELECT @@SESSION.optimizer_switch'))
        connection.rollback()
        connection.execute(text('SET SESSION lock_wait_timeout = 15'))
        build_ms = None
        if create:
            print('Adding an invisible CLAIMS(member_id, date, amount) index. This may take several minutes and consumes storage. No records are changed.', flush=True)
            start = perf_counter_ns()
            connection.exec_driver_sql(CREATE_SQL)
            build_ms = round((perf_counter_ns() - start) / 1_000_000, 3)
            connection.commit()
            print('Index created; it remains invisible to normal dashboard sessions.', flush=True)
        else:
            print('Reusing an existing matching covering index.', flush=True)
        try:
            connection.execute(text("SET SESSION optimizer_switch = 'use_invisible_indexes=on'"))
            connection.execute(text('SET SESSION MAX_EXECUTION_TIME = 300000'))
            connection.execute(text('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            connection.execute(text('SET TRANSACTION READ ONLY'))
            connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT'))
            counts = {name: connection.scalar(text(f'SELECT COUNT(*) FROM `{name}`')) for name in
                      ('MEMBERS', 'CLAIMS', 'ENROLLMENT', 'FACILITY', 'CONDITION', 'INSURANCE', 'PLAN', 'MEMBER_CONDITION')}
            if counts != original['table_counts']:
                raise ValueError('Full table counts changed. The index remains installed; no comparison is published.')
            measured = compare(connection, reference, candidate, PARAMETERS, repeats)
            expected = next(r['result_sha256'] for r in original['results'] if r['query'] == 'conditions_costs')
            if measured['result_sha256'] != expected:
                raise ValueError('Results differ from the saved full-data report.')
            return {'measured_at': datetime.now(timezone.utc).isoformat(), 'mysql_version': version,
                    'table_counts': counts, 'parameters': PARAMETERS, 'repeats': repeats,
                    'connection': 'local' if engine.url.host in ('localhost', '127.0.0.1', '::1') else 'remote',
                    'index_name': index_name, 'index_columns': INDEX_COLUMNS, 'index_created': create,
                    'index_build_ms': build_ms, 'indexes_before': indexes,
                    'candidate_name': 'conditions_covering_claims', 'query': 'conditions_costs', **measured,
                    'method': 'Reference uses the existing member/date claims index; candidate uses a covering index. Both are measured after index creation in one read-only snapshot, with alternating execution order. Index construction is excluded from query timings. Invisible indexes are enabled only in this benchmark session. No dashboard query or index visibility is changed. Buffers are not flushed; one client; background load is not controlled.'}
        finally:
            connection.rollback()
            connection.execute(text('SET SESSION optimizer_switch = :settings'), {'settings': previous_switch})
            connection.commit()


def main():
    from database import engine
    try:
        report = run(engine, int(os.getenv('HEALTHPULSE_BENCHMARK_RUNS', '3')),
                     os.getenv('HEALTHPULSE_CREATE_COVERING_INDEX') == '1')
        temporary = OUTPUT.with_suffix('.tmp')
        temporary.write_text(json.dumps(jsonable_encoder(report), indent=2))
        temporary.replace(OUTPUT)
        print(f"Conditions comparison: {report['change_pct']}% time change; identical results.")
        print(f'Comparison saved: {OUTPUT}')
        return 0
    except SQLAlchemyError:
        print('Database could not complete the experiment. Any successfully created index remains installed. No dashboard query or prior report was replaced.')
        return 1
    except (ValueError, OSError) as exc:
        print(f'Experiment not saved: {exc} Any created index remains installed; no dashboard query was changed.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
