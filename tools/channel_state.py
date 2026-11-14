"""Pure channel decisions and canonical identity of production build inputs."""

from __future__ import annotations

import copy
import hashlib
import re
import struct
from pathlib import Path
from datetime import datetime, timedelta, timezone


PAK_NAME = 'ASA_RU_Fix_P.pak'
COMPANION_NAMES = ('ASA_RU_Fix_P.utoc', 'ASA_RU_Fix_P.ucas')
BUNDLE_NAMES = (PAK_NAME, *COMPANION_NAMES)


# Explicit production inputs: neither mtime nor docs, tests, audit or workflow schedules
# change the identity. Missing inputs are errors rather than an incomplete fingerprint.
BUILD_INPUTS = (
    '.gitattributes',
    'build.py',
    'tools/auto_update.py', 'tools/bootstrap.py', 'tools/channel_state.py',
    'tools/cloud_report.py', 'tools/corrections.py', 'tools/github_publish.py', 'tools/iostore_companions.py',
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


def decide(state: dict, manifest: str, fingerprint: str, force: bool = False, *, now: str | None = None) -> dict:
    if force:
        return {'action': 'build', 'reason': 'forced'}
    if _same_pair(state.get('last_successful'), manifest, fingerprint):
        return {'action': 'skip', 'reason': 'already processed'}
    attempt = state.get('last_attempt')
    if _same_pair(attempt, manifest, fingerprint) and attempt.get('failure_count', 0) >= 2:
        return {'action': 'blocked', 'reason': 'two failed attempts for this input pair'}
    delay = backoff(state, manifest, fingerprint, now)
    if delay:
        return delay
    return {'action': 'build', 'reason': 'new or retryable input pair'}


def backoff(state: dict, manifest: str | None, fingerprint: str, now: str | None = None) -> dict | None:
    failure = state.get('transient_failure')
    if (not failure or failure.get('manifest_id') != manifest
            or failure.get('build_fingerprint') != fingerprint):
        return None
    current = datetime.fromisoformat(now.replace('Z', '+00:00')) if now else datetime.now(timezone.utc)
    if current < datetime.fromisoformat(failure['next_retry_at'].replace('Z', '+00:00')):
        return {'action': 'backoff', 'reason': 'transient network failure; check deferred',
                'next_retry_at': failure['next_retry_at']}
    return None


def record_transient_failure(state: dict, manifest: str | None, fingerprint: str,
                             run_id: str, reason: str, now: str) -> dict:
    result = copy.deepcopy(state)
    previous = state.get('transient_failure') or {}
    same = previous.get('manifest_id') == manifest and previous.get('build_fingerprint') == fingerprint
    count = previous.get('failure_count', 0) + 1 if same else 1
    seconds = min(1800 * 2 ** min(count - 1, 4), 21600)
    retry = datetime.fromisoformat(now.replace('Z', '+00:00')) + timedelta(seconds=seconds)
    result['schema'] = 1
    result['transient_failure'] = {
        'manifest_id': manifest, 'build_fingerprint': fingerprint, 'run_id': str(run_id),
        'at': now, 'status': 'backoff', 'failure_count': count, 'reason': str(reason)[:4000],
        'next_retry_at': retry.isoformat().replace('+00:00', 'Z'),
    }
    return result


def record_failure(state: dict, manifest: str, fingerprint: str, run_id: str,
                   reason: str, now: str) -> dict:
    result = copy.deepcopy(state)
    previous = state.get('last_attempt')
    count = previous.get('failure_count', 0) if _same_pair(previous, manifest, fingerprint) else 0
    attempts = previous.get('attempt_count', 0) if _same_pair(previous, manifest, fingerprint) else 0
    result.pop('transient_failure', None)
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
    result.pop('transient_failure', None)
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


def artifact_identity(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError('invalid artifact: expected an object')
    size, digest = record.get('size'), record.get('sha256')
    if (type(size) is not int or size <= 0 or not isinstance(digest, str)
            or not re.fullmatch(r'[0-9a-f]{64}', digest)):
        raise ValueError('invalid artifact size or SHA-256')
    return {'size': size, 'sha256': digest}


def bundle_identities(report: dict) -> dict:
    companions = report.get('companions')
    if not isinstance(companions, dict) or set(companions) != set(COMPANION_NAMES):
        raise ValueError('verified bundle requires exactly the .utoc and .ucas companions')
    return {PAK_NAME: artifact_identity(report['final_pak']),
            **{name: artifact_identity(companions[name]) for name in COMPANION_NAMES}}
