"""Publish immutable updater releases and fast-forward only channel/client.json.

The server publisher remains untouched. Its gh transport and asset verification
are reused here as an adapter, with client-specific tags, assets and channel data.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from tools.client_build_report import (ASSET_NAMES, EXE_NAME, build_manifest,
                                       json_bytes, validate_project_version)
from tools.github_publish import BOT, GitHubError, GitHubPublisher, _file_hash


class ClientPublisher(GitHubPublisher):
    def publish_client_release(self, version: str, commit: str, assets: list[Path]) -> dict:
        expected = {}
        for path in map(Path, assets):
            if path.name in expected or path.name not in ASSET_NAMES or '#' in str(path):
                raise ValueError(f'unexpected or duplicate client release asset: {path.name}')
            expected[path.name] = (path, _file_hash(path))
        if set(expected) != set(ASSET_NAMES):
            raise ValueError('client release requires EXE, SHA256SUMS.txt and client-manifest.json')
        exe = expected[EXE_NAME][0]
        record = build_manifest(exe.parent, version, commit, self.repository)
        if expected['client-manifest.json'][0].read_bytes() != json_bytes(record):
            raise ValueError('client manifest does not match the binary and source provenance')
        if expected['SHA256SUMS.txt'][0].read_bytes() != f'{record["artifact"]["sha256"]}  {EXE_NAME}\n'.encode('ascii'):
            raise ValueError('SHA256SUMS.txt does not match client EXE')
        commit = record['release']['commit']
        tag = record['release']['tag']
        tag_commit = self._tag_commit(tag)
        if tag_commit is not None and tag_commit != commit:
            raise GitHubError('client release tag points to a different commit')
        release = self.get_release(tag)
        if release is not None:
            if release.get('prerelease'):
                raise GitHubError('client stable release cannot be a prerelease')
            if release.get('draft') and release.get('target_commitish') != commit:
                raise GitHubError('client draft release targets a different commit')
            if not release.get('draft') and tag_commit is None:
                raise GitHubError('published client release is missing its commit tag')
        if tag_commit is None:
            try:
                self._api('git/refs', method='POST', body={'ref': f'refs/tags/{tag}', 'sha': commit})
            except GitHubError as exc:
                if exc.status != 422 or self._tag_commit(tag) != commit:
                    raise
        if release is None:
            release = self._api('releases', method='POST', body={
                'tag_name': tag, 'target_commitish': commit, 'name': f'ASA RU Fix updater {version}',
                'body': 'Клиент Windows x64: скачайте ASA-RU-Fix.exe, запустите и нажмите «Установить».\n\n'
                        'EXE self-contained, установка .NET не требуется. Подпись отсутствует (unsigned); '
                        'Windows SmartScreen может показать предупреждение при первом запуске.',
                'draft': True, 'prerelease': False, 'make_latest': 'false'})
        missing = self._verify_assets(release, expected)
        if not release.get('draft'):
            if missing:
                raise GitHubError('published client release has missing assets; refusing mutation')
        else:
            if missing:
                self._execute(['gh', 'release', 'upload', tag, *[str(path.resolve()) for path in missing],
                               '--repo', self.repository])
            release = self._api(f'releases/{release["id"]}')
            if self._verify_assets(release, expected):
                raise GitHubError('client draft has missing assets after upload')
            self._verify_exe_download(release, record)
            if self._tag_commit(tag) != commit:
                raise GitHubError('client release tag changed before publication')
            release = self._api(f'releases/{release["id"]}', method='PATCH',
                                body={'draft': False, 'make_latest': 'false'})
        if release.get('draft') or not release.get('published_at'):
            raise GitHubError('client release was not published')
        if self._tag_commit(tag) != commit:
            raise GitHubError('client release tag commit changed')
        if self._verify_assets(release, expected):
            raise GitHubError('published client release has missing assets')
        self._verify_exe_download(release, record)
        record['release']['published_at'] = release['published_at']
        return record

    def _verify_exe_download(self, release: dict, record: dict) -> None:
        asset = next(row for row in release['assets'] if row['name'] == EXE_NAME)
        raw = self._api(f'releases/assets/{asset["id"]}', binary=True)
        if len(raw) != record['artifact']['size']:
            raise GitHubError('downloaded client EXE size mismatch')
        if hashlib.sha256(raw).hexdigest() != record['artifact']['sha256']:
            raise GitHubError('downloaded client EXE SHA-256 mismatch')

    def write_client_channel(self, record: dict, expected_sha: str) -> str:
        if self._channel_sha() != expected_sha:
            raise GitHubError('channel ref changed; refusing stale client write')
        if not expected_sha:
            raise GitHubError('existing channel branch is required for client publication')
        existing = self._optional(f'contents/client.json?ref={quote(expected_sha, safe="")}')
        if existing is not None:
            try:
                if existing.get('encoding') != 'base64':
                    raise ValueError('encoding')
                old = json.loads(base64.b64decode(''.join(existing['content'].split()), validate=True))
            except (ValueError, KeyError) as exc:
                raise GitHubError('existing client.json is invalid') from exc
            if old == record:
                return expected_sha
        base_tree = self._api(f'git/commits/{expected_sha}')['tree']['sha']
        blob = self._api('git/blobs', method='POST', body={
            'content': base64.b64encode(json_bytes(record)).decode('ascii'), 'encoding': 'base64'})
        tree = self._api('git/trees', method='POST', body={
            'base_tree': base_tree,
            'tree': [{'path': 'client.json', 'mode': '100644', 'type': 'blob', 'sha': blob['sha']}]})
        commit = self._api('git/commits', method='POST', body={
            'message': f'Publish verified updater client {record.get("version", "")}',
            'tree': tree['sha'], 'parents': [expected_sha], 'author': BOT, 'committer': BOT})
        if self._channel_sha() != expected_sha:
            raise GitHubError('channel ref changed during client commit creation')
        self._api('git/refs/heads/channel', method='PATCH', body={'sha': commit['sha'], 'force': False})
        return commit['sha']


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    validate = commands.add_parser('validate')
    publish = commands.add_parser('publish')
    for command in (validate, publish):
        command.add_argument('--project', type=Path, default=Path('client/Directory.Build.props'))
        command.add_argument('--version', required=True)
    publish.add_argument('--repository', required=True)
    publish.add_argument('--commit', required=True)
    publish.add_argument('--publish-dir', type=Path, required=True)
    publish.add_argument('--metadata-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    version = validate_project_version(args.project, args.version)
    if args.command == 'validate':
        print(version)
        return 0
    publisher = ClientPublisher(args.repository)
    assets = [args.publish_dir / EXE_NAME, args.metadata_dir / 'SHA256SUMS.txt',
              args.metadata_dir / 'client-manifest.json']
    record = publisher.publish_client_release(version, args.commit, assets)
    # Resolve channel only after the public release has passed every asset check.
    channel_sha = publisher.write_client_channel(record, publisher._channel_sha())
    output = args.metadata_dir / 'client-channel.json'
    output.write_bytes(json_bytes(record))
    print(json.dumps({'tag': record['release']['tag'], 'channel_commit': channel_sha,
                      'artifact': record['artifact']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
