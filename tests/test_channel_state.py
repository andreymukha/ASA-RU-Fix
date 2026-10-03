import copy
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from tools.channel_state import (
    BUILD_INPUTS, build_fingerprint, decide, next_version, record_failure, record_success,
)


class FingerprintTests(unittest.TestCase):
    def test_only_build_inputs_and_canonical_paths_and_bytes_are_hashed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            expected = hashlib.sha256()
            for name in sorted(BUILD_INPUTS):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = (name + '\n').encode()
                path.write_bytes(raw)
                relative = name.encode('utf-8')
                expected.update(struct.pack('>Q', len(relative)))
                expected.update(relative)
                expected.update(struct.pack('>Q', len(raw)))
                expected.update(raw)
            first = build_fingerprint(root)
            self.assertEqual(first, expected.hexdigest())
            for name in ('README.md', 'tests/test_build.py', 'tools/audit.py',
                         '.github/workflows/live_update.yml', 'work/current.pak'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'unrelated')
            self.assertEqual(first, build_fingerprint(root))
            (root / 'tools/translation_data.py').write_bytes(b'changed')
            self.assertNotEqual(first, build_fingerprint(root))

    def test_missing_build_input_is_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                build_fingerprint(Path(folder))


class ChannelStateTests(unittest.TestCase):
    def test_initial_pair_builds(self):
        self.assertEqual(decide({}, '123', 'fp')['action'], 'build')

    def test_success_is_skipped_and_does_not_mutate_input(self):
        state = {'extra': {'keep': True}}
        before = copy.deepcopy(state)
        result = record_success(state, '123', 'fp', 'run',
                                {'version': '1.2.3', 'tag': 'v1.2.3', 'sha256': 'pak'}, 'now')
        self.assertEqual(state, before)
        self.assertEqual(result['schema'], 1)
        self.assertEqual(result['last_successful']['manifest_id'], '123')
        self.assertEqual(result['latest_release']['sha256'], 'pak')
        self.assertEqual(decide(result, '123', 'fp')['action'], 'skip')
        self.assertEqual(decide(result, '124', 'fp')['action'], 'build')
        self.assertEqual(decide(result, '123', 'new-fp')['action'], 'build')
        self.assertEqual(decide(result, '123', 'fp', force=True)['action'], 'build')

    def test_second_consecutive_failure_blocks_same_pair(self):
        old = {'last_successful': {'manifest_id': 'old', 'build_fingerprint': 'old-fp'},
               'latest_release': {'version': '1.0.0', 'sha256': 'old-pak'}}
        before = copy.deepcopy(old)
        first = record_failure(old, '123', 'fp', '1', 'failed', 'now')
        self.assertEqual(old, before)
        self.assertEqual(first['last_attempt']['failure_count'], 1)
        self.assertEqual(first['last_attempt']['attempt_count'], 1)
        self.assertEqual(decide(first, '123', 'fp')['action'], 'build')
        second = record_failure(first, '123', 'fp', '2', 'failed again', 'later')
        self.assertEqual(second['last_attempt']['failure_count'], 2)
        self.assertEqual(second['last_attempt']['attempt_count'], 2)
        self.assertEqual(second['last_attempt']['status'], 'blocked')
        self.assertEqual(decide(second, '123', 'fp')['action'], 'blocked')
        self.assertEqual(second['last_successful'], old['last_successful'])
        self.assertEqual(second['latest_release'], old['latest_release'])
        self.assertEqual(decide(second, '123', 'fp', force=True)['action'], 'build')
        for manifest, fingerprint in [('124', 'fp'), ('123', 'new')]:
            self.assertEqual(decide(second, manifest, fingerprint)['action'], 'build')
            reset = record_failure(second, manifest, fingerprint, '3', 'error', 'later')
            self.assertEqual(reset['last_attempt']['failure_count'], 1)
            self.assertEqual(reset['last_attempt']['attempt_count'], 1)

    def test_success_resets_failure_counter_even_for_existing_release(self):
        state = record_failure({}, '123', 'fp', '1', 'bad', 'now')
        stable = {'version': '1.2.3', 'tag': 'v1.2.3', 'sha256': 'unchanged'}
        state = record_success(state, '123', 'fp', '2', stable, 'later')
        self.assertEqual(state['last_attempt']['failure_count'], 0)
        self.assertEqual(state['last_attempt']['attempt_count'], 2)
        self.assertEqual(state['latest_release'], stable)
        self.assertEqual(decide(state, '123', 'fp')['action'], 'skip')

    def test_attempt_count_includes_successes_and_resets_for_new_pair(self):
        state = record_success({}, '123', 'fp', '1', {'version': '1.0.0'}, 'now')
        self.assertEqual(state['last_attempt']['attempt_count'], 1)
        state = record_success(state, '123', 'fp', '2', {'version': '1.0.0'}, 'later')
        self.assertEqual(state['last_attempt']['attempt_count'], 2)
        state = record_failure(state, '123', 'fp', '3', 'failed', 'later')
        self.assertEqual(state['last_attempt']['attempt_count'], 3)
        self.assertEqual(state['last_attempt']['failure_count'], 1)
        state = record_success(state, '124', 'fp', '4', {'version': '1.0.1'}, 'later')
        self.assertEqual(state['last_attempt']['attempt_count'], 1)

    def test_package_order_is_a_build_input(self):
        self.assertIn('tools/pak_order.py', BUILD_INPUTS)

    def test_same_successful_pair_with_failed_forced_run_stays_processed(self):
        state = record_success({}, '123', 'fp', '1', {'version': '1.0.0'}, 'now')
        state = record_failure(state, '123', 'fp', '2', 'forced failed', 'later')
        self.assertEqual(decide(state, '123', 'fp')['action'], 'skip')

    def test_failure_reason_is_bounded_and_stable_is_copied(self):
        state = record_failure({}, '123', 'fp', '1', 'x' * 5000, 'now')
        self.assertEqual(len(state['last_attempt']['reason']), 4000)
        stable = {'version': '1.0.0', 'details': {'value': 'old'}}
        success = record_success(state, '123', 'fp', '2', stable, 'now')
        stable['details']['value'] = 'mutated'
        self.assertEqual(success['latest_release']['details']['value'], 'old')

    def test_patch_version_increment_and_validation(self):
        self.assertEqual(next_version('1.2.9'), '1.2.10')
        self.assertEqual(next_version('0.0.0'), '0.0.1')
        for invalid in ('v1.2.3', '1.2', '01.2.3', '1.2.-1', '1.2.3-beta', '1.2.3\n', None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                next_version(invalid)


if __name__ == '__main__':
    unittest.main()
