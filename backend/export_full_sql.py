"""Execute the dashboard SQL on all source CSV records when MySQL is unavailable."""
import csv
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from sql_showcase import ROOT, build_showcase, full_showcase

PATH = Path('/private/tmp/healthpulse-premium-source.sqlite')
DEFINITIONS = {
    'MEMBERS': ('members.csv', 'member_id INTEGER PRIMARY KEY, Enrollment_ID INTEGER, housing_insecurity INTEGER',
                ['member_id', 'Enrollment ID', 'housing insecurity']),
    'ENROLLMENT': ('enrollment.csv', 'Enrollment_ID INTEGER PRIMARY KEY, state TEXT, plan_id INTEGER, Coverage_tier TEXT, premium NUMERIC, start_date TEXT, end_date TEXT',
                   ['Enrollment_ID', 'state', 'plan_id', 'Coverage_tier', 'premium', 'start_date', 'end_date']),
    'CLAIMS': ('claims.csv', 'claim_id INTEGER PRIMARY KEY, member_id INTEGER, amount NUMERIC, date TEXT',
               ['claim_id', 'member_id', 'amount', 'date']),
    'MEMBER_CONDITION': ('member_condition.csv', 'Member_ID INTEGER, Condition_ID INTEGER, Diagnostic_date TEXT',
                         ['Member_ID', 'Condition_ID', 'Diagnostic_date']),
}


def export_full():
    snapshot_path = ROOT / 'frontend/public/demo/snapshot.json'
    original = snapshot_path.read_bytes()
    snapshot = json.loads(original)
    build_showcase(snapshot['sample'])
    files = {table: ROOT / 'database' / spec[0] for table, spec in DEFINITIONS.items()}
    signatures = {table: [path.stat().st_size, path.stat().st_mtime_ns] for table, path in files.items()}
    connection = sqlite3.connect(PATH)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode = WAL')
    connection.execute('PRAGMA synchronous = NORMAL')
    connection.execute('PRAGMA cache_size = -100000')
    connection.execute('CREATE TABLE IF NOT EXISTS SOURCE_METADATA (signature TEXT)')
    old_signature = connection.execute('SELECT signature FROM SOURCE_METADATA').fetchone()
    expected_counts = {r['name']: r['row_count'] for r in snapshot['overview']['tables']}
    if not old_signature or old_signature[0] != json.dumps(signatures, sort_keys=True):
        for table, (_, definition, csv_columns) in DEFINITIONS.items():
            connection.execute(f'DROP TABLE IF EXISTS {table}')
            connection.execute(f'CREATE TABLE {table} ({definition})')
            placeholders = ','.join('?' for _ in csv_columns)
            count, cents = 0, 0
            with files[table].open(newline='') as file:
                reader = csv.reader(file)
                header = next(reader)
                positions = [header.index(column) for column in csv_columns]
                batch = []
                for row in reader:
                    values = [None if row[i] in ('', '\\N', 'NULL') else row[i] for i in positions]
                    if table == 'ENROLLMENT' and values[-1] == '2099-12-31':
                        values[-1] = None
                    if table == 'CLAIMS':
                        cents += int(Decimal(values[2]) * 100)
                    batch.append(values)
                    if len(batch) == 50000:
                        connection.executemany(f'INSERT INTO {table} VALUES ({placeholders})', batch)
                        count += len(batch)
                        batch.clear()
                        if count % 1000000 == 0:
                            connection.commit()
                            print(f'{table}: {count:,} source records loaded', flush=True)
                if batch:
                    connection.executemany(f'INSERT INTO {table} VALUES ({placeholders})', batch)
                    count += len(batch)
            connection.commit()
            assert count == expected_counts[table], f'Source count differs for {table}'
            if table == 'CLAIMS':
                assert abs(cents / 100 - snapshot['overview']['total_claims_value']) < 0.01
            print(f'{table}: all {count:,} records reconciled', flush=True)
        for statement in [
            'CREATE INDEX ix_members_enrollment ON MEMBERS(Enrollment_ID)',
            'CREATE INDEX ix_claims_member_date ON CLAIMS(member_id, date)',
            'CREATE UNIQUE INDEX pk_member_condition ON MEMBER_CONDITION(Member_ID, Condition_ID, Diagnostic_date)',
        ]:
            print('Building source validation index', flush=True)
            connection.execute(statement)
            connection.commit()
        connection.execute('DELETE FROM SOURCE_METADATA')
        connection.execute('INSERT INTO SOURCE_METADATA VALUES (?)', [json.dumps(signatures, sort_keys=True)])
        connection.commit()
    table_counts = {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in DEFINITIONS}
    assert all(table_counts[t] == expected_counts[t] for t in DEFINITIONS)
    for table in DEFINITIONS:
        columns = [r['name'] for r in connection.execute(f'PRAGMA table_info({table})')]
        key_columns = ['Member_ID', 'Condition_ID', 'Diagnostic_date'] if table == 'MEMBER_CONDITION' else [columns[0]]
        for row in snapshot['sample'][table]:
            found = connection.execute(f'SELECT * FROM {table} WHERE ' + ' AND '.join(f'{key} = ?' for key in key_columns), [row[key] for key in key_columns]).fetchone()
            assert found is not None and all(found[column] == row[column] for column in columns), f'Source differs from exported sample in {table}'
    def read(sql, parameters):
        print('Executing full-source SELECT', flush=True)
        return [dict(r) for r in connection.execute(sql, parameters)]
    showcase = full_showcase(read, table_counts, 'Full synthetic source CSVs', f'SQLite {sqlite3.sqlite_version}', False)
    showcase['source_files'] = [f'database/{spec[0]}' for spec in DEFINITIONS.values()]
    showcase['source_reconciliation'] = 'All four table counts and the complete claims amount match the saved MySQL export. Projected fields match every exported sample record.'
    showcase['source_checked_at'] = datetime.now(timezone.utc).isoformat()
    assert all(signatures[t] == [p.stat().st_size, p.stat().st_mtime_ns] for t, p in files.items())
    assert snapshot_path.read_bytes() == original, 'Snapshot changed during full-source computation.'
    snapshot['sql_showcase'] = showcase
    temporary = snapshot_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot, separators=(',', ':')))
    temporary.replace(snapshot_path)
    connection.close()
    print(json.dumps({'full_members': showcase['total_members'], 'eligible_members': showcase['eligible_members'],
                      'eligible_enrollments': showcase['eligible_enrollments'], 'results': {c['id']: c['rows'] for c in showcase['cases']}}), flush=True)


if __name__ == '__main__':
    export_full()
