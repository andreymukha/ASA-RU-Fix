"""Recovery fixtures use real staged bytes and mocked external boundaries only."""

import copy
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools import auto_update as updater
from tools.github_publish import GitHubPublisher


REPOSITORY = 'owner/repo'
FINGERPRINT = 'f' * 64
FIRST_COMMIT = 'a' * 40
NEXT_COMMIT = 'b' * 40


class ReleaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.raw_pak = b'verified candidate PAK fixture'
        self.digest = hashlib.sha256(self.raw_pak).hexdigest()
        (self.root / 'dist').mkdir()
        (self.root / 'dist' / updater.PAK_NAME).write_bytes(self.raw_pak)
        self.companions = {}
        for suffix in ('utoc', 'ucas'):
            name = f'ASA_RU_Fix_P.{suffix}'
            raw = suffix.encode('ascii')
            (self.root / 'dist' / name).write_bytes(raw)
            self.companions[name] = {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        (self.root / 'work').mkdir()
        updater.write_json(self.root / 'work/build_validation.json', {})
        stable = {
            'schema': 1, 'channel': 'stable', 'version': '1.0.0',
            'release': {'tag': 'v1.0.0', 'commit': 'c' * 40, 'published_at': 'baseline-time'},
            'build': {'fingerprint': None, 'shooter_desired': 1243, 'engine_desired': 21},
            'artifact': {'filename': updater.PAK_NAME, 'size': 12, 'sha256': 'd' * 64,
                         'download_url': f'https://github.com/{REPOSITORY}/releases/download/v1.0.0/{updater.PAK_NAME}'},
        }
        self.channel = SimpleNamespace(stable=stable, state={'schema': 1}, head='channel-0', writes=[])
        self.initial_stable = copy.deepcopy(stable)
        self.publisher = Mock(spec=GitHubPublisher)
        self.publisher.read_channel.side_effect = lambda: (
            copy.deepcopy(self.channel.stable), copy.deepcopy(self.channel.state), self.channel.head)
        self.publisher.write_channel.side_effect = self._write_channel
        self.publisher.publish_release.side_effect = self._publish
        self.fail_success_write = False
        self.fail_partial_upload = False
        self.uploaded = {}
        self.publications = []
        self.published_metadata = None

    def _write_channel(self, stable, state, expected_sha, message):
        self.assertEqual(expected_sha, self.channel.head)
        if self.fail_success_write and message == 'Record verified Steam localization build':
            self.fail_success_write = False
            raise RuntimeError('injected channel failure after release publication')
        self.channel.writes.append((copy.deepcopy(stable), copy.deepcopy(state), message))
        self.channel.stable, self.channel.state = copy.deepcopy(stable), copy.deepcopy(state)
        self.channel.head = f'channel-{len(self.channel.writes)}'
        return self.channel.head

    def _publish(self, version, commit, assets, *, notes):
        self.assertIn('pending_release', self.channel.state)
        self.assertEqual(self.channel.state['pending_release']['commit'], commit)
        snapshot = {path.name: path.read_bytes() for path in assets}
        self.publications.append((version, commit, snapshot))
        for name, old_bytes in self.uploaded.items():
            self.assertEqual(snapshot[name], old_bytes, f'immutable existing asset changed: {name}')
        if self.fail_partial_upload:
            self.fail_partial_upload = False
            self.uploaded.update(dict(list(snapshot.items())[:2]))
            raise RuntimeError('injected partial draft upload failure')
        self.uploaded.update(snapshot)
        self.published_metadata = {
            'version': version, 'tag': f'v{version}', 'commit': commit,
            'published_at': 'original-publication-time', 'size': len(self.raw_pak), 'sha256': self.digest,
            'asset_url': f'https://github.com/{REPOSITORY}/releases/download/v{version}/{updater.PAK_NAME}',
        }
        return copy.deepcopy(self.published_metadata)

    def _run(self, *, run_id='first-run', commit=FIRST_COMMIT, timestamp='first-time',
             manifest='123', changed=True, companions=None):
        probe = {'app_id': '2430930', 'depot_id': '2430931', 'manifest_id': manifest, 'checked_at': timestamp}
        report = {
            'timestamp_utc': timestamp, 'run_id': run_id, 'git_commit': commit,
            'steam': probe, 'source': {'pak_size': 123, 'pak_sha256': 'e' * 64},
            'stock_locres': {}, 'build_fingerprint': FINGERPRINT, 'pak_changed': changed,
            'final_pak': {'path': updater.PAK_NAME, 'size': len(self.raw_pak), 'sha256': self.digest if changed else 'd' * 64},
            'companions': self.companions if companions is None else companions,
        }
        with patch.object(updater, 'build_fingerprint', return_value=FINGERPRINT), \
             patch.object(updater.subprocess, 'check_output', return_value=commit), \
             patch.object(updater, 'execute') as commands, \
             patch.object(updater, 'probe_manifest', return_value=probe) as probe_call, \
             patch.object(updater, 'run_tests', return_value={'result': 'PASS', 'count': 100}), \
             patch.object(updater, 'make_live_report', return_value=report), \
             patch.object(updater, 'utc_now', return_value=timestamp), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = updater.run_update(self.root, REPOSITORY, self.publisher, run_id=run_id)
            self.commands = commands
            self.probe_call = probe_call
        live = updater.read_json(self.root / 'work/live-build-report.json')
        return result, live

    def test_published_release_channel_failure_preserves_pending_and_true_report(self):
        self.fail_success_write = True
        result, report = self._run()
        self.assertEqual(result, 2)
        self.assertEqual(self.channel.stable, self.initial_stable)
        self.assertIn('pending_release', self.channel.state)
        self.assertEqual(self.channel.state['pending_release']['commit'], FIRST_COMMIT)
        self.assertNotIn('last_attempt', self.channel.state)
        self.assertTrue(report['release_created'])
        self.assertEqual(report['published_release'], self.published_metadata)
        self.assertEqual(report['status'], 'publication_failed')
        prepared_state = self.channel.writes[0][1]
        self.assertIn('pending_release', prepared_state)

    def test_partial_draft_retry_uses_original_report_and_commit_bytes(self):
        self.fail_partial_upload = True
        result, report = self._run()
        self.assertEqual(result, 2)
        self.assertFalse(report['release_created'])
        self.assertIn('pending_release', self.channel.state)
        original_pending = copy.deepcopy(self.channel.state['pending_release'])
        result, report = self._run(run_id='second-run', commit=NEXT_COMMIT, timestamp='second-time')
        self.assertEqual(result, 0)
        first, second = self.publications
        self.assertEqual(first, second)
        self.assertEqual(second[1], FIRST_COMMIT)
        staged_report = json.loads(second[2]['live-build-report.json'])
        self.assertEqual(staged_report, original_pending['report'])
        self.assertEqual(staged_report['run_id'], 'first-run')
        self.assertEqual(staged_report['timestamp_utc'], 'first-time')
        self.assertEqual(report['run_id'], 'second-run')
        self.assertEqual(self.channel.stable['release'], self.initial_stable['release'])
        self.assertEqual(self.channel.stable['bundle']['release']['commit'], FIRST_COMMIT)
        staged_manifest = json.loads(second[2]['release-manifest.json'])
        for key in ('schema', 'channel', 'version', 'release', 'artifact'):
            self.assertEqual(staged_manifest[key], self.initial_stable[key])
        self.assertEqual(staged_manifest['bundle']['version'], '1.0.2')
        self.assertEqual(staged_manifest['bundle']['artifacts'], self.channel.stable['bundle']['artifacts'])
        self.assertEqual({name for name in second[2] if name.startswith('ASA_RU_Fix_P.')}, set(updater.BUNDLE_NAMES))
        sums = second[2]['SHA256SUMS.txt'].decode('utf-8')
        for name in updater.BUNDLE_NAMES:
            self.assertIn(f'{hashlib.sha256(second[2][name]).hexdigest()}  {name}', sums)
        self.assertNotIn('pending_release', self.channel.state)
        self.assertEqual(self.channel.state['last_successful']['run_id'], 'second-run')

    def test_public_release_retry_clears_pending_only_after_successful_channel_commit(self):
        self.fail_success_write = True
        self.assertEqual(self._run()[0], 2)
        self.assertIn('pending_release', self.channel.state)
        self.assertEqual(self._run(run_id='recovery', commit=NEXT_COMMIT, timestamp='recovery-time')[0], 0)
        self.assertEqual(self.publications[0], self.publications[1])
        self.assertNotIn('pending_release', self.channel.state)
        self.assertEqual(self.channel.stable['version'], '1.0.0')
        self.assertEqual(self.channel.stable['bundle']['version'], '1.0.2')
        self.assertEqual(self.channel.state['last_attempt']['failure_count'], 0)
        self.assertEqual(self.channel.state['last_attempt']['attempt_count'], 1)
        self.assertEqual(self.channel.writes[-1][2], 'Record verified Steam localization build')

    def test_new_manifest_unchanged_pak_cannot_discard_existing_pending_transaction(self):
        self.fail_partial_upload = True
        self.assertEqual(self._run()[0], 2)
        original_pending = copy.deepcopy(self.channel.state['pending_release'])
        result, report = self._run(run_id='new-manifest', timestamp='next-time', manifest='124', changed=False)
        self.assertEqual(result, 2)
        self.assertEqual(self.channel.state['pending_release'], original_pending)
        self.assertEqual(self.channel.stable, self.initial_stable)
        self.assertEqual(len(self.publications), 1)
        self.assertNotIn('last_attempt', self.channel.state)
        self.assertEqual(report['status'], 'publication_failed')

    def test_release_timeout_is_publication_failure_without_source_backoff(self):
        self.publisher.publish_release.side_effect = RuntimeError('[WinError 10060] upload timeout')
        code, report = self._run(timestamp='2026-11-01T00:00:00Z')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'publication_failed')
        self.assertEqual(report['failure_kind'], 'publication')
        self.assertEqual(report['failure_stage'], 'release_publish')
        self.assertIn('pending_release', self.channel.state)
        self.assertNotIn('last_attempt', self.channel.state)
        self.assertNotIn('transient_failure', self.channel.state)
        self.assertEqual(self.channel.stable, self.initial_stable)
        self.publisher.publish_release.side_effect = self._publish
        self.assertEqual(self._run(run_id='recovery', timestamp='2026-11-01T00:01:00Z')[0], 0)

    def test_pending_recovery_precedes_all_ordinary_skip_decisions(self):
        self.fail_partial_upload = True
        self.assertEqual(self._run()[0], 2)
        self.channel.state.update(
            last_successful={'manifest_id': '123', 'build_fingerprint': FINGERPRINT},
            last_attempt={'manifest_id': '123', 'build_fingerprint': FINGERPRINT, 'failure_count': 2},
            transient_failure={'manifest_id': None, 'build_fingerprint': FINGERPRINT,
                               'next_retry_at': '2099-01-01T00:00:00Z'})
        code, report = self._run(run_id='recovery')
        self.assertEqual(code, 0)
        self.assertTrue(report['recovering_publication'])
        self.probe_call.assert_not_called()
        build = next(call for call in self.commands.call_args_list if 'build.py' in call.args)
        self.assertEqual(build.args[-1], '123')
        self.assertEqual(len(self.publications), 2)
        self.assertNotIn('pending_release', self.channel.state)

    def test_repeated_recovery_failure_is_not_success_or_source_backoff(self):
        self.publisher.publish_release.side_effect = RuntimeError('[WinError 10060] upload timeout')
        for run in ('first', 'retry', 'retry-again'):
            code, report = self._run(run_id=run, timestamp='2026-11-01T00:00:00Z')
            self.assertEqual(code, 2)
            self.assertEqual(report['status'], 'publication_failed')
            self.assertEqual(report['failure_stage'], 'release_publish')
            self.assertNotIn('transient_failure', self.channel.state)
            self.assertNotIn('last_attempt', self.channel.state)
            self.assertIn('pending_release', self.channel.state)

    def test_channel_timeout_after_published_release_recovers_same_bytes(self):
        original_writer = self.publisher.write_channel.side_effect
        fail = True
        def write(stable, state, head, message):
            nonlocal fail
            if fail and message == 'Record verified Steam localization build':
                fail = False
                raise TimeoutError('channel write timeout')
            return original_writer(stable, state, head, message)
        self.publisher.write_channel.side_effect = write
        code, report = self._run()
        self.assertEqual(code, 2)
        self.assertEqual(report['failure_stage'], 'channel_commit')
        self.assertTrue(report['release_created'])
        self.assertNotIn('transient_failure', self.channel.state)
        original_bytes = dict(self.uploaded)
        self.assertEqual(self._run(run_id='recovery')[0], 0)
        self.assertEqual(self.uploaded, original_bytes)
        self.assertEqual(self.publications[0], self.publications[1])

    def test_recovery_staging_failure_is_visible_without_download_backoff(self):
        self.fail_partial_upload = True
        self.assertEqual(self._run()[0], 2)
        original = copy.deepcopy(self.channel.state)
        with patch.object(updater, 'stage_release', side_effect=RuntimeError('[WinError 10060] staging error')):
            code, report = self._run(run_id='recovery')
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'publication_failed')
        self.assertEqual(report['failure_stage'], 'release_staging')
        self.assertEqual(self.channel.state, original)

    def test_pending_recovery_refuses_changed_companion_with_unchanged_pak(self):
        self.fail_partial_upload = True
        self.assertEqual(self._run()[0], 2)
        original = copy.deepcopy(self.channel.state['pending_release'])
        changed = copy.deepcopy(self.companions)
        changed['ASA_RU_Fix_P.ucas']['sha256'] = '9' * 64
        code, report = self._run(run_id='recovery', companions=changed)
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'publication_failed')
        self.assertEqual(self.channel.state['pending_release'], original)
        self.assertEqual(len(self.publications), 1)

    def test_staging_rejects_unverified_companion_bytes(self):
        (self.root / 'dist' / 'ASA_RU_Fix_P.ucas').write_bytes(b'UCAS')  # same size, different SHA
        code, report = self._run()
        self.assertEqual(code, 2)
        self.assertEqual(report['failure_stage'], 'release_staging')
        self.assertIn('ASA_RU_Fix_P.ucas differs', report['error'])
        self.publisher.publish_release.assert_not_called()
        self.publisher.write_channel.assert_not_called()

    def test_legacy_pending_uses_original_single_pak_manifest_and_assets(self):
        original = {'steam': {'manifest_id': '123', 'app_id': '2430930', 'depot_id': '2430931', 'checked_at': 'old'},
                    'final_pak': {'path': updater.PAK_NAME, 'size': len(self.raw_pak), 'sha256': self.digest},
                    'build_fingerprint': '7' * 64, 'git_commit': FIRST_COMMIT, 'run_id': 'old'}
        self.channel.state['pending_release'] = {'version': '1.0.1', 'commit': FIRST_COMMIT, 'report': original}
        code, report = self._run(run_id='recovery', commit=NEXT_COMMIT)
        self.assertEqual(code, 0)
        version, commit, assets = self.publications[0]
        self.assertEqual((version, commit), ('1.0.1', FIRST_COMMIT))
        self.assertEqual({name for name in assets if name.startswith('ASA_RU_Fix_P.')}, {updater.PAK_NAME})
        self.assertNotIn('bundle', json.loads(assets['release-manifest.json']))
        self.assertEqual(json.loads(assets['live-build-report.json']), original)
        self.assertEqual(self.channel.stable['version'], '1.0.1')
        self.assertNotIn('pending_release', self.channel.state)

    def test_legacy_pending_cannot_take_reserved_first_bundle_version(self):
        self.channel.stable['version'] = '1.0.1'
        self.channel.stable['release']['tag'] = 'v1.0.1'
        self.channel.stable['artifact']['download_url'] = self.channel.stable['artifact']['download_url'].replace('v1.0.0', 'v1.0.1')
        pending = {'version': '1.0.2', 'commit': FIRST_COMMIT, 'report': {'build_fingerprint': FINGERPRINT}}
        self.channel.state['pending_release'] = pending
        code, report = self._run()
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'publication_failed')
        self.assertEqual(self.channel.state['pending_release'], pending)
        self.publisher.publish_release.assert_not_called()

    def test_offline_stage_cli_verifies_and_stages_without_network(self):
        stable_json, report_json = self.root / 'stable.json', self.root / 'verified.json'
        updater.write_json(stable_json, self.initial_stable)
        updater.write_json(report_json, {
            'git_commit': FIRST_COMMIT, 'steam': {'manifest_id': '123'},
            'final_pak': {'size': len(self.raw_pak), 'sha256': self.digest}, 'companions': self.companions,
            'tests': {'result': 'PASS'}, 'repak_validation': 'PASS',
            'placeholder_printf_richtext_validation': {'status': 'PASS', 'issues': 0},
            'translation_counts': {'shooter_desired': 1243, 'engine_desired': 21},
        })
        argv = ['auto_update', 'stage-bundle', '--repository', REPOSITORY,
                '--stable-json', str(stable_json), '--report', str(report_json),
                '--pak', str(self.root / 'dist' / updater.PAK_NAME)]
        with patch.object(sys, 'argv', argv), patch.object(updater, 'ROOT', self.root), \
             patch.object(updater, 'GitHubPublisher') as publisher, patch.object(updater, 'execute') as execute, \
             patch.object(updater, 'probe_manifest') as probe, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(updater.main(), 0)
        publisher.assert_not_called(); execute.assert_not_called(); probe.assert_not_called()
        staged = self.root / 'work/release-staging/v1.0.2'
        self.assertEqual({path.name for path in staged.iterdir()},
                         {*updater.BUNDLE_NAMES, 'release-manifest.json', 'cloud-build-report.json', 'SHA256SUMS.txt'})
        self.assertEqual(updater.read_json(staged / 'release-manifest.json')['bundle']['release']['commit'], FIRST_COMMIT)



if __name__ == '__main__':
    unittest.main()
