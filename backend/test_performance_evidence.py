"""Guard against unsupported speed claims and changed analytical results."""
import copy
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from compare_mysql import candidates, compare
from performance_evidence import load_report, load_evidence, load_covering, validate_report, validate_optimization, validate_covering, validate_activation
from sql_showcase import PARAMETERS, check_rows, independent_results, sample_database
import test_sql_showcase


class PerformanceEvidenceTests(unittest.TestCase):
    def test_saved_report_download_and_safe_missing_evidence(self):
        import json
        from fastapi import HTTPException
        from explorer import query_performance
        response = query_performance()
        self.assertEqual(json.loads(response.body), load_evidence())
        self.assertIn('attachment;', response.headers['content-disposition'])
        with patch('performance_evidence.load_evidence', side_effect=OSError('private path')):
            with self.assertRaises(HTTPException) as caught:
                query_performance()
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn('private', caught.exception.detail)

    def test_report_rejects_missing_queries_and_changed_sql_or_timings(self):
        report = load_report()
        for kind in ('missing', 'sql', 'median'):
            broken = copy.deepcopy(report)
            if kind == 'missing':
                broken['results'].pop()
            elif kind == 'sql':
                broken['results'][0]['sql'] += ' '
            else:
                broken['results'][0]['median_repeated_ms'] += 100
            with self.assertRaises(ValueError):
                validate_report(broken)

    def test_comparison_rejects_changed_results_and_speed_claims(self):
        original = load_evidence()['optimization']
        for key, value in (('result_sha256', 'changed'), ('speedup', 100), ('results_equal', False)):
            broken = copy.deepcopy(original)
            broken['results'][0][key] = value
            with self.assertRaises(ValueError):
                validate_optimization(broken, load_report())

    def test_grouped_regional_query_preserves_weights_nulls_and_boundaries(self):
        sql = (Path(__file__).parent / 'sql_candidates/regional_grouped.sql').read_text()
        fixture = test_sql_showcase.SQLShowcaseTests().fixture()
        rng = random.Random(12)
        for i in range(6, 200):
            fixture['ENROLLMENT'].append({'Enrollment_ID': i, 'state': rng.choice(['IL', 'TX', None]),
                'plan_id': rng.choice([1, 2, None]), 'Coverage_tier': rng.choice(['Individual', 'Family', None]),
                'premium': rng.choice([0, 25, 300, 1000, None, -1]), 'start_date': '2024-01-01',
                'end_date': rng.choice([None, '2025-11-30', '2025-11-29'])})
        for sample in (fixture, {key: [] for key in fixture}):
            expected = independent_results(sample, PARAMETERS)[0]['regional_premiums']
            with sample_database(sample) as connection:
                rows = [dict(row) for row in connection.execute(sql, PARAMETERS)]
            check_rows(rows, expected)

    def test_scan_candidates_preserve_condition_query_semantics(self):
        fixture = test_sql_showcase.SQLShowcaseTests().fixture()
        expected = independent_results(fixture, PARAMETERS)[0]['conditions_costs']
        for name, query, sql in candidates():
            if query == 'conditions_costs':
                with sample_database(fixture) as connection:
                    rows = [dict(row) for row in connection.execute(sql.replace(' USE INDEX (PRIMARY)', ''), PARAMETERS)]
                check_rows(rows, expected)

    def test_comparison_rejects_different_results(self):
        class Rows:
            def __init__(self, n):
                self.n = n
            def mappings(self):
                return [{'n': self.n}]
        class Connection:
            def execute(self, sql, parameters):
                return Rows(1 if str(sql) == 'SELECT 1' else 2)
        with self.assertRaisesRegex(ValueError, 'results differ'):
            compare(Connection(), 'SELECT 1', 'SELECT 2', {})

    def test_covering_index_requires_opt_in_and_reuses_existing_definition(self):
        from benchmark_covering_index import INDEX_NAME, INDEX_COLUMNS, select_index, scan_query
        with self.assertRaises(ValueError):
            select_index([])
        self.assertEqual(select_index([], True), (INDEX_NAME, True))
        self.assertEqual(select_index([{'name': 'existing_covering', 'column_names': INDEX_COLUMNS}]), ('existing_covering', False))
        with self.assertRaises(ValueError):
            select_index([{'name': INDEX_NAME, 'column_names': ['date']}], True)
        with self.assertRaises(ValueError):
            scan_query('FROM CLAIMS\n', 'unsafe` index')
        fixture = test_sql_showcase.SQLShowcaseTests().fixture()
        sql = scan_query((Path(__file__).parents[1] / 'frontend/public/sql/conditions_costs.sql').read_text(), INDEX_NAME)
        with sample_database(fixture) as connection:
            rows = [dict(row) for row in connection.execute(sql.replace(f' USE INDEX (`{INDEX_NAME}`)', ''), PARAMETERS)]
        check_rows(rows, independent_results(fixture, PARAMETERS)[0]['conditions_costs'])

    def test_covering_trial_rejects_inconsistent_or_slow_evidence(self):
        trial = load_covering()
        for key, value in (('result_sha256', 'different'), ('speedup', 10), ('index_columns', ['date'])):
            broken = copy.deepcopy(trial)
            broken[key] = value
            with self.assertRaises(ValueError):
                validate_covering(broken, load_report())

    def test_activation_restores_invisibility_on_failed_check_and_preserves_success(self):
        from activate_covering_index import activate_and_verify
        class Connection:
            def __init__(self):
                self.sql = []
            def rollback(self):
                pass
            def commit(self):
                pass
            def exec_driver_sql(self, sql):
                self.sql.append(sql)
        connection = Connection()
        def fail():
            raise ValueError('Changed result')
        with self.assertRaises(ValueError):
            activate_and_verify(connection, 'tested_index', False, fail)
        self.assertEqual(connection.sql, ['ALTER TABLE `CLAIMS` ALTER INDEX `tested_index` VISIBLE',
                                          'ALTER TABLE `CLAIMS` ALTER INDEX `tested_index` INVISIBLE'])
        connection = Connection()
        self.assertEqual(activate_and_verify(connection, 'tested_index', False, lambda: {'checked': True}), {'checked': True})
        self.assertEqual(len(connection.sql), 1)
        connection = Connection()
        with self.assertRaises(ValueError):
            activate_and_verify(connection, 'tested_index', True, fail)
        self.assertEqual(connection.sql, [])

    def test_normal_query_activation_rejects_wrong_plan_or_result(self):
        from activate_covering_index import validate_normal_result
        trial = load_covering()
        timing = {'result_sha256': trial['result_sha256'], 'repeated_uncached_ms': trial['candidate']['repeated_uncached_ms']}
        validate_normal_result(timing, trial['candidate']['plan'], trial)
        with self.assertRaises(ValueError):
            validate_normal_result(timing, 'Table scan on CLAIMS', trial)
        with self.assertRaises(ValueError):
            validate_normal_result({**timing, 'result_sha256': 'different'}, trial['candidate']['plan'], trial)

    def test_published_activation_requires_matching_scope_sql_plan_and_timings(self):
        activation = load_evidence()['covering_activation']
        for key, value in (('applied', False), ('parameters', {}), ('sql', 'SELECT 1'),
                           ('plan', 'Table scan on CLAIMS'), ('result_sha256', 'different'),
                           ('median_repeated_ms', 1), ('max_repeated_ms', 1)):
            broken = copy.deepcopy(activation)
            broken[key] = value
            with self.assertRaises(ValueError):
                validate_activation(broken, load_covering())


if __name__ == '__main__':
    unittest.main()
