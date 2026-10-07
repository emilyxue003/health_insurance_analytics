"""Run the showcase SELECT statements on MySQL without modifying tables."""
import json
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from database import engine
from sql_showcase import CASES, PARAMETERS, SQL_DIR


def run():
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT'))
        try:
            results = {key: [dict(row) for row in connection.execute(text((SQL_DIR / f'{key}.sql').read_text()), PARAMETERS).mappings()]
                       for key, _, _, _ in CASES}
        finally:
            connection.rollback()
    print(json.dumps(jsonable_encoder({'source': 'Live MySQL', 'parameters': PARAMETERS, 'results': results})))


if __name__ == '__main__':
    run()
