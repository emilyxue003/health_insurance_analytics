"""Make the verified index visible and verify the normal dashboard SELECT."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from benchmark_covering_index import scan_query
from benchmark_mysql import measure
from performance_evidence import load_covering
from sql_showcase import PARAMETERS, SQL_DIR

OUTPUT = Path(__file__).resolve().parent / 'benchmarks/mysql-covering-index-applied.json'


def validate_normal_result(timing, plan, trial):
    if timing['result_sha256'] != trial['result_sha256']:
        raise ValueError('The normal dashboard query returned different results.')
    if f"Covering index scan on CLAIMS using {trial['index_name']}" not in plan:
        raise ValueError('The normal dashboard plan did not select the tested covering index.')
    if max(timing['repeated_uncached_ms']) >= min(trial['baseline']['repeated_uncached_ms']):
        raise ValueError('The normal query is not consistently faster than the saved reference trials.')


def activate_and_verify(connection, index_name, was_visible, verify):
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', index_name):
        raise ValueError('Unexpected index name.')
    connection.rollback()
    changed = not was_visible
    if changed:
        print('Making the tested covering index visible to normal dashboard queries...', flush=True)
        connection.exec_driver_sql(f'ALTER TABLE `CLAIMS` ALTER INDEX `{index_name}` VISIBLE')
        connection.commit()
    try:
        result = verify()
    except BaseException:
        connection.rollback()
        if changed:
            connection.exec_driver_sql(f'ALTER TABLE `CLAIMS` ALTER INDEX `{index_name}` INVISIBLE')
            connection.commit()
            print('Verification did not complete; previous index visibility restored.', flush=True)
        raise
    return result


def run(engine):
    trial = load_covering()
    sql = (SQL_DIR / 'conditions_costs.sql').read_text()
    name = trial['index_name']
    if scan_query(sql, name) != trial['candidate']['sql'] or scan_query(sql, 'ix_claims_member_date') != trial['baseline']['sql']:
        raise ValueError('Dashboard SQL has changed since the covering trial.')
    if engine.dialect.name != 'mysql':
        raise ValueError('MySQL is required.')
    with engine.connect() as connection:
        version = connection.scalar(text('SELECT VERSION()'))
        if version != trial['mysql_version']:
            raise ValueError('MySQL version differs from the successful trial.')
        rows = connection.execute(text('''SELECT COLUMN_NAME, IS_VISIBLE, SUB_PART
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'CLAIMS' AND INDEX_NAME = :name
            ORDER BY SEQ_IN_INDEX'''), {'name': name}).mappings().all()
        if [row['COLUMN_NAME'] for row in rows] != trial['index_columns'] or any(row['SUB_PART'] is not None for row in rows):
            raise ValueError('The tested index is missing or has a different definition.')
        if len({row['IS_VISIBLE'] for row in rows}) != 1:
            raise ValueError('Index visibility is inconsistent.')
        was_visible = rows[0]['IS_VISIBLE'] == 'YES'
        previous_switch = connection.scalar(text('SELECT @@SESSION.optimizer_switch'))
        connection.execute(text('SET SESSION lock_wait_timeout = 15'))

        def verify():
            try:
                connection.execute(text("SET SESSION optimizer_switch = 'use_invisible_indexes=off'"))
                connection.execute(text('SET SESSION MAX_EXECUTION_TIME = 300000'))
                connection.execute(text('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
                connection.execute(text('SET TRANSACTION READ ONLY'))
                connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT'))
                counts = {table: connection.scalar(text(f'SELECT COUNT(*) FROM `{table}`')) for table in
                          ('MEMBERS', 'CLAIMS', 'ENROLLMENT', 'FACILITY', 'CONDITION', 'INSURANCE', 'PLAN', 'MEMBER_CONDITION')}
                if counts != trial['table_counts']:
                    raise ValueError('Table counts changed since the successful trial.')
                print('Verifying four executions of the normal dashboard query, then its plan. This takes a few minutes.', flush=True)
                timing = measure(lambda: [dict(row) for row in connection.execute(text(sql), PARAMETERS).mappings()])
                compiled = text(sql).compile(dialect=engine.dialect)
                plan = '\n'.join(str(row[0]) for row in connection.exec_driver_sql('EXPLAIN ANALYZE ' + str(compiled), PARAMETERS))
                validate_normal_result(timing, plan, trial)
                result = {'measured_at': datetime.now(timezone.utc).isoformat(), 'mysql_version': version,
                    'table_counts': counts, 'parameters': PARAMETERS, 'connection': trial['connection'],
                    'index_name': name, 'index_columns': trial['index_columns'], 'previously_visible': was_visible,
                    'applied': True, 'repeats': 3, 'query': 'conditions_costs', 'sql': sql,
                    'sql_sha256': hashlib.sha256(sql.encode()).hexdigest(), 'plan': plan, **timing,
                    'method': 'Normal unhinted dashboard SELECT after making the tested covering index visible. One initial and three direct repeated reads in a read-only snapshot, plus EXPLAIN ANALYZE. Exact results match the successful covering trial and original full-data baseline. Query timing excludes metadata, HTTP, app caches, rendering, and index creation. Buffers are not flushed. Reference trial occurred earlier, so this is activation verification, not a fresh paired speedup estimate.'}
                return result
            finally:
                connection.rollback()
                connection.execute(text('SET SESSION optimizer_switch = :settings'), {'settings': previous_switch})
                connection.commit()

        def verify_and_save():
            result = verify()
            temporary = OUTPUT.with_suffix('.tmp')
            temporary.write_text(json.dumps(jsonable_encoder(result), indent=2))
            temporary.replace(OUTPUT)
            return result

        return activate_and_verify(connection, name, was_visible, verify_and_save)


def main():
    from database import engine
    try:
        result = run(engine)
        print(f"Index active; normal conditions query median: {result['median_repeated_ms'] / 1000:.2f} seconds. Identical results verified.")
        print(f'Activation verification saved: {OUTPUT}')
        return 0
    except (SQLAlchemyError, KeyboardInterrupt):
        print('Activation did not complete. Review whether previous visibility was restored in the output above. No records were changed.')
        return 1
    except (ValueError, OSError) as exc:
        print(f'Activation not completed: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
