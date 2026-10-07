"""Write MySQL INSERTs for the reviewed connected synthetic sample."""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ORDER = ('CONDITION', 'FACILITY', 'INSURANCE', 'PLAN', 'ENROLLMENT', 'MEMBERS', 'MEMBER_CONDITION', 'CLAIMS')


def literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError('A sample value is not finite.')
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, separators=(',', ':'))
    return "CONVERT(X'" + str(value).encode('utf-8').hex() + "' USING utf8mb4)"


def export(destination):
    snapshot = json.loads((ROOT / 'frontend/public/demo/snapshot.json').read_text())
    if snapshot['metadata']['synthetic'] is not True:
        raise ValueError('Only the reviewed synthetic sample can be exported.')
    schema = {row['name']: row for row in snapshot['schema']}
    lines = ['/* Connected synthetic sample only. Load into a new empty sample database. */', 'START TRANSACTION;']
    for table in ORDER:
        columns = schema[table]['columns']
        for row in snapshot['sample'][table]:
            values = ', '.join(literal(row[column]) for column in columns)
            names = ', '.join('`' + column + '`' for column in columns)
            lines.append(f'INSERT INTO `{table}` ({names}) VALUES ({values});')
    lines.append('COMMIT;')
    destination.write_text('\n'.join(lines) + '\n')
    print('Exported the connected 200-member synthetic sample; no database was accessed.')


if __name__ == '__main__':
    export(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'database/sample_data.sql')
