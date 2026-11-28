import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.cloud_report import run_tests


class CloudTestOutputTests(unittest.TestCase):
    def test_fixture_commands_remain_in_log_without_creating_actions_annotations(self):
        def fixture():
            print('::warning::BLOCKED fixture')
            print('::error::publication failure fixture', file=sys.stderr)

        suite = unittest.TestSuite([unittest.FunctionTestCase(fixture)])
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'tests.log'
            output = io.StringIO()
            with patch('unittest.defaultTestLoader.discover', return_value=suite), \
                    redirect_stdout(output), redirect_stderr(output):
                result = run_tests(log)
            self.assertEqual(result['result'], 'PASS')
            self.assertIn('::warning::BLOCKED fixture', log.read_text(encoding='utf-8'))
            self.assertIn('::error::publication failure fixture', log.read_text(encoding='utf-8'))
            self.assertNotIn('::warning::', output.getvalue())
            self.assertNotIn('::error::', output.getvalue())

    def test_failed_fixture_keeps_failure_result(self):
        def fixture():
            raise AssertionError('expected fixture failure')

        suite = unittest.TestSuite([unittest.FunctionTestCase(fixture)])
        with tempfile.TemporaryDirectory() as folder:
            with patch('unittest.defaultTestLoader.discover', return_value=suite), redirect_stdout(io.StringIO()):
                result = run_tests(Path(folder) / 'tests.log')
            self.assertEqual(result, {'result': 'FAIL', 'count': 1, 'failures': 1, 'errors': 0})
