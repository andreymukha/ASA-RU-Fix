import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import auto_update as updater


SHA = 'a' * 64
FP = 'b' * 64
REPO = 'owner/repo'


def stable():
    return {'schema': 1, 'channel': 'stable', 'version': '1.0.0',
            'release': {'tag': 'v1.0.0', 'commit': 'c' * 40, 'published_at': 'now'},
            'build': {'fingerprint': None, 'shooter_desired': 1243, 'engine_desired': 21},
            'artifact': {'filename': updater.PAK_NAME, 'size': 12, 'sha256': SHA,
                         'download_url': f'https://github.com/{REPO}/releases/download/v1.0.0/{updater.PAK_NAME}'}}


def full_report(changed=False):
    return {'steam': {'app_id': '2430930', 'depot_id': '2430931', 'manifest_id': '1', 'checked_at': 'now'},
            'source': {'pak_size': 123, 'pak_sha256': 'd' * 64}, 'stock_locres': {},
            'build_fingerprint': FP, 'pak_changed': changed,
            'final_pak': {'size': 12, 'sha256': 'e' * 64 if changed else SHA}}


class AutomationTests(unittest.TestCase):
    def exercise(self, state=None, *, changed=False, fail=None, force=False, probe_fail=False, failure_context=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            publisher = Mock()
            publisher.read_channel.return_value = (stable(), state or {'schema': 1}, 'old-channel')
            publisher.write_channel.return_value = 'new-channel'
            publisher.publish_release.return_value = {'version': '1.0.1', 'tag': 'v1.0.1', 'commit': 'c' * 40,
                'published_at': 'now', 'size': 12, 'sha256': 'e' * 64, 'asset_url': 'new-url'}
            probe = full_report()['steam']
            def execute(*args):
                if fail and 'build.py' in args:
                    if failure_context:
                        updater.write_json(root / 'work/build_failure.json', failure_context)
                    raise RuntimeError('injected build failure')
            with patch.object(updater, 'build_fingerprint', return_value=FP), \
                 patch.object(updater.subprocess, 'check_output', return_value='c' * 40), \
                 patch.object(updater, 'execute', side_effect=execute) as commands, \
                 patch.object(updater, 'probe_manifest', side_effect=RuntimeError('probe') if probe_fail else None, return_value=probe), \
                 patch.object(updater, 'run_tests', return_value={'result': 'PASS', 'count': 123}) as tests, \
                 patch.object(updater, 'read_json', return_value=failure_context or {}), \
                 patch.object(updater, 'make_live_report', return_value=full_report(changed)), \
                 patch.object(updater, 'stage_release', return_value=[]) as stage:
                code = updater.run_update(root, REPO, publisher, force=force, run_id='42')
            report = json.loads((root / 'work/live-build-report.json').read_text(encoding='utf-8'))
            return code, report, publisher, commands, tests, stage

    def test_processed_pair_skips_all_heavy_steps_and_state_commit(self):
        state = {'schema': 1, 'last_successful': {'manifest_id': '1', 'build_fingerprint': FP}}
        code, report, pub, cmd, tests, stage = self.exercise(state)
        self.assertEqual(code, 0)
        self.assertEqual(cmd.call_count, 1)
        self.assertIn('--probe-only', cmd.call_args.args)
        tests.assert_not_called(); stage.assert_not_called()
        pub.publish_release.assert_not_called(); pub.write_channel.assert_not_called()
        self.assertFalse(report['heavy_build'])
        self.assertEqual(report['downloaded_bytes'], 0)

    def test_build_failure_never_runs_tests_or_publisher(self):
        code, report, pub, cmd, tests, stage = self.exercise(fail=True)
        self.assertEqual(code, 2)
        tests.assert_not_called(); stage.assert_not_called(); pub.publish_release.assert_not_called()
        self.assertEqual(pub.write_channel.call_args.args[0], stable())
        self.assertEqual(pub.write_channel.call_args.args[1]['last_attempt']['failure_count'], 1)

    def test_unchanged_pak_processes_new_pair_without_release(self):
        code, report, pub, cmd, tests, stage = self.exercise()
        self.assertEqual(code, 0)
        self.assertEqual(cmd.call_count, 3)
        self.assertEqual(cmd.call_args.args[-1], '1')
        tests.assert_called_once(); stage.assert_not_called(); pub.publish_release.assert_not_called()
        new_stable, state = pub.write_channel.call_args.args[:2]
        self.assertEqual(new_stable['version'], '1.0.0')
        self.assertEqual(new_stable['artifact'], stable()['artifact'])
        self.assertEqual(state['last_successful']['build_fingerprint'], FP)

    def test_changed_verified_pak_publishes_next_patch(self):
        code, report, pub, cmd, tests, stage = self.exercise(changed=True)
        self.assertEqual(code, 0)
        self.assertEqual(pub.publish_release.call_args.args[0], '1.0.1')
        self.assertTrue(report['release_created'])
        self.assertEqual(pub.write_channel.call_args.args[0]['version'], '1.0.1')

    def test_blocked_pair_has_no_heavy_steps(self):
        state = {'schema': 1, 'last_attempt': {'manifest_id': '1', 'build_fingerprint': FP, 'failure_count': 2}}
        code, report, pub, cmd, tests, stage = self.exercise(state)
        self.assertEqual(code, 2)
        self.assertEqual(cmd.call_count, 1)
        pub.write_channel.assert_not_called()
        self.assertEqual(report['status'], 'blocked')

    def test_force_retries_blocked_pair(self):
        state = {'schema': 1, 'last_attempt': {'manifest_id': '1', 'build_fingerprint': FP, 'failure_count': 2}}
        self.assertEqual(self.exercise(state, force=True)[0], 0)

    def test_probe_failure_does_not_block_unknown_pair(self):
        code, report, pub, cmd, tests, stage = self.exercise(probe_fail=True)
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'probe_failed')
        pub.write_channel.assert_not_called(); tests.assert_not_called()

    def test_stable_rejects_nonversioned_download_url(self):
        value = stable(); value['artifact']['download_url'] = 'https://example.org/latest'
        with self.assertRaises(ValueError):
            updater.validate_channel(value, {'schema': 1}, REPO)

    def test_source_guard_failure_preserves_real_download_metadata(self):
        detail = {'source': {'downloaded_bytes': 100, 'pak_size': 200}, 'stock_locres': {'ShooterGame EN': {}},
                  'issues': [{'kind': 'source_changed', 'resource': 'ShooterGame',
                              'full_key': 'Content\t123', 'old_source_hash': 1, 'current_source_hash': 2}]}
        code, report, pub, cmd, tests, stage = self.exercise(fail=True, failure_context=detail)
        self.assertEqual(code, 2)
        self.assertEqual(report['downloaded_bytes'], 100)
        self.assertEqual(report['source_changed'], 1)
        self.assertEqual(report['validation_failure']['issues'][0]['current_source_hash'], 2)
        self.assertEqual(pub.write_channel.call_args.args[0], stable())
        pub.publish_release.assert_not_called()


if __name__ == '__main__':
    unittest.main()
