"""Pure channel decisions and canonical identity of production build inputs."""

from __future__ import annotations

import copy
import hashlib
import re
import struct
from pathlib import Path


# Explicit production inputs: neither mtime nor docs, tests, audit or workflow schedules
# change the identity. Missing inputs are errors rather than an incomplete fingerprint.
BUILD_INPUTS = (
    '.gitattributes',
    'build.py',
    'tools/auto_update.py', 'tools/bootstrap.py', 'tools/channel_state.py',
    'tools/cloud_report.py', 'tools/corrections.py', 'tools/github_publish.py',
    'tools/locres.py', 'tools/manifest_probe.py', 'tools/oodle.py',
    'tools/ooz_bridge.cpp', 'tools/pak_order.py', 'tools/pakv12.py', 'tools/server_depot.py',
    'tools/steam.py', 'tools/translation_data.py',
    'data/shootergame_ru.json', 'data/engine_ru.json', 'data/source_identity.json',
)


def build_fingerprint(root: Path) -> str:
    """Hash sorted POSIX relative paths and bytes, each prefixed by uint64 length."""
    digest = hashlib.sha256()
    for name in sorted(BUILD_INPUTS):
        path = name.encode('utf-8')
        raw = (Path(root) / name).read_bytes()
        digest.update(struct.pack('>Q', len(path)))
        digest.update(path)
        digest.update(struct.pack('>Q', len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def _same_pair(record: dict | None, manifest: str, fingerprint: str) -> bool:
    return bool(record and record.get('manifest_id') == str(manifest)
                and record.get('build_fingerprint') == fingerprint)


def decide(state: dict, manifest: str, fingerprint: str, force: bool = False) -> dict:
    if force:
        return {'action': 'build', 'reason': 'forced'}
    if _same_pair(state.get('last_successful'), manifest, fingerprint):
        return {'action': 'skip', 'reason': 'already processed'}
    attempt = state.get('last_attempt')
    if _same_pair(attempt, manifest, fingerprint) and attempt.get('failure_count', 0) >= 2:
        return {'action': 'blocked', 'reason': 'two failed attempts for this input pair'}
    return {'action': 'build', 'reason': 'new or retryable input pair'}


def record_failure(state: dict, manifest: str, fingerprint: str, run_id: str,
                   reason: str, now: str) -> dict:
    result = copy.deepcopy(state)
    previous = state.get('last_attempt')
    count = previous.get('failure_count', 0) if _same_pair(previous, manifest, fingerprint) else 0
    attempts = previous.get('attempt_count', 0) if _same_pair(previous, manifest, fingerprint) else 0
    result['schema'] = 1
    result['last_attempt'] = {
        'manifest_id': str(manifest), 'build_fingerprint': fingerprint,
        'run_id': str(run_id), 'at': now, 'status': 'blocked' if count + 1 >= 2 else 'failed',
        'failure_count': count + 1, 'attempt_count': attempts + 1, 'reason': str(reason)[:4000],
    }
    return result


def record_success(state: dict, manifest: str, fingerprint: str, run_id: str,
                   stable: dict, now: str) -> dict:
    result = copy.deepcopy(state)
    previous = state.get('last_attempt')
    attempts = previous.get('attempt_count', 0) if _same_pair(previous, manifest, fingerprint) else 0
    pair = {'manifest_id': str(manifest), 'build_fingerprint': fingerprint,
            'run_id': str(run_id), 'at': now}
    result.update(schema=1, last_successful=copy.deepcopy(pair),
                  latest_release=copy.deepcopy(stable),
                  last_attempt={**pair, 'status': 'success', 'failure_count': 0,
                                'attempt_count': attempts + 1})
    return result


def next_version(previous_version: str) -> str:
    if not isinstance(previous_version, str) or not re.fullmatch(
            r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', previous_version):
        raise ValueError('version must be canonical x.y.z')
    major, minor, patch = map(int, previous_version.split('.'))
    return f'{major}.{minor}.{patch + 1}'
