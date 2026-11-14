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


def full_report(changed=False, companion_changed=False):
    return {'steam': {'app_id': '2430930', 'depot_id': '2430931', 'manifest_id': '1', 'checked_at': 'now'},
            'source': {'pak_size': 123, 'pak_sha256': 'd' * 64}, 'stock_locres': {},
            'build_fingerprint': FP, 'pak_changed': changed,
            'final_pak': {'size': 12, 'sha256': 'e' * 64 if changed else SHA},
            'companions': {'ASA_RU_Fix_P.utoc': {'size': 100, 'sha256': ('9' if companion_changed else '1') * 64},
                           'ASA_RU_Fix_P.ucas': {'size': 5, 'sha256': '2' * 64}}}


def with_bundle():
    value = stable()
    value['bundle'] = {'version': '1.0.2', 'release': {'tag': 'v1.0.2', 'commit': 'c' * 40, 'published_at': 'now'},
                       'artifacts': updater.bundle_artifact_records(REPO, '1.0.2', updater.bundle_identities(full_report()))}
    return value


class AutomationTests(unittest.TestCase):
    def test_first_bundle_uses_v102_with_identical_pak_and_preserves_legacy(self):
        state = {'schema': 1, 'last_successful': {'manifest_id': '1', 'build_fingerprint': FP}}
        code, report, pub, *_ = self.exercise(state)
        self.assertEqual(code, 0)
        self.assertEqual(pub.publish_release.call_args.args[0], '1.0.2')
        self.assertTrue(report['release_created'])
        self.assertFalse(report['pak_changed'])
        self.assertTrue(report['bundle_changed'])
        updated = pub.write_channel.call_args.args[0]
        for key in ('version', 'release', 'artifact'):
            self.assertEqual(updated[key], stable()[key])
        self.assertEqual(updated['bundle']['version'], '1.0.2')
        self.assertEqual({asset['filename'] for asset in updated['bundle']['artifacts']},
                         {updater.PAK_NAME, 'ASA_RU_Fix_P.utoc', 'ASA_RU_Fix_P.ucas'})

    def exercise(self, state=None, *, changed=False, fail=None, force=False, probe_fail=False,
                 failure_context=None, now="2026-11-01T00:00:00Z", bootstrap_error=None,
                 existing_bundle=False, companion_changed=False, missing_companions=False,
                 expected_first_pak=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            publisher = Mock()
            publisher.read_channel.return_value = (with_bundle() if existing_bundle else stable(),
                                                   state or {'schema': 1}, 'old-channel')
            publisher.write_channel.return_value = 'new-channel'
            publisher.publish_release.side_effect = lambda version, commit, assets, **kwargs: {
                'version': version, 'tag': f'v{version}', 'commit': commit, 'published_at': 'now',
                'size': 12, 'sha256': 'e' * 64, 'asset_url': 'new-url'}
            probe = full_report()['steam']
            candidate = full_report(changed, companion_changed)
            if missing_companions:
                candidate.pop('companions')
            def execute(*args):
                if bootstrap_error and '--probe-only' not in args and 'tools.bootstrap' in args:
                    raise bootstrap_error
                if fail and 'build.py' in args:
                    if failure_context:
                        updater.write_json(root / 'work/build_failure.json', failure_context)
                    raise fail if isinstance(fail, Exception) else RuntimeError('injected build failure')
            with patch.object(updater, 'utc_now', return_value=now), \
                 patch.object(updater, 'build_fingerprint', return_value=FP), \
                 patch.object(updater.subprocess, 'check_output', return_value='c' * 40), \
                 patch.object(updater, 'execute', side_effect=execute) as commands, \
                 patch.object(updater, 'probe_manifest', side_effect=(probe_fail if isinstance(probe_fail, Exception) else RuntimeError('probe')) if probe_fail else None, return_value=probe), \
                 patch.object(updater, 'run_tests', return_value={'result': 'PASS', 'count': 123}) as tests, \
                 patch.object(updater, 'read_json', return_value=failure_context or {}), \
                 patch.object(updater, 'make_live_report', return_value=candidate), \
                 patch.object(updater, 'stage_release', return_value=[]) as stage:
                code = updater.run_update(root, REPO, publisher, force=force, run_id='42',
                                          expected_first_pak=expected_first_pak)
            report = json.loads((root / 'work/live-build-report.json').read_text(encoding='utf-8'))
            return code, report, publisher, commands, tests, stage

    def test_processed_pair_skips_all_heavy_steps_and_state_commit(self):
        state = {'schema': 1, 'last_successful': {'manifest_id': '1', 'build_fingerprint': FP}}
        code, report, pub, cmd, tests, stage = self.exercise(state, existing_bundle=True)
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

    def test_unchanged_bundle_processes_new_pair_without_release(self):
        code, report, pub, cmd, tests, stage = self.exercise(existing_bundle=True)
        self.assertEqual(code, 0)
        self.assertEqual(cmd.call_count, 3)
        self.assertEqual(cmd.call_args.args[-1], '1')
        tests.assert_called_once(); stage.assert_not_called(); pub.publish_release.assert_not_called()
        new_stable, state = pub.write_channel.call_args.args[:2]
        self.assertEqual(new_stable['version'], '1.0.0')
        self.assertEqual(new_stable['artifact'], stable()['artifact'])
        self.assertEqual(new_stable['bundle'], with_bundle()['bundle'])
        self.assertEqual(state['last_successful']['build_fingerprint'], FP)

    def test_changed_verified_pak_publishes_next_patch(self):
        code, report, pub, cmd, tests, stage = self.exercise(changed=True, existing_bundle=True)
        self.assertEqual(code, 0)
        self.assertEqual(pub.publish_release.call_args.args[0], '1.0.3')
        self.assertTrue(report['release_created'])
        self.assertEqual(pub.write_channel.call_args.args[0]['bundle']['version'], '1.0.3')

    def test_change_to_one_companion_publishes_complete_next_patch(self):
        code, report, pub, *_ = self.exercise(existing_bundle=True, companion_changed=True)
        self.assertEqual(code, 0)
        self.assertFalse(report['pak_changed'])
        self.assertTrue(report['bundle_changed'])
        self.assertEqual(pub.publish_release.call_args.args[0], '1.0.3')
        state = pub.write_channel.call_args.args[1]
        self.assertEqual(state['latest_release']['artifacts']['ASA_RU_Fix_P.utoc']['sha256'], '9' * 64)

    def test_new_build_with_missing_companions_fails_before_publication(self):
        code, report, pub, _, _, stage = self.exercise(changed=True, missing_companions=True)
        self.assertEqual(code, 2)
        self.assertEqual(report['failure_kind'], 'deterministic')
        self.assertNotIn('pending_release', pub.write_channel.call_args.args[1])
        pub.publish_release.assert_not_called()
        stage.assert_not_called()

    def test_first_bundle_rejects_a_pak_other_than_the_game_verified_candidate(self):
        code, report, pub, _, _, stage = self.exercise(expected_first_pak='f' * 64)
        self.assertEqual(code, 2)
        self.assertEqual(report['failure_stage'], 'validation')
        self.assertNotIn('pending_release', pub.write_channel.call_args.args[1])
        stage.assert_not_called()
        pub.publish_release.assert_not_called()

    def test_blocked_pair_has_no_heavy_steps(self):
        state = {'schema': 1, 'last_attempt': {'manifest_id': '1', 'build_fingerprint': FP, 'failure_count': 2}}
        code, report, pub, cmd, tests, stage = self.exercise(state)
        self.assertEqual(code, 0)
        self.assertEqual(cmd.call_count, 1)
        pub.write_channel.assert_not_called()
        self.assertEqual(report['status'], 'blocked')

    def test_network_failures_do_not_block_and_backoff_expires(self):
        state = {'schema': 1}
        for now in ('2026-11-01T00:00:00Z', '2026-11-01T00:30:00Z'):
            code, report, pub, cmd, tests, stage = self.exercise(
                state, now=now, bootstrap_error=RuntimeError('BOOTSTRAP ERROR: <urlopen error [WinError 10060]>'))
            self.assertEqual(code, 2)
            self.assertEqual(report['failure_kind'], 'transient')
            self.assertEqual(pub.write_channel.call_args.args[0], stable())
            state = pub.write_channel.call_args.args[1]
            self.assertEqual(state.get('last_attempt', {}).get('failure_count', 0), 0)
            pub.publish_release.assert_not_called(); tests.assert_not_called()
        code, report, pub, cmd, tests, stage = self.exercise(state, now='2026-11-01T00:45:00Z')
        self.assertEqual(code, 0); self.assertEqual(report['status'], 'backoff')
        self.assertEqual(cmd.call_count, 1)
        pub.write_channel.assert_not_called(); pub.publish_release.assert_not_called()
        code, report, pub, cmd, tests, stage = self.exercise(state, now='2026-11-01T01:30:00Z')
        self.assertEqual(code, 0); self.assertEqual(report['status'], 'success')
        self.assertNotIn('transient_failure', pub.write_channel.call_args.args[1])

    def test_unknown_bootstrap_error_is_not_transient(self):
        code, report, pub, *_ = self.exercise(bootstrap_error=RuntimeError('ooz compiler failed'))
        self.assertEqual(code, 2)
        self.assertNotEqual(report['failure_kind'], 'transient')
        self.assertEqual(pub.write_channel.call_args.args[1]['last_attempt']['failure_count'], 1)

    def test_two_validation_failures_block_and_next_run_is_warning_only(self):
        state = {'schema': 1}
        for count in (1, 2):
            code, report, pub, *_ = self.exercise(state, fail=True,
                failure_context={'issues': [{'kind': 'source_changed'}]})
            self.assertEqual(code, 2)
            self.assertEqual(report['failure_kind'], 'deterministic')
            state = pub.write_channel.call_args.args[1]
            self.assertEqual(state['last_attempt']['failure_count'], count)
            pub.publish_release.assert_not_called()
        code, report, pub, cmd, *_ = self.exercise(state)
        self.assertEqual(code, 0); self.assertEqual(report['status'], 'blocked')
        self.assertEqual(cmd.call_count, 1); pub.write_channel.assert_not_called()
        self.assertEqual(self.exercise(state, force=True)[1]['status'], 'success')

    def test_validation_evidence_wins_over_network_text(self):
        code, report, pub, *_ = self.exercise(fail=RuntimeError('[WinError 10060]'),
            failure_context={'issues': [{'kind': 'source_changed'}]})
        self.assertEqual(code, 2); self.assertEqual(report['failure_kind'], 'deterministic')
        pub.publish_release.assert_not_called()

    def test_probe_network_error_has_backoff_without_a_manifest(self):
        code, report, pub, *_ = self.exercise(probe_fail=TimeoutError('network timed out'))
        self.assertEqual(code, 2)
        self.assertEqual(report['failure_kind'], 'transient')
        state = pub.write_channel.call_args.args[1]
        self.assertIsNone(state['transient_failure']['manifest_id'])
        self.assertNotIn('last_attempt', state)
        code, report, pub, cmd, *_ = self.exercise(state, now='2026-11-01T00:10:00Z')
        self.assertEqual(code, 0); self.assertEqual(report['status'], 'backoff')
        cmd.assert_not_called(); pub.write_channel.assert_not_called()
        self.assertEqual(self.exercise(state, now='2026-11-01T00:30:00Z')[1]['status'], 'success')
        self.assertEqual(self.exercise(state, force=True)[1]['status'], 'success')

    def test_actual_child_diagnostic_reaches_the_classifier(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(updater.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 2, '', 'BOOTSTRAP ERROR: <urlopen error [WinError 10060]>')):
                with self.assertRaises(RuntimeError) as caught:
                    updater.execute(Path(folder), 'python', '-m', 'tools.bootstrap')
            self.assertTrue(updater.is_transient_network_error(caught.exception))

    def test_bootstrap_preserves_typed_timeout_across_process_boundary(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(updater.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 75, '', 'BOOTSTRAP TRANSIENT NETWORK ERROR: timed out')):
                with self.assertRaises(updater.TransientNetworkError):
                    updater.execute(Path(folder), 'python', '-m', 'tools.bootstrap')

    def test_all_validation_failures_prevent_publication(self):
        for kind in ('source_changed', 'missing_en_key', 'locres_parse', 'pak_structure',
                     'sha256_mismatch', 'placeholder', 'richtext'):
            with self.subTest(kind=kind):
                code, report, pub, cmd, tests, stage = self.exercise(changed=True, fail=True,
                    failure_context={'issues': [{'kind': kind}]})
                self.assertEqual(code, 2)
                self.assertEqual(report['failure_kind'], 'deterministic')
                self.assertEqual(pub.write_channel.call_args.args[0], stable())
                pub.publish_release.assert_not_called(); stage.assert_not_called()
                tests.assert_not_called()

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

    def test_stable_bundle_rejects_duplicate_and_cross_release_url(self):
        for replacements in ('duplicate', 'url'):
            value = with_bundle()
            if replacements == 'duplicate':
                value['bundle']['artifacts'][1] = value['bundle']['artifacts'][0]
            else:
                value['bundle']['artifacts'][1]['download_url'] = value['bundle']['artifacts'][1]['download_url'].replace('v1.0.2', 'v1.0.3')
            with self.subTest(replacements=replacements), self.assertRaises(ValueError):
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
