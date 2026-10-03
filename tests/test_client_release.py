import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.client_build_report import create_build_assets, validate_project_version
from tools.client_release import ClientPublisher, main
from tools.github_publish import GitHubError


COMMIT = 'a' * 40
OTHER = 'b' * 40


class FakeGitHub:
    """Mock the gh process boundary; never contact GitHub or create a release."""
    def __init__(self):
        self.calls = []
        self.tag = None
        self.release = None
        self.asset_bytes = {}
        self.bad_upload = False
        self.fail_upload = False
        self.race_tag = None

    def reply(self, value, binary=False, status=None):
        if status:
            error = f'gh error (HTTP {status})'
            return SimpleNamespace(returncode=1, stdout=b'' if binary else '',
                                   stderr=error.encode() if binary else error)
        return SimpleNamespace(returncode=0, stdout=value if binary else json.dumps(value),
                               stderr=b'' if binary else '')

    def __call__(self, args, **kwargs):
        body = json.loads(Path(args[args.index('--input') + 1]).read_text(encoding='utf-8')) if '--input' in args else None
        self.calls.append((args, body))
        if args[:3] == ['gh', 'release', 'upload']:
            if self.fail_upload:
                return self.reply(None, status=503)
            for filename in args[4:args.index('--repo')]:
                path = Path(filename)
                raw = path.read_bytes()
                if self.bad_upload and path.name == 'ASA-RU-Fix.exe':
                    raw = b'X' * len(raw)
                asset_id = len(self.asset_bytes) + 1
                self.asset_bytes[asset_id] = raw
                self.release['assets'].append({
                    'id': asset_id, 'name': path.name, 'size': len(raw), 'state': 'uploaded',
                    'digest': 'sha256:' + hashlib.sha256(raw).hexdigest()})
            return self.reply({})
        self.assert_command(args)
        route = args[2].removeprefix('repos/owner/repo/')
        method = args[args.index('--method') + 1]
        binary = not kwargs.get('text', False)
        if method == 'GET' and route == 'git/ref/tags/updater-v1.0.0':
            return self.reply({'object': {'type': 'commit', 'sha': self.tag}}) if self.tag else self.reply(None, status=404)
        if method == 'GET' and route == 'releases/tags/updater-v1.0.0':
            return self.reply(self.release) if self.release else self.reply(None, status=404)
        if method == 'POST' and route == 'git/refs':
            if self.race_tag:
                self.tag = self.race_tag
                return self.reply(None, status=422)
            self.tag = body['sha']
            return self.reply({})
        if method == 'POST' and route == 'releases':
            self.release = {**body, 'id': 7, 'assets': [], 'published_at': None,
                            'html_url': 'https://github.com/owner/repo/releases/tag/updater-v1.0.0'}
            return self.reply(self.release)
        if method == 'GET' and route == 'releases/7':
            return self.reply(self.release)
        if method == 'PATCH' and route == 'releases/7':
            self.release.update(body)
            self.release['published_at'] = '2026-10-03T00:00:00Z'
            return self.reply(self.release)
        if method == 'GET' and route.startswith('releases/assets/'):
            return self.reply(self.asset_bytes[int(route.rsplit('/', 1)[1])], binary=binary)
        raise AssertionError(f'unexpected API {method} {route}')

    def assert_command(self, args):
        if args[:2] != ['gh', 'api']:
            raise AssertionError(f'unexpected command {args}')


class BuildAssetsTests(unittest.TestCase):
    def test_version_matches_project_exactly_and_rejects_invalid_input(self):
        with tempfile.TemporaryDirectory() as folder:
            props = Path(folder) / 'Directory.Build.props'
            props.write_text('<Project><PropertyGroup><Version>1.0.0</Version></PropertyGroup></Project>')
            self.assertEqual(validate_project_version(props, '1.0.0'), '1.0.0')
            for version in ('v1.0.0', '01.0.0', '1.0', '1.0.0-rc.1', '1.0.1', '1.0.0\n'):
                with self.subTest(version=version), self.assertRaises(ValueError):
                    validate_project_version(props, version)

    def test_report_is_deterministic_and_user_folder_contains_only_exe(self):
        with tempfile.TemporaryDirectory() as folder:
            publish = Path(folder) / 'publish'
            publish.mkdir()
            exe = publish / 'ASA-RU-Fix.exe'
            exe.write_bytes(b'MZ fixture exe')
            destination = Path(folder) / 'metadata'
            paths = create_build_assets(publish, destination, '1.0.0', COMMIT, 'owner/repo')
            first = {path.name: path.read_bytes() for path in paths}
            create_build_assets(publish, destination, '1.0.0', COMMIT, 'owner/repo')
            self.assertEqual(first, {path.name: path.read_bytes() for path in paths})
            self.assertEqual([path.name for path in publish.iterdir()], ['ASA-RU-Fix.exe'])
            manifest = json.loads(first['client-manifest.json'])
            self.assertEqual(manifest['release'], {'commit': COMMIT, 'tag': 'updater-v1.0.0'})
            self.assertEqual(manifest['artifact']['sha256'], hashlib.sha256(exe.read_bytes()).hexdigest())
            self.assertEqual(manifest['build']['sdk'], '10.0.401')
            self.assertEqual(manifest['build']['signing'], 'unsigned')
            self.assertNotIn('published_at', manifest['release'])
            self.assertEqual(first['SHA256SUMS.txt'], (manifest['artifact']['sha256'] + '  ASA-RU-Fix.exe\n').encode())
            (publish / 'clutter.dll').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                create_build_assets(publish, destination, '1.0.0', COMMIT, 'owner/repo')


class ClientReleaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.publish = Path(self.folder.name) / 'publish'
        self.publish.mkdir()
        self.exe = self.publish / 'ASA-RU-Fix.exe'
        self.exe.write_bytes(b'MZ fixture exe')
        self.assets = [self.exe, *create_build_assets(self.publish, Path(self.folder.name) / 'metadata',
                                                    '1.0.0', COMMIT, 'owner/repo')]
        self.fake = FakeGitHub()
        self.publisher = ClientPublisher('owner/repo', run=self.fake)

    def release(self):
        return self.publisher.publish_client_release('1.0.0', COMMIT, self.assets)

    def test_new_release_verifies_assets_before_publication_and_is_never_latest(self):
        manifest = self.release()
        self.assertEqual(self.fake.tag, COMMIT)
        self.assertEqual(manifest['schema'], 1)
        self.assertEqual(manifest['release']['tag'], 'updater-v1.0.0')
        self.assertEqual(manifest['artifact']['size'], self.exe.stat().st_size)
        self.assertEqual(manifest['artifact']['download_url'],
                         'https://github.com/owner/repo/releases/download/updater-v1.0.0/ASA-RU-Fix.exe')
        mutations = [(args[2], body) for args, body in self.fake.calls if body is not None]
        self.assertTrue(all(body['make_latest'] == 'false' for route, body in mutations if '/releases' in route))
        downloads = [i for i, (args, _) in enumerate(self.fake.calls) if '/releases/assets/' in args[2]]
        publication = next(i for i, (args, body) in enumerate(self.fake.calls) if body and body.get('draft') is False)
        self.assertTrue(any(i < publication for i in downloads))
        self.assertTrue(any(i > publication for i in downloads))
        self.assertFalse(any('--clobber' in args for args, _ in self.fake.calls))

    def test_identical_published_release_retry_has_no_mutations(self):
        first = self.release()
        self.fake.calls.clear()
        self.assertEqual(self.release(), first)
        self.assertFalse(any(body is not None or args[:3] == ['gh', 'release', 'upload']
                             for args, body in self.fake.calls))

    def test_uploaded_hash_mismatch_never_publishes(self):
        self.fake.bad_upload = True
        with self.assertRaisesRegex(GitHubError, 'SHA-256'):
            self.release()
        self.assertTrue(self.fake.release['draft'])

    def test_asset_bytes_are_verified_even_when_digest_claims_success(self):
        self.release()
        exe_id = next(asset['id'] for asset in self.fake.release['assets'] if asset['name'] == self.exe.name)
        self.fake.asset_bytes[exe_id] = b'X' * self.exe.stat().st_size
        with self.assertRaisesRegex(GitHubError, 'SHA-256'):
            self.release()

    def test_existing_tag_different_commit_refuses_all_writes(self):
        self.fake.tag = OTHER
        with self.assertRaisesRegex(GitHubError, 'different commit'):
            self.release()
        self.assertFalse(any(body for _, body in self.fake.calls))

    def test_published_assets_cannot_be_changed_or_added(self):
        self.release()
        self.exe.write_bytes(b'MZ changed exe')
        with self.assertRaises((GitHubError, ValueError)):
            self.release()
        self.assertFalse(any('--clobber' in args for args, _ in self.fake.calls))

    def test_draft_upload_failure_is_resumable_without_tag_overwrite(self):
        self.fake.fail_upload = True
        with self.assertRaises(GitHubError):
            self.release()
        self.assertTrue(self.fake.release['draft'])
        self.fake.fail_upload = False
        self.release()
        refs = [body for args, body in self.fake.calls if args[2].endswith('/git/refs')]
        self.assertEqual(len(refs), 1)

    def test_tag_creation_race_only_accepts_exact_commit(self):
        self.fake.race_tag = OTHER
        with self.assertRaises(GitHubError):
            self.release()
        self.assertIsNone(self.fake.release)
        self.fake.tag = None
        self.fake.race_tag = COMMIT
        self.release()

    def test_required_metadata_is_checked_against_binary_before_github_writes(self):
        self.assets[1].write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.release()
        self.assertEqual(self.fake.calls, [])

    def test_failed_release_cannot_update_channel(self):
        props = Path(self.folder.name) / 'Directory.Build.props'
        props.write_text('<Project><PropertyGroup><Version>1.0.0</Version></PropertyGroup></Project>')
        with patch('tools.client_release.ClientPublisher') as publisher_class:
            publisher_class.return_value.publish_client_release.side_effect = GitHubError('SHA-256 mismatch')
            with self.assertRaises(GitHubError):
                main(['publish', '--project', str(props), '--version', '1.0.0', '--repository', 'owner/repo',
                      '--commit', COMMIT, '--publish-dir', str(self.publish),
                      '--metadata-dir', str(self.assets[1].parent)])
            publisher_class.return_value.write_client_channel.assert_not_called()
            publisher_class.return_value._channel_sha.assert_not_called()


class WorkflowContractTests(unittest.TestCase):
    def test_client_workflows_keep_manual_trigger_pinned_sdk_and_serialized_channel_writer(self):
        root = Path(__file__).resolve().parents[1]
        build = (root / '.github/workflows/client-build.yml').read_text(encoding='utf-8')
        release = (root / '.github/workflows/client-release.yml').read_text(encoding='utf-8')
        for workflow in (build, release):
            self.assertIn('workflow_dispatch:', workflow)
            self.assertNotIn('schedule:', workflow)
            self.assertIn('working-directory: client', workflow)
            self.assertIn('26b0ec14cb23fa6904739307f278c14f94c95bf1', workflow)
            self.assertIn('dotnet-version: "10.0.401"', workflow)
            self.assertIn('tests/ChildProbe/ChildProbe.csproj', workflow)
            self.assertIn('dotnet test', workflow)
            self.assertIn('RuntimeFrameworkVersion=10.0.12', workflow)
            self.assertIn('DOTNET_CLI_TELEMETRY_OPTOUT: "1"', workflow)
        self.assertIn('contents: read', build)
        self.assertIn('contents: write', release)
        server = (root / '.github/workflows/auto-update.yml').read_text(encoding='utf-8')
        for workflow in (server, release):
            self.assertIn('group: asa-ru-fix-live-update', workflow)
            self.assertIn('cancel-in-progress: false', workflow)
        self.assertIn('GH_TOKEN: ${{ github.token }}', release)
        self.assertNotIn('secrets.', release)


if __name__ == '__main__':
    unittest.main()
