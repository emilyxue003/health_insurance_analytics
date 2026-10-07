"""Check grain, boundary dates, overlap, zero premiums, and empty samples."""
import asyncio
from datetime import date
from decimal import Decimal
import json
import unittest
from unittest.mock import patch

from sql_showcase import build_showcase, full_showcase, sample_database


class SQLShowcaseTests(unittest.TestCase):
    def fixture(self):
        return {
            'MEMBERS': [
                {'member_id': i, 'Enrollment_ID': e, 'housing_insecurity': h}
                for i, e, h in [(1, 1, 1), (2, 2, 0), (3, None, None), (4, 3, 1), (5, 4, None)]],
            'ENROLLMENT': [
                {'Enrollment_ID': i, 'state': state, 'plan_id': plan, 'Coverage_tier': 'Individual',
                 'premium': price, 'start_date': '2024-01-01', 'end_date': end}
                for i, state, plan, price, end in [(1, 'IL', 1, 100, None), (2, 'TX', 1, 300, '2025-11-30'),
                                                 (3, 'IL', 1, 1000, '2025-11-29'), (4, 'IL', 2, 0, None)]],
            'CLAIMS': [{'claim_id': i, 'member_id': m, 'amount': a, 'date': d}
                       for i, m, a, d in [(1, 1, 10, '2024-11-01'), (2, 1, 20, '2025-11-30'),
                                          (3, 1, 999, '2025-12-01'), (4, 1, 999, '2024-10-31'),
                                          (5, 4, 1000, '2025-01-01')]],
            'MEMBER_CONDITION': [{'Member_ID': 1, 'Condition_ID': c, 'Diagnostic_date': d}
                                 for c, d in [(1, '2020-01-01'), (1, '2021-01-01'), (2, '2025-12-01')]],
        }

    def test_grain_dates_and_weights(self):
        result = build_showcase(self.fixture())
        cases = {c['id']: c['rows'] for c in result['cases']}
        self.assertEqual(result['eligible_members'], 3)
        self.assertEqual([r['premium_index'] for r in cases['regional_premiums']], [150, 50])
        housing = cases['housing_premiums'][0]
        self.assertEqual((housing['matched_cells'], housing['yes_members'], housing['no_members']), (1, 1, 1))
        self.assertEqual(housing['premium_difference'], -200)
        conditions = {r['conditions']: r for r in cases['conditions_costs']}
        self.assertEqual(conditions['1']['claims'], 2)
        self.assertEqual(conditions['1']['total_claim_amount'], 30)
        self.assertEqual(conditions['0']['members'], 2)
        self.assertEqual(conditions['0']['average_claim_amount'], 0)
        self.assertEqual(conditions['0']['average_premium'], 150)

    def test_no_overlap_and_empty(self):
        sample = self.fixture()
        sample['MEMBERS'][0]['housing_insecurity'] = 0
        housing = build_showcase(sample)['cases'][1]['rows'][0]
        self.assertEqual(housing['matched_cells'], 0)
        self.assertIsNone(housing['premium_difference'])
        empty = build_showcase({key: [] for key in sample})
        self.assertEqual(empty['cases'][0]['rows'], [])
        self.assertIsNone(empty['cases'][1]['rows'][0]['yes_premium'])
        self.assertEqual(empty['cases'][2]['rows'], [])

    def test_common_weights_not_raw_group_means(self):
        sample = self.fixture()
        sample['MEMBERS'].append({'member_id': 6, 'Enrollment_ID': 2, 'housing_insecurity': 0})
        housing = build_showcase(sample)['cases'][1]['rows'][0]
        self.assertEqual(housing['overlap_weight'], 1)
        self.assertEqual(housing['no_members'], 2)
        self.assertEqual(housing['premium_difference'], -200)

    def test_full_execution_reconciles_claims_without_fanout(self):
        sample = self.fixture()
        with sample_database(sample) as connection:
            result = full_showcase(lambda sql, params: [dict(r) for r in connection.execute(sql, params)],
                                   {key: len(rows) for key, rows in sample.items()}, 'Fixture', 'SQLite', False)
        self.assertEqual(result['scope'], 'full')
        self.assertEqual(result['total_members'], 5)
        self.assertEqual(result['eligible_members'], 3)
        self.assertEqual(sum(r['claims'] for r in result['cases'][2]['rows']), 2)

    def test_mysql_decimal_counts_preserve_regional_reconciliation(self):
        from fastapi.encoders import jsonable_encoder
        sample = self.fixture()
        with sample_database(sample) as connection:
            def read(sql, parameters, inconsistent=False):
                rows = [dict(row) for row in connection.execute(sql, parameters)]
                for row in rows:
                    if 'premium_index' in row:
                        for field in ('enrollments', 'average_premium', 'premium_index'):
                            row[field] = Decimal(str(row[field]))
                        if inconsistent:
                            row['premium_index'] += Decimal('1')
                return rows
            counts = {key: len(rows) for key, rows in sample.items()}
            result = full_showcase(read, counts, 'Fixture', 'MySQL numeric types', False)
            regional = result['cases'][0]['rows']
            self.assertEqual(sum(row['enrollments'] for row in regional), Decimal('2'))
            self.assertEqual(jsonable_encoder(result)['cases'][0]['rows'][0]['premium_index'], 150.0)
            with self.assertRaises(AssertionError):
                full_showcase(lambda sql, parameters: read(sql, parameters, True), counts,
                              'Fixture', 'MySQL numeric types', False)

    def test_result_export_preserves_scope_and_filters_only_regional_rows(self):
        from fastapi import HTTPException
        from explorer import export_premium_equity
        sample = self.fixture()
        with sample_database(sample) as connection:
            data = full_showcase(lambda sql, params: [dict(r) for r in connection.execute(sql, params)],
                                 {key: len(rows) for key, rows in sample.items()}, 'Fixture', 'SQLite', False)
        parameters = (date(2025, 11, 30), date(2024, 11, 1), date(2025, 12, 1), 2)
        with patch('explorer.premium_equity', return_value={'sql_showcase': data}) as query:
            response = export_premium_equity('regional_premiums', 2, *parameters)
            query.assert_called_once_with(*parameters)
            exported = json.loads(response.body)
            expected = [r for r in data['cases'][0]['rows'] if r['enrollments'] >= 2]
            self.assertEqual(exported['rows'], expected)
            self.assertEqual(exported['scope'], 'full')
            self.assertEqual(exported['parameters'], data['parameters'])
            self.assertEqual(exported['state_minimum_count'], 2)
            self.assertEqual(exported['sql_sha256'], data['cases'][0]['sha256'])
            self.assertIn('attachment;', response.headers['content-disposition'])
            housing = json.loads(export_premium_equity('housing_premiums', 1000, *parameters).body)
            self.assertEqual(housing['rows'], data['cases'][1]['rows'])
            self.assertIsNone(housing['state_minimum_count'])
            with self.assertRaises(HTTPException) as caught:
                export_premium_equity('unknown', 0, *parameters)
            self.assertEqual(caught.exception.status_code, 404)

    def test_http_parameter_validation_and_safe_failure(self):
        from fastapi import FastAPI
        from sqlalchemy.exc import OperationalError
        from explorer import router
        app = FastAPI()
        app.include_router(router)
        async def request(query):
            messages = []
            async def receive():
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            async def send(message):
                messages.append(message)
            await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                       'method': 'GET', 'scheme': 'http', 'path': '/api/stats/premium-equity',
                       'raw_path': b'/api/stats/premium-equity', 'root_path': '',
                       'query_string': query.encode(), 'headers': [], 'server': ('test', 80), 'client': ('test', 1)}, receive, send)
            return messages[0]['status'], b''.join(m.get('body', b'') for m in messages)
        for query, expected in [('claims_start=2025-12-01&claims_end=2025-11-01', 400),
                                ('claims_end=2026-01-01', 400), ('minimum_peers=1', 422), ('as_of=invalid', 422)]:
            self.assertEqual(asyncio.run(request(query))[0], expected)
        with patch('explorer.engine.connect', side_effect=OperationalError('private statement', {}, Exception('private credentials'))):
            status, body = asyncio.run(request(''))
        self.assertEqual(status, 503)
        self.assertNotIn(b'private', body)


if __name__ == '__main__':
    unittest.main()
