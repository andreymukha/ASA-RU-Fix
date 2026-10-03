"""Recovery fixtures use real staged bytes and mocked external boundaries only."""

import copy
import contextlib
import hashlib
import io
import json
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

    def _run(self, *, run_id='first-run', commit=FIRST_COMMIT, timestamp='first-time'):
        probe = {'app_id': '2430930', 'depot_id': '2430931', 'manifest_id': '123', 'checked_at': timestamp}
        report = {
            'timestamp_utc': timestamp, 'run_id': run_id, 'git_commit': commit,
            'steam': probe, 'source': {'pak_size': 123, 'pak_sha256': 'e' * 64},
            'stock_locres': {}, 'build_fingerprint': FINGERPRINT, 'pak_changed': True,
            'final_pak': {'path': updater.PAK_NAME, 'size': len(self.raw_pak), 'sha256': self.digest},
        }
        with patch.object(updater, 'build_fingerprint', return_value=FINGERPRINT), \
             patch.object(updater.subprocess, 'check_output', return_value=commit), \
             patch.object(updater, 'execute'), \
             patch.object(updater, 'probe_manifest', return_value=probe), \
             patch.object(updater, 'run_tests', return_value={'result': 'PASS', 'count': 100}), \
             patch.object(updater, 'make_live_report', return_value=report), \
             patch.object(updater, 'utc_now', return_value=timestamp), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = updater.run_update(self.root, REPOSITORY, self.publisher, run_id=run_id)
        live = updater.read_json(self.root / 'work/live-build-report.json')
        return result, live

    def test_published_release_channel_failure_preserves_pending_and_true_report(self):
        self.fail_success_write = True
        result, report = self._run()
        self.assertEqual(result, 2)
        self.assertEqual(self.channel.stable, self.initial_stable)
        self.assertIn('pending_release', self.channel.state)
        self.assertEqual(self.channel.state['pending_release']['commit'], FIRST_COMMIT)
        self.assertEqual(self.channel.state['last_attempt']['failure_count'], 1)
        self.assertTrue(report['release_created'])
        self.assertEqual(report['published_release'], self.published_metadata)
        self.assertEqual(report['status'], 'failed')
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
        self.assertEqual(self.channel.stable['release']['commit'], FIRST_COMMIT)
        self.assertNotIn('pending_release', self.channel.state)
        self.assertEqual(self.channel.state['last_successful']['run_id'], 'second-run')

    def test_public_release_retry_clears_pending_only_after_successful_channel_commit(self):
        self.fail_success_write = True
        self.assertEqual(self._run()[0], 2)
        self.assertIn('pending_release', self.channel.state)
        self.assertEqual(self._run(run_id='recovery', commit=NEXT_COMMIT, timestamp='recovery-time')[0], 0)
        self.assertEqual(self.publications[0], self.publications[1])
        self.assertNotIn('pending_release', self.channel.state)
        self.assertEqual(self.channel.stable['version'], '1.0.1')
        self.assertEqual(self.channel.state['last_attempt']['failure_count'], 0)
        self.assertEqual(self.channel.state['last_attempt']['attempt_count'], 2)
        self.assertEqual(self.channel.writes[-1][2], 'Record verified Steam localization build')


if __name__ == '__main__':
    unittest.main()
