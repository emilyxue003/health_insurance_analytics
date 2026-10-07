"""Guard isolated setup and read-only API startup."""
import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


class SampleSetupTests(unittest.TestCase):
    def initializer(self):
        path = Path(__file__).resolve().parents[1] / 'scripts/init_mysql_sample.py'
        specification = importlib.util.spec_from_file_location('sample_initializer', path)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module

    def test_initializer_refuses_full_database_and_existing_tables(self):
        module = self.initializer()
        engine = MagicMock()
        engine.url = SimpleNamespace(database='health_insurance')
        with patch.object(module, 'engine', engine):
            with self.assertRaises(ValueError):
                module.initialize()
        engine.connect.assert_not_called()
        engine.url = SimpleNamespace(database='healthpulse_sample')
        connection = engine.connect.return_value.__enter__.return_value
        connection.scalar.return_value = 1
        with patch.object(module, 'engine', engine):
            with self.assertRaises(ValueError):
                module.initialize()
        connection.exec_driver_sql.assert_not_called()

    def test_api_import_does_not_connect_or_create_tables(self):
        with patch('database.engine.connect', side_effect=AssertionError('API startup attempted a database connection')):
            importlib.reload(importlib.import_module('main'))
        from models import MemberCondition
        self.assertEqual(list(MemberCondition.__table__.primary_key.columns.keys()),
                         ['Member_ID', 'Condition_ID', 'Diagnostic_date'])


if __name__ == '__main__':
    unittest.main()
