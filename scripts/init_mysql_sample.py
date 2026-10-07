"""Initialize only an empty isolated sample database, without deleting tables."""
from pathlib import Path
import os
import sys
from time import sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from database import engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


def initialize():
    if engine.url.database != 'healthpulse_sample':
        raise ValueError('Initialization requires the isolated healthpulse_sample database.')
    attempts = 60 if os.getenv('CI') else 1
    for attempt in range(attempts):
        try:
            connection = engine.connect()
            break
        except OperationalError:
            if attempt + 1 == attempts:
                raise RuntimeError('Sample database connection failed. Check local settings and MySQL readiness.') from None
            sleep(1)
    with connection:
        existing = connection.scalar(text('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()'))
        if existing:
            raise ValueError('The sample database must have no tables. Existing tables are never removed.')
        for source in ('schema.sql', 'sample_data.sql'):
            for statement in (ROOT / 'database' / source).read_text().split(';'):
                if statement.strip():
                    connection.exec_driver_sql(statement)
            connection.commit()
    print('Initialized the isolated connected synthetic sample database.')


if __name__ == '__main__':
    initialize()
