import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.github_publish import GitHubPublisher, GitHubError


COMMIT = 'a' * 40
OLD = 'b' * 40
NEW = 'c' * 40


class FakeGitHub:
    """In-memory gh boundary: tests never execute gh or contact GitHub."""
    def __init__(self):
        self.calls = []
        self.head = None
        self.tag = None
        self.release = None
        self.files = {'stable.json': {'version': '1.0.0'}, 'automation.json': {'schema': 1}}
        self.bodies = {}
        self.asset_bytes = {}
        self.race_after_commit = False
        self.fail_upload = False
        self.error_status = None
        self.bad_uploaded_digest = False
        self.race_tag = None
        self.ref_update_status = None

    def asset(self, name, raw, *, digest=True):
        asset_id = len(self.asset_bytes) + 1
        self.asset_bytes[asset_id] = raw
        result = {'id': asset_id, 'name': name, 'state': 'uploaded', 'size': len(raw),
                  'browser_download_url': f'https://github.com/owner/repo/releases/download/v1.0.1/{name}'}
        if digest:
            result['digest'] = 'sha256:' + hashlib.sha256(raw).hexdigest()
        return result

    def result(self, value, *, binary=False, status=None):
        if status:
            return SimpleNamespace(returncode=1, stdout=b'' if binary else '',
                                   stderr=(f'gh: error (HTTP {status})'.encode() if binary
                                           else f'gh: error (HTTP {status})'))
        return SimpleNamespace(returncode=0, stdout=value if binary else json.dumps(value),
                               stderr=b'' if binary else '')

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if args[:3] == ['gh', 'release', 'upload']:
            if self.fail_upload:
                return self.result(None, status=503)
            for filename in args[4:args.index('--repo')]:
                path = Path(filename)
                row = self.asset(path.name, path.read_bytes())
                if self.bad_uploaded_digest:
                    row['digest'] = 'sha256:' + '0' * 64
                self.release['assets'].append(row)
            return self.result({})
        if args[:2] != ['gh', 'api']:
            raise AssertionError(f'unexpected command {args}')
        endpoint = args[2]
        method = args[args.index('--method') + 1]
        binary = not kwargs.get('text', False)
        body = json.loads(Path(args[args.index('--input') + 1]).read_text(encoding='utf-8')) if '--input' in args else None
        self.bodies.setdefault(endpoint, []).append(body)
        if self.error_status:
            return self.result(None, binary=binary, status=self.error_status)
        prefix = 'repos/owner/repo/'
        route = endpoint.removeprefix(prefix)
        if method == 'GET' and route == 'git/ref/heads/channel':
            return self.result({'object': {'sha': self.head}}) if self.head else self.result(None, status=404)
        if method == 'GET' and route.startswith('contents/'):
            name, sha = route[len('contents/'):].split('?ref=')
            if sha != OLD:
                raise AssertionError('contents must use resolved SHA')
            self.head = NEW  # A moving branch cannot change the second JSON snapshot.
            return self.result({'encoding': 'base64', 'content': base64.b64encode(json.dumps(self.files[name]).encode()).decode()})
        if method == 'GET' and route == f'git/commits/{OLD}':
            return self.result({'tree': {'sha': 'tree-old'}})
        if method == 'POST' and route == 'git/blobs':
            return self.result({'sha': 'blob'})
        if method == 'POST' and route == 'git/trees':
            return self.result({'sha': 'tree-new'})
        if method == 'POST' and route == 'git/commits':
            if self.race_after_commit:
                self.head = NEW
            return self.result({'sha': COMMIT})
        if method == 'POST' and route == 'git/refs':
            if body['ref'].startswith('refs/tags/') and self.race_tag:
                self.tag = self.race_tag
                return self.result(None, status=422)
            if body['ref'] == 'refs/heads/channel':
                self.head = body['sha']
            else:
                self.tag = body['sha']
            return self.result({'object': {'sha': body['sha']}})
        if method == 'PATCH' and route == 'git/refs/heads/channel':
            if self.ref_update_status:
                return self.result(None, status=self.ref_update_status)
            self.head = body['sha']
            return self.result({'object': {'sha': self.head}})
        if method == 'GET' and route == 'git/ref/tags/v1.0.1':
            return self.result({'object': {'type': 'commit', 'sha': self.tag}}) if self.tag else self.result(None, status=404)
        if method == 'GET' and route == 'releases/tags/v1.0.1':
            return self.result(self.release) if self.release else self.result(None, status=404)
        if method == 'POST' and route == 'releases':
            self.release = {**body, 'id': 7, 'assets': [], 'published_at': None,
                            'html_url': 'https://github.com/owner/repo/releases/tag/v1.0.1'}
            return self.result(self.release)
        if method == 'GET' and route == 'releases/7':
            return self.result(self.release)
        if method == 'PATCH' and route == 'releases/7':
            self.release.update(body)
            self.release['published_at'] = '2026-10-03T00:00:00Z'
            return self.result(self.release)
        if method == 'GET' and route.startswith('releases/assets/'):
            return self.result(self.asset_bytes[int(route.rsplit('/', 1)[1])], binary=True)
        raise AssertionError(f'unexpected API {method} {route}')


class ChannelPublishingTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitHub()
        self.publisher = GitHubPublisher('owner/repo', run=self.fake)

    def test_missing_branch_returns_empty_state(self):
        self.assertEqual(self.publisher.read_channel(), ({}, {}, None))

    def test_both_json_files_use_the_exact_resolved_commit(self):
        self.fake.head = OLD
        stable, automation, sha = self.publisher.read_channel()
        self.assertEqual((stable, automation, sha), (self.fake.files['stable.json'], self.fake.files['automation.json'], OLD))

    def test_orphan_channel_initialization_and_bot_identity(self):
        sha = self.publisher.write_channel({'version': '1.0.1'}, {'schema': 1}, None, 'init\nchannel')
        self.assertEqual(sha, COMMIT)
        body = self.fake.bodies['repos/owner/repo/git/commits'][0]
        self.assertEqual(body['parents'], [])
        self.assertEqual(body['author']['name'], 'github-actions[bot]')
        self.assertEqual(body['author']['email'], '41898282+github-actions[bot]@users.noreply.github.com')
        self.assertEqual(body['committer'], body['author'])

    def test_existing_channel_preserves_tree_and_fast_forwards(self):
        self.fake.head = OLD
        self.publisher.write_channel({}, {}, OLD, 'update')
        self.assertEqual(self.fake.bodies['repos/owner/repo/git/trees'][0]['base_tree'], 'tree-old')
        self.assertEqual(self.fake.bodies['repos/owner/repo/git/commits'][0]['parents'], [OLD])
        self.assertEqual(self.fake.bodies['repos/owner/repo/git/refs/heads/channel'][0], {'sha': COMMIT, 'force': False})

    def test_stale_head_refused_before_writes(self):
        self.fake.head = NEW
        with self.assertRaisesRegex(GitHubError, 'changed'):
            self.publisher.write_channel({}, {}, OLD, 'stale')
        self.assertFalse(any('--input' in args for args, _ in self.fake.calls))

    def test_race_during_commit_creation_refuses_ref_update(self):
        self.fake.head = OLD
        self.fake.race_after_commit = True
        with self.assertRaisesRegex(GitHubError, 'changed'):
            self.publisher.write_channel({}, {}, OLD, 'raced')
        self.assertNotIn('repos/owner/repo/git/refs/heads/channel', self.fake.bodies)
        self.assertEqual(self.fake.head, NEW)

    def test_orphan_race_refuses_initial_branch_creation(self):
        self.fake.race_after_commit = True
        with self.assertRaisesRegex(GitHubError, 'changed'):
            self.publisher.write_channel({}, {}, None, 'raced orphan')
        self.assertNotIn('repos/owner/repo/git/refs', self.fake.bodies)

    def test_api_rejection_during_final_ref_update_is_propagated(self):
        self.fake.head = OLD
        self.fake.ref_update_status = 422
        with self.assertRaises(GitHubError) as caught:
            self.publisher.write_channel({}, {}, OLD, 'raced update')
        self.assertEqual(caught.exception.status, 422)
        self.assertEqual(self.fake.head, OLD)

    def test_only_404_is_missing_release_or_channel(self):
        self.fake.error_status = 403
        with self.assertRaises(GitHubError):
            self.publisher.get_release('v1.0.1')
        with self.assertRaises(GitHubError):
            self.publisher.read_channel()


class ReleasePublishingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.assets = []
        for name in ('ASA_RU_Fix_P.pak', 'release-manifest.json', 'SHA256SUMS', 'live-report.json'):
            path = Path(self.folder.name) / name
            path.write_bytes(('bytes-' + name).encode())
            self.assets.append(path)
        self.fake = FakeGitHub()
        self.publisher = GitHubPublisher('owner/repo', run=self.fake)

    def publish(self):
        return self.publisher.publish_release('1.0.1', COMMIT, self.assets, notes='verified report\n')

    def existing(self, *, draft=False, digest=True):
        self.fake.tag = COMMIT
        self.fake.release = {'id': 7, 'tag_name': 'v1.0.1', 'target_commitish': COMMIT,
                             'draft': draft, 'published_at': None if draft else 'now',
                             'html_url': 'https://github.com/owner/repo/releases/tag/v1.0.1',
                             'assets': [self.fake.asset(p.name, p.read_bytes(), digest=digest) for p in self.assets]}

    def test_draft_upload_verify_then_publish_and_metadata(self):
        metadata = self.publish()
        self.assertEqual(metadata['version'], '1.0.1')
        self.assertEqual(metadata['commit'], COMMIT)
        self.assertEqual(metadata['sha256'], hashlib.sha256(self.assets[0].read_bytes()).hexdigest())
        self.assertEqual(metadata['asset_url'], 'https://github.com/owner/repo/releases/download/v1.0.1/ASA_RU_Fix_P.pak')
        self.assertTrue(self.fake.bodies['repos/owner/repo/releases'][0]['draft'])
        self.assertFalse(self.fake.release['draft'])
        self.assertFalse(any('--clobber' in args for args, _ in self.fake.calls))

    def test_public_identical_release_is_reused_without_writes(self):
        self.existing()
        self.publish()
        self.assertFalse(any('--input' in args or args[1] == 'release' for args, _ in self.fake.calls))

    def test_public_release_without_digest_is_actually_downloaded(self):
        self.existing(digest=False)
        self.publish()
        downloads = [args for args, _ in self.fake.calls if '/releases/assets/' in args[2]]
        self.assertEqual(len(downloads), 4)
        self.assertTrue(all('Accept: application/octet-stream' in args for args in downloads))

    def test_resume_draft_uploads_missing_files_only(self):
        self.existing(draft=True)
        self.fake.release['assets'] = self.fake.release['assets'][:1]
        self.publish()
        uploads = [args for args, _ in self.fake.calls if args[1] == 'release']
        self.assertEqual(len(uploads), 1)
        self.assertNotIn(str(self.assets[0]), uploads[0])
        self.assertFalse(self.fake.release['draft'])

    def test_failed_upload_leaves_draft_and_retry_resumes(self):
        self.fake.fail_upload = True
        with self.assertRaises(GitHubError):
            self.publish()
        self.assertTrue(self.fake.release['draft'])
        self.fake.fail_upload = False
        self.publish()
        self.assertEqual(len(self.fake.bodies['repos/owner/repo/releases']), 1)
        self.assertFalse(self.fake.release['draft'])

    def test_mismatching_existing_asset_refused_before_upload_or_publish(self):
        self.existing(draft=True)
        self.fake.release['assets'][0]['digest'] = 'sha256:' + '0' * 64
        with self.assertRaisesRegex(GitHubError, 'SHA-256'):
            self.publish()
        self.assertTrue(self.fake.release['draft'])
        self.assertFalse(any(args[1] == 'release' for args, _ in self.fake.calls))

    def test_mismatching_download_refused(self):
        self.existing(digest=False)
        self.fake.asset_bytes[1] = b'corrupt'
        with self.assertRaisesRegex(GitHubError, 'SHA-256'):
            self.publish()

    def test_mismatching_uploaded_digest_never_publishes(self):
        self.fake.bad_uploaded_digest = True
        with self.assertRaisesRegex(GitHubError, 'SHA-256'):
            self.publish()
        self.assertTrue(self.fake.release['draft'])

    def test_existing_public_missing_asset_refused(self):
        self.existing()
        self.fake.release['assets'].pop()
        with self.assertRaisesRegex(GitHubError, 'missing'):
            self.publish()
        self.assertFalse(any(args[1] == 'release' for args, _ in self.fake.calls))

    def test_wrong_tag_commit_is_never_reused(self):
        self.existing()
        self.fake.tag = OLD
        with self.assertRaisesRegex(GitHubError, 'commit'):
            self.publish()

    def test_duplicate_asset_names_and_invalid_version_fail_locally(self):
        with self.assertRaises(ValueError):
            self.publisher.publish_release('1.0.1', COMMIT, self.assets + [self.assets[0]], notes='')
        with self.assertRaises(ValueError):
            self.publisher.publish_release('v1.0.1', COMMIT, self.assets, notes='')
        self.assertEqual(self.fake.calls, [])

    def test_malformed_digest_and_unexpected_assets_fail_closed(self):
        self.existing(draft=True)
        self.fake.release['assets'][0]['digest'] = 'sha256:not-a-hash'
        with self.assertRaisesRegex(GitHubError, 'invalid SHA-256'):
            self.publish()
        self.existing(draft=True)
        self.fake.release['assets'].append(self.fake.asset('unexpected.txt', b'extra'))
        with self.assertRaisesRegex(GitHubError, 'unexpected'):
            self.publish()
        self.assertTrue(self.fake.release['draft'])

    def test_draft_with_wrong_target_commit_is_refused(self):
        self.existing(draft=True)
        self.fake.release['target_commitish'] = OLD
        with self.assertRaisesRegex(GitHubError, 'different commit'):
            self.publish()
        self.assertTrue(self.fake.release['draft'])

    def test_matching_tag_creation_race_is_reused(self):
        self.fake.race_tag = COMMIT
        self.publish()
        self.assertFalse(self.fake.release['draft'])

    def test_different_tag_creation_race_refuses_release_creation(self):
        self.fake.race_tag = OLD
        with self.assertRaises(GitHubError):
            self.publish()
        self.assertIsNone(self.fake.release)


if __name__ == '__main__':
    unittest.main()
