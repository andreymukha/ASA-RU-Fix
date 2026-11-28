import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.automation_summary import main, summarize


class AutomationSummaryTests(unittest.TestCase):
    def test_blocked_and_backoff_explicitly_report_no_full_validation(self):
        for status in ('blocked', 'backoff'):
            with self.subTest(status=status):
                summary = summarize({'status': status, 'heavy_build': False,
                                     'decision': {'reason': 'check deferred'}})
                self.assertIn(status.upper(), summary)
                self.assertIn('НЕ ВЫПОЛНЯЛАСЬ', summary)
                self.assertNotIn('SUCCESS', summary)

    def test_unchanged_manifest_is_a_normal_skip(self):
        summary = summarize({'status': 'skipped', 'decision': {'reason': 'already processed'}})
        self.assertIn('SKIPPED', summary)
        self.assertIn('already processed', summary)
        self.assertNotIn('BLOCKED', summary)

    def test_only_successful_full_build_reports_pass(self):
        summary = summarize({'status': 'success', 'heavy_build': True, 'bundle_version': '1.0.3'})
        self.assertIn('SUCCESS', summary)
        self.assertIn('PASS', summary)
        self.assertIn('1.0.3', summary)
        self.assertNotIn('PASS', summarize({'status': 'failed', 'heavy_build': True}))

    def test_publication_failure_and_unavailable_report_are_visible(self):
        summary = summarize({'status': 'publication_failed', 'failure_stage': 'channel_commit',
                             'error': 'network timeout'})
        self.assertIn('PUBLICATION_FAILED', summary)
        self.assertIn('channel_commit', summary)
        self.assertIn('network timeout', summary)
        self.assertIn('FAILED', summarize(None))

    def test_cli_preserves_json_and_appends_actions_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'report.json'
            report.write_text('{"status":"blocked","heavy_build":false}', encoding='utf-8')
            original = report.read_bytes()
            summary = Path(folder) / 'summary.md'
            summary.write_text('Previous step\n', encoding='utf-8')
            with patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(summary)}):
                self.assertEqual(main(['--report', str(report)]), 0)
            self.assertEqual(report.read_bytes(), original)
            self.assertTrue(summary.read_text(encoding='utf-8').startswith('Previous step\n'))
            self.assertIn('BLOCKED', summary.read_text(encoding='utf-8'))
