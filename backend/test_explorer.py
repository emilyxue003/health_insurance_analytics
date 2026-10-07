"""Cache, pagination, and optional read-only MySQL metric checks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from threading import Barrier, Event
import unittest

from fastapi import HTTPException
from sqlalchemy import Column, Date, Integer, MetaData, String, Table, create_engine, literal, select, union_all
from sqlalchemy.exc import OperationalError

from explorer import (TTLCache, coverage_statement, database_read, decode_cursor,
                      encode_cursor, engine, get_table, member_statement, page_statement)


class CacheTests(unittest.TestCase):
    def test_expiry_starts_after_loading_and_cache_is_bounded(self):
        now = [0]
        cache = TTLCache(ttl=10, max_entries=2, clock=lambda: now[0])
        def loader():
            now[0] = 100
            return 'value'
        self.assertEqual(cache.get('a', loader), 'value')
        now[0] = 109
        self.assertEqual(cache.get('a', lambda: 'wrong'), 'value')
        now[0] = 110
        self.assertEqual(cache.get('a', lambda: 'fresh'), 'fresh')
        cache.get('b', lambda: 2)
        cache.get('c', lambda: 3)
        self.assertEqual(list(cache.entries), ['b', 'c'])

    def test_concurrent_calls_use_one_loader(self):
        cache, barrier, release, started = TTLCache(), Barrier(3), Event(), Event()
        calls = []
        def loader():
            calls.append(1)
            started.set()
            release.wait(3)
            return 42
        def request():
            barrier.wait()
            return cache.get('same', loader)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(request) for _ in range(2)]
            barrier.wait()
            self.assertTrue(started.wait(3))
            release.set()
            self.assertEqual([future.result(timeout=3) for future in futures], [42, 42])
        self.assertEqual(len(calls), 1)

    def test_failure_releases_loader_and_is_not_cached(self):
        cache = TTLCache()
        def fail():
            raise ValueError('failure')
        with self.assertRaises(ValueError):
            cache.get('key', fail)
        self.assertFalse(cache.running)
        self.assertEqual(cache.get('key', lambda: 'recovered'), 'recovered')

    def test_database_errors_are_sanitized(self):
        def fail():
            raise OperationalError('private SQL', {}, Exception('private connection details'))
        with self.assertRaises(HTTPException) as raised:
            database_read(fail)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn('private', raised.exception.detail)


class PaginationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        self.table = Table('LINKS', MetaData(), Column('member', Integer, primary_key=True),
                           Column('condition', Integer, primary_key=True), Column('diagnosis', Date, primary_key=True))
        self.table.metadata.create_all(self.engine)
        self.rows = [
            {'member': 1, 'condition': 1, 'diagnosis': date(2020, 1, day)} for day in (1, 2, 3)
        ] + [{'member': 1, 'condition': 2, 'diagnosis': date(2020, 1, 1)},
             {'member': 2, 'condition': 1, 'diagnosis': date(2020, 1, 1)}]
        with self.engine.begin() as connection:
            connection.execute(self.table.insert(), self.rows)

    def tearDown(self):
        self.engine.dispose()

    def test_composite_date_pages_do_not_skip_or_repeat(self):
        cursor, collected = None, []
        with self.engine.connect() as connection:
            while True:
                fetched = [dict(row) for row in connection.execute(page_statement(self.table, 2, cursor)).mappings()]
                page = fetched[:2]
                collected.extend(page)
                if len(fetched) <= 2:
                    break
                cursor = encode_cursor(self.table, page[-1])
        self.assertEqual(collected, self.rows)

    def test_malformed_wrong_table_and_wrong_type_cursors_rejected(self):
        cursor = encode_cursor(self.table, self.rows[0])
        other = Table('OTHER', MetaData(), Column('id', Integer, primary_key=True))
        for table, token in [(self.table, '!'), (self.table, 'bnVsbA'), (other, cursor)]:
            with self.assertRaises(HTTPException) as raised:
                decode_cursor(table, token)
            self.assertEqual(raised.exception.status_code, 400)

    def test_unapproved_table_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            get_table('MEMBERS; DROP TABLE MEMBERS')
        self.assertEqual(raised.exception.status_code, 404)


@unittest.skipUnless(os.getenv('HEALTHPULSE_LIVE_TESTS') == '1', 'Read-only MySQL checks not requested')
class LiveMetricTests(unittest.TestCase):
    def test_age_boundaries_nulls_and_future_dates(self):
        reference = date(2026, 10, 5)
        births = [date(2008, 10, 6), date(2008, 10, 5), date(1991, 10, 6), date(1991, 10, 5),
                  date(1981, 10, 5), date(1971, 10, 5), date(1961, 10, 5), date(1951, 10, 5),
                  date(2026, 10, 6), None]
        dataset = union_all(*[select(literal(birth, type_=Date).label('DOB'), literal('F').label('Sex'),
                                     literal(70 if birth is not None else None).label('heart_rate')) for birth in births]).subquery()
        with engine.connect() as connection:
            row = connection.execute(member_statement(dataset, reference)).mappings().one()
        self.assertEqual([row[label] for label in ('0–17', '18–34', '35–44', '45–54', '55–64', '65–74', '75+')], [1, 2, 1, 1, 1, 1, 1])
        self.assertEqual(row['total'], 10)
        self.assertEqual(row['F'], 10)
        self.assertEqual(float(row['heart_rate']), 70)

    def test_coverage_dates_are_inclusive_and_null_end_is_open(self):
        reference = date(2026, 10, 5)
        dates = [(reference, reference), (reference, None), (date(2026, 10, 6), None),
                 (date(2026, 1, 1), date(2026, 10, 4)), (None, None)]
        dataset = union_all(*[select(literal(start, type_=Date).label('start_date'), literal(end, type_=Date).label('end_date'),
                                     literal('Family', type_=String).label('Coverage_tier')) for start, end in dates]).subquery()
        with engine.connect() as connection:
            row = connection.execute(coverage_statement(dataset, reference)).mappings().one()
        self.assertEqual(row['count'], 5)
        self.assertEqual(row['active'], 2)


if __name__ == '__main__':
    unittest.main()
