"""Check that timing evidence separates first reads and stable repeat trials."""
import unittest
from benchmark_mysql import measure, result_signature


class BenchmarkTests(unittest.TestCase):
    def test_first_read_is_not_part_of_repeated_median(self):
        ticks = iter([0, 50_000_000, 100_000_000, 102_000_000,
                      200_000_000, 204_000_000, 300_000_000, 306_000_000])
        result = measure(lambda: [{'count': 5000000}], clock=lambda: next(ticks))
        self.assertEqual(result['first_read_ms'], 50)
        self.assertEqual(result['repeated_uncached_ms'], [2, 4, 6])
        self.assertEqual(result['median_repeated_ms'], 4)
        self.assertEqual(result['returned_rows'], 1)

    def test_changed_results_reject_timings(self):
        reads = iter([[{'n': 1}], [{'n': 2}]])
        with self.assertRaisesRegex(ValueError, 'changed'):
            measure(lambda: next(reads))

    def test_output_order_does_not_change_signature(self):
        self.assertEqual(result_signature([{'state': 'IL'}, {'state': 'TX'}]),
                         result_signature([{'state': 'TX'}, {'state': 'IL'}]))

    def test_shared_dashboard_queries_keep_aggregate_results(self):
        from sqlalchemy import create_engine
        import models
        from dashboard_queries import claims_trend_statement, members_by_state_statement
        engine = create_engine('sqlite://')
        models.Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.connection.driver_connection.create_function('date_format', 2, lambda value, pattern: value[:7])
            connection.execute(models.Member.__table__.insert(), [
                {'member_id': 1, 'State': 'IL'}, {'member_id': 2, 'State': 'IL'}, {'member_id': 3, 'State': 'TX'}])
            from datetime import date
            connection.execute(models.Claim.__table__.insert(), [
                {'claim_id': 1, 'amount': 10, 'date': date(2025, 1, 1)},
                {'claim_id': 2, 'amount': 20, 'date': date(2025, 1, 15)},
                {'claim_id': 3, 'amount': 40, 'date': date(2025, 2, 1)}])
            states = {row.state: row.count for row in connection.execute(members_by_state_statement(models.Member.__table__))}
            claims = [(row.month, float(row.total)) for row in connection.execute(claims_trend_statement(models.Claim.__table__))]
        self.assertEqual(states, {'IL': 2, 'TX': 1})
        self.assertEqual(claims, [('2025-01', 30), ('2025-02', 40)])


if __name__ == '__main__':
    unittest.main()
