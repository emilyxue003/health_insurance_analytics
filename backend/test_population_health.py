import unittest

from sqlalchemy import Column, Float, Integer, MetaData, Table, create_engine

from population_health import format_health, health_statement, numeric, summarize_rows


class HealthMeasuresTests(unittest.TestCase):
    def test_sql_and_source_rows_agree_with_missing_values_and_zero_exercise(self):
        rows = [
            {'heart_rate': 40, 'hours_sleep_per_day': 5, 'minutes_exercise_per_week': 0, 'smoker': 1, 'drinker': 0},
            {'heart_rate': 80, 'hours_sleep_per_day': 8, 'minutes_exercise_per_week': 150, 'smoker': 0, 'drinker': 1},
            {'heart_rate': None, 'hours_sleep_per_day': None, 'minutes_exercise_per_week': None, 'smoker': None, 'drinker': None},
        ]
        engine = create_engine('sqlite://')
        table = Table('MEMBERS', MetaData(), *(Column(name, Integer if name in ('smoker', 'drinker') else Float) for name in rows[0]))
        table.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(table.insert(), rows)
            sql = format_health(connection.execute(health_statement(table)).mappings().one(), 'test')
        source = format_health(summarize_rows(rows), 'test')
        self.assertEqual(sql, source)
        self.assertEqual(sql['averages']['heart_rate'], {'value': 60.0, 'count': 2, 'missing': 1})
        self.assertEqual(sql['averages']['sleep']['value'], 6.5)
        self.assertEqual(sql['averages']['exercise']['value'], 75.0)
        self.assertEqual(sql['distributions']['exercise'][0]['count'], 1)
        self.assertEqual(sql['behaviors'][0]['unknown'], 1)
        self.assertIsNone(numeric('\\N'))
        engine.dispose()

    def test_empty_population_has_no_fabricated_averages(self):
        empty = format_health(summarize_rows([]), 'test')
        self.assertEqual(empty['total_members'], 0)
        self.assertIsNone(empty['averages']['heart_rate']['value'])


if __name__ == '__main__':
    unittest.main()
