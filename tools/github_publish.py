"""GitHub channel commits and verified, resumable versioned releases via gh CLI.

Authentication is inherited from the caller's gh environment. This module never
reads or logs tokens, mutates gh authentication, or force-updates refs/assets.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

from tools.channel_state import next_version


BOT = {'name': 'github-actions[bot]',
       'email': '41898282+github-actions[bot]@users.noreply.github.com'}
PAK_NAME = 'ASA_RU_Fix_P.pak'


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class GitHubPublisher:
    def __init__(self, repository: str, run=subprocess.run):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('repository must be owner/repo')
        self.repository = repository
        self.run = run
        self.base = f'repos/{repository}/'

    def _execute(self, command: list[str], *, binary: bool = False):
        kwargs = {'capture_output': True}
        if not binary:
            kwargs.update(text=True, encoding='utf-8', errors='replace')
        result = self.run(command, **kwargs)
        if result.returncode:
            stderr = result.stderr.decode('utf-8', 'replace') if isinstance(result.stderr, bytes) else result.stderr
            matched = re.search(r'\bHTTP (\d{3})\b', stderr or '')
            status = int(matched.group(1)) if matched else None
            # gh stderr may contain environment-sensitive data; never echo it.
            raise GitHubError(f'GitHub command failed (HTTP {status})' if status else 'GitHub command failed', status)
        return result.stdout

    def _api(self, route: str, *, method: str = 'GET', body: dict | None = None,
             binary: bool = False):
        command = ['gh', 'api', self.base + route, '--method', method,
                   '--header', 'Accept: application/octet-stream' if binary else 'Accept: application/vnd.github+json']
        if body is None:
            raw = self._execute(command, binary=binary)
        else:
            # Structured JSON is read by gh, never interpolated into shell arguments.
            with tempfile.TemporaryDirectory(prefix='asa-gh-body-') as folder:
                request = Path(folder) / 'request.json'
                request.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
                raw = self._execute([*command, '--input', str(request)], binary=binary)
        if binary:
            if not isinstance(raw, bytes):
                raise GitHubError('GitHub asset download did not return bytes')
            return raw
        try:
            return json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise GitHubError('GitHub API returned invalid JSON') from exc

    def _optional(self, route: str):
        try:
            return self._api(route)
        except GitHubError as exc:
            if exc.status == 404:
                return None
            raise

    def _channel_sha(self) -> str | None:
        ref = self._optional('git/ref/heads/channel')
        return ref['object']['sha'] if ref else None

    def read_channel(self) -> tuple[dict, dict, str | None]:
        sha = self._channel_sha()
        if sha is None:
            return {}, {}, None
        records = []
        for filename in ('stable.json', 'automation.json'):
            payload = self._api(f'contents/{filename}?ref={quote(sha, safe="")}')
            if payload.get('encoding') != 'base64':
                raise GitHubError(f'channel {filename} has unsupported encoding')
            try:
                raw = base64.b64decode(''.join(payload['content'].split()), validate=True)
                record = json.loads(raw)
            except (ValueError, KeyError) as exc:
                raise GitHubError(f'channel {filename} is invalid') from exc
            if not isinstance(record, dict):
                raise GitHubError(f'channel {filename} must be a JSON object')
            records.append(record)
        return records[0], records[1], sha

    def write_channel(self, stable: dict, automation: dict, expected_sha: str | None,
                      message: str) -> str:
        if self._channel_sha() != expected_sha:
            raise GitHubError('channel ref changed; refusing stale write')
        tree_body = {'tree': []}
        if expected_sha:
            tree_body['base_tree'] = self._api(f'git/commits/{expected_sha}')['tree']['sha']
        for filename, record in (('stable.json', stable), ('automation.json', automation)):
            raw = (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
            blob = self._api('git/blobs', method='POST', body={
                'content': base64.b64encode(raw).decode('ascii'), 'encoding': 'base64'})
            tree_body['tree'].append({'path': filename, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
        tree = self._api('git/trees', method='POST', body=tree_body)
        commit = self._api('git/commits', method='POST', body={
            'message': message, 'tree': tree['sha'], 'parents': [expected_sha] if expected_sha else [],
            'author': BOT, 'committer': BOT})
        # Recheck after object creation. GitHub also rejects a divergent fast-forward
        # if a competing writer moves the ref between this read and PATCH.
        if self._channel_sha() != expected_sha:
            raise GitHubError('channel ref changed during commit creation')
        if expected_sha:
            self._api('git/refs/heads/channel', method='PATCH', body={'sha': commit['sha'], 'force': False})
        else:
            self._api('git/refs', method='POST', body={'ref': 'refs/heads/channel', 'sha': commit['sha']})
        return commit['sha']

    def get_release(self, tag: str) -> dict | None:
        return self._optional(f'releases/tags/{quote(tag, safe="")}')

    def _tag_commit(self, tag: str) -> str | None:
        ref = self._optional(f'git/ref/tags/{quote(tag, safe="")}')
        if ref is None:
            return None
        obj = ref['object']
        # Support existing annotated tags by peeling to a commit.
        seen = set()
        while obj['type'] == 'tag':
            if obj['sha'] in seen:
                raise GitHubError('cyclic release tag')
            seen.add(obj['sha'])
            obj = self._api(f'git/tags/{obj["sha"]}')['object']
        if obj['type'] != 'commit':
            raise GitHubError('release tag must point to a commit')
        return obj['sha']

    def _verify_assets(self, release: dict, expected: dict) -> list[Path]:
        seen = set()
        for asset in release.get('assets', []):
            name = asset['name']
            if name in seen or name not in expected:
                raise GitHubError(f'unexpected or duplicate release asset: {name}')
            seen.add(name)
            path, local_hash = expected[name]
            if asset.get('state') != 'uploaded' or asset.get('size') != path.stat().st_size:
                raise GitHubError(f'release asset size/state mismatch: {name}')
            digest = asset.get('digest')
            if digest:
                if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
                    raise GitHubError(f'invalid SHA-256 digest for release asset: {name}')
                actual = digest.split(':', 1)[1].lower()
            else:
                actual = hashlib.sha256(self._api(f'releases/assets/{asset["id"]}', binary=True)).hexdigest()
            if actual != local_hash:
                raise GitHubError(f'release asset SHA-256 mismatch: {name}')
        return [path for name, (path, _) in expected.items() if name not in seen]

    def publish_release(self, version: str, commit: str, assets: list[Path], *, notes: str) -> dict:
        next_version(version)  # validates without accepting prefixed/prerelease versions
        if not re.fullmatch(r'[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', commit):
            raise ValueError('release commit must be a full commit SHA')
        commit = commit.lower()
        expected = {}
        for path in map(Path, assets):
            if path.name in expected:
                raise ValueError(f'duplicate release asset name: {path.name}')
            if '#' in str(path):
                raise ValueError('release asset paths must not contain gh label separator #')
            expected[path.name] = (path, _file_hash(path))
        if PAK_NAME not in expected:
            raise ValueError(f'release requires {PAK_NAME}')
        tag = f'v{version}'
        tag_commit = self._tag_commit(tag)
        if tag_commit is not None and tag_commit != commit:
            raise GitHubError('release tag points to a different commit')
        release = self.get_release(tag)
        if release is not None and release.get('draft') and release.get('target_commitish') != commit:
            raise GitHubError('draft release targets a different commit')
        if release is not None and not release.get('draft') and tag_commit is None:
            raise GitHubError('published release is missing its commit tag')
        if tag_commit is None:
            try:
                self._api('git/refs', method='POST', body={'ref': f'refs/tags/{tag}', 'sha': commit})
            except GitHubError as exc:
                if exc.status != 422 or self._tag_commit(tag) != commit:
                    raise
        if release is None:
            release = self._api('releases', method='POST', body={
                'tag_name': tag, 'target_commitish': commit, 'name': tag,
                'body': notes, 'draft': True, 'prerelease': False})
        missing = self._verify_assets(release, expected)
        if not release.get('draft'):
            if missing:
                raise GitHubError('published release has missing assets; refusing mutation')
        else:
            if missing:
                self._execute(['gh', 'release', 'upload', tag, *[str(path.resolve()) for path in missing],
                               '--repo', self.repository])
            release = self._api(f'releases/{release["id"]}')
            if self._verify_assets(release, expected):
                raise GitHubError('draft release has missing assets after upload')
            if self._tag_commit(tag) != commit:
                raise GitHubError('release tag commit changed before publication')
            release = self._api(f'releases/{release["id"]}', method='PATCH', body={'draft': False})
        if release.get('draft') or not release.get('published_at'):
            raise GitHubError('release was not published')
        if self._tag_commit(tag) != commit:
            raise GitHubError('release tag commit changed')
        pak, digest = expected[PAK_NAME]
        return {'version': version, 'tag': tag, 'published_at': release['published_at'],
                'commit': commit, 'url': release['html_url'],
                'asset_url': f'https://github.com/{self.repository}/releases/download/{tag}/{PAK_NAME}',
                'sha256': digest, 'size': pak.stat().st_size, 'release_id': release['id']}
