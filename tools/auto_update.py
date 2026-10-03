"""Verified Steam-to-Release automation; no local game installation or launch."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.channel_state import build_fingerprint, decide, next_version, record_failure, record_success
from tools.cloud_report import make_live_report, run_tests
from tools.github_publish import GitHubPublisher, PAK_NAME
from tools.manifest_probe import probe_manifest
from tools.server_depot import EXPECTED_PAK_SHA256, EXPECTED_PAK_SIZE, PINNED_MANIFEST, file_sha256

ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def execute(root: Path, *args: str) -> None:
    """Preserve native failure code in logs, raising before subsequent steps."""
    result = subprocess.run(list(args), cwd=root, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    output = result.stdout + result.stderr
    log = root / 'work/live-process.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8') as stream:
        stream.write(f'COMMAND: {args!r}\n{output}\nEXIT: {result.returncode}\n')
    print(output, end='', flush=True)
    if result.returncode:
        raise RuntimeError(f'command failed with exit {result.returncode}: {args!r}')


def validate_channel(stable: dict, state: dict, repository: str) -> None:
    if stable.get('schema') != 1 or stable.get('channel') != 'stable' or state.get('schema') != 1:
        raise ValueError('channel schema is missing or unsupported; initialize verified baseline first')
    next_version(stable['version'])
    release, artifact = stable['release'], stable['artifact']
    expected_url = f'https://github.com/{repository}/releases/download/v{stable["version"]}/{PAK_NAME}'
    if (release['tag'] != 'v' + stable['version'] or artifact['filename'] != PAK_NAME
            or artifact['download_url'] != expected_url
            or not re.fullmatch(r'[0-9a-f]{64}', artifact['sha256'])
            or type(artifact['size']) is not int or artifact['size'] <= 0
            or not re.fullmatch(r'[0-9a-f]{40}', release['commit'])
            or not release.get('published_at')
            or stable['build'].get('shooter_desired') != 1243
            or stable['build'].get('engine_desired') != 21):
        raise ValueError('invalid trusted stable channel metadata')


def latest_release(stable: dict) -> dict:
    return {'version': stable['version'], 'tag': stable['release']['tag'],
            'sha256': stable['artifact']['sha256']}


def update_stable(previous: dict, report: dict, published: dict | None) -> dict:
    stable = copy.deepcopy(previous)
    probe, source = report['steam'], report['source']
    stable['source'] = {
        'steam_app_id': probe['app_id'], 'depot_id': probe['depot_id'],
        'manifest_id': probe['manifest_id'], 'checked_at': probe['checked_at'],
        'server_pak_size': source['pak_size'], 'server_pak_sha256': source['pak_sha256'],
        'stock_locres': report['stock_locres'],
    }
    stable['build'] = {'fingerprint': report['build_fingerprint'], 'shooter_desired': 1243, 'engine_desired': 21}
    if published:
        stable['version'] = published['version']
        stable['release'] = {k: published[k] for k in ('tag', 'published_at', 'commit')}
        stable['artifact'] = {'filename': PAK_NAME, 'size': published['size'], 'sha256': published['sha256'],
                              'download_url': published['asset_url']}
    return stable


def stage_release(root: Path, repository: str, version: str, commit: str,
                  report: dict, pak: Path, report_name: str) -> list[Path]:
    """Create only the small, verified public artifacts, never official stock data."""
    folder = root / 'work/release-staging' / ('v' + version)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / PAK_NAME
    shutil.copyfile(pak, destination)
    if file_sha256(destination) != report['final_pak']['sha256'] or destination.stat().st_size != report['final_pak']['size']:
        raise ValueError('staged PAK differs from verified build report')
    manifest = {'schema': 1, 'channel': 'stable', 'version': version,
                'release': {'tag': 'v' + version, 'commit': commit},
                'source': report['steam'], 'build': {'fingerprint': report.get('build_fingerprint'),
                'shooter_desired': 1243, 'engine_desired': 21},
                'artifact': {'filename': PAK_NAME, 'size': destination.stat().st_size,
                             'sha256': file_sha256(destination),
                             'download_url': f'https://github.com/{repository}/releases/download/v{version}/{PAK_NAME}'}}
    write_json(folder / 'release-manifest.json', manifest)
    write_json(folder / report_name, report)
    files = [destination, folder / 'release-manifest.json', folder / report_name]
    sums = folder / 'SHA256SUMS.txt'
    sums.write_text(''.join(f'{file_sha256(path)}  {path.name}\n' for path in sorted(files)), encoding='utf-8')
    return files + [sums]


def initialize(root: Path, repository: str, artifact_dir: Path, publisher: GitHubPublisher) -> dict:
    stable, state, head = publisher.read_channel()
    if head is not None:
        validate_channel(stable, state, repository)
        raise ValueError('channel already exists; initialization refuses to overwrite state')
    report = read_json(artifact_dir / 'cloud-build-report.json')
    pak = artifact_dir / PAK_NAME
    if (report['steam']['manifest_id'] != PINNED_MANIFEST
            or report['steam']['app_id'] != '2430930' or report['steam']['depot_id'] != '2430931'
            or report['tests']['result'] != 'PASS' or report['tests']['count'] < 75
            or report['repak_validation'] != 'PASS'
            or report['placeholder_printf_richtext_validation']['issues'] != 0
            or report['final_pak']['sha256'] != EXPECTED_PAK_SHA256
            or report['final_pak']['size'] != EXPECTED_PAK_SIZE
            or file_sha256(pak) != EXPECTED_PAK_SHA256 or pak.stat().st_size != EXPECTED_PAK_SIZE):
        raise ValueError('baseline must be the proven pinned cloud artifact')
    commit = report['git_commit']
    files = stage_release(root, repository, '1.0.0', commit, report, pak, 'cloud-build-report.json')
    # Preserve the original report bytes as provenance, not a newly claimed build.
    shutil.copyfile(artifact_dir / 'cloud-build-report.json', files[2])
    files[3].write_text(''.join(f'{file_sha256(path)}  {path.name}\n' for path in sorted(files[:3])), encoding='utf-8')
    release = publisher.publish_release('1.0.0', commit, files,
        notes='Проверенный русский перевод v1.0.0. PAK побайтно совпадает с доказанной облачной сборкой. Клиентский updater ещё не реализован.')
    stable = {'schema': 1, 'channel': 'stable', 'version': '1.0.0',
              'release': {k: release[k] for k in ('tag', 'published_at', 'commit')},
              'source': {'steam_app_id': report['steam']['app_id'], 'depot_id': report['steam']['depot_id'],
                         'manifest_id': PINNED_MANIFEST, 'checked_at': report['timestamp_utc'],
                         'stock_locres': report['stock_locres']},
              'build': {'fingerprint': None, 'initial_baseline': 'proven-cloud-artifact',
                        'shooter_desired': 1243, 'engine_desired': 21},
              'artifact': {'filename': PAK_NAME, 'size': release['size'], 'sha256': release['sha256'],
                           'download_url': release['asset_url']}}
    state = {'schema': 1, 'last_successful': None, 'last_attempt': None, 'latest_release': latest_release(stable)}
    sha = publisher.write_channel(stable, state, None, 'Initialize verified stable v1.0.0')
    result = {'release': release, 'channel_commit': sha, 'stable': stable}
    write_json(root / 'work/channel-initialization.json', result)
    return result


def run_update(root: Path, repository: str, publisher: GitHubPublisher, *, force: bool = False,
               run_id: str = 'local') -> int:
    work = root / 'work'
    work.mkdir(parents=True, exist_ok=True)
    (work / 'live-process.log').write_text('', encoding='utf-8')
    stable, state, channel_head = publisher.read_channel()
    validate_channel(stable, state, repository)
    fingerprint = build_fingerprint(root)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    report = {'schema': 1, 'timestamp_utc': utc_now(), 'run_id': run_id, 'git_commit': commit,
              'build_fingerprint': fingerprint, 'full_bootstrap': False, 'heavy_build': False,
              'downloaded_bytes': 0, 'release_created': False}
    probe, published = None, None
    try:
        execute(root, sys.executable, '-m', 'tools.bootstrap', '--probe-only')
        probe = probe_manifest(work / 'tools/depotdownloader/DepotDownloader.exe', work / 'manifest-probe')
        report['steam'] = probe
        print(f"Current Steam manifest: {probe['manifest_id']}; probe PAK downloaded bytes: 0", flush=True)
        decision = decide(state, probe['manifest_id'], fingerprint, force)
        report['decision'] = decision
        if decision['action'] != 'build':
            report['status'] = 'skipped' if decision['action'] == 'skip' else 'blocked'
            write_json(work / 'live-build-report.json', report)
            print('Full bootstrap, ooz, repak, server PAK download, build, full tests, Release: SKIPPED', flush=True)
            return 0 if decision['action'] == 'skip' else 2
        report.update(full_bootstrap=True, heavy_build=True)
        (work / 'build_failure.json').unlink(missing_ok=True)
        execute(root, sys.executable, '-m', 'tools.bootstrap')
        execute(root, sys.executable, 'build.py', '--profile', 'live', '--source', 'steam', '--manifest', probe['manifest_id'])
        tests = run_tests(work / 'live-validation.log')
        report.update(make_live_report(read_json(work / 'build_validation.json'), tests, probe,
                      fingerprint=fingerprint, commit=commit, run_id=run_id,
                      previous_sha=stable['artifact']['sha256']))
        pending = state.get('pending_release')
        if pending and (not report['pak_changed']
                        or pending['report']['build_fingerprint'] != fingerprint
                        or pending['report']['steam']['manifest_id'] != probe['manifest_id']
                        or pending['report']['final_pak'] != report['final_pak']):
            raise ValueError('unresolved Release transaction belongs to other inputs; explicit review required')
        if report['pak_changed']:
            version = next_version(stable['version'])
            report.update(release_created=True, release_tag='v' + version, version=version)
            pending = state.get('pending_release')
            if pending:
                original = pending['report']
                if (pending['version'] != version
                        or original['build_fingerprint'] != fingerprint
                        or original['steam']['manifest_id'] != probe['manifest_id']
                        or original['final_pak'] != report['final_pak']):
                    raise ValueError('pending Release belongs to different inputs; explicit review required')
                release_report, release_commit = original, pending['commit']
            else:
                release_report, release_commit = copy.deepcopy(report), commit
                state = copy.deepcopy(state)
                state['pending_release'] = {'version': version, 'commit': commit, 'report': release_report}
                channel_head = publisher.write_channel(stable, state, channel_head,
                                                       'Prepare verified immutable Release transaction')
            assets = stage_release(root, repository, version, release_commit, release_report,
                                   root / 'dist' / PAK_NAME, 'live-build-report.json')
            assets.sort(key=lambda path: path.name == PAK_NAME)
            published = publisher.publish_release(version, release_commit, assets,
                notes=f"Автоматически проверенный русский перевод. Steam manifest: {probe['manifest_id']}. Все 1264 перевода, форматирование, упаковка и тесты проверены.")
        else:
            print('Verified PAK SHA unchanged: no Release and no version increment.', flush=True)
        updated = update_stable(stable, report, published)
        updated_state = record_success(state, probe['manifest_id'], fingerprint, run_id, latest_release(updated), utc_now())
        updated_state.pop('pending_release', None)
        sha = publisher.write_channel(updated, updated_state, channel_head, 'Record verified Steam localization build')
        report.update(status='success', channel_commit=sha, stable_version=updated['version'])
        write_json(work / 'live-build-report.json', report)
        return 0
    except Exception as exc:
        report.update(status='failed', release_created=published is not None, error=str(exc))
        if published:
            report['published_release'] = published
        failure = work / 'build_failure.json'
        if report['heavy_build'] and failure.is_file():
            detail = read_json(failure)
            report['validation_failure'] = detail
            if 'source' in detail:
                report['source'] = detail['source']
                report['downloaded_bytes'] = detail['source'].get('downloaded_bytes', 0)
            if 'stock_locres' in detail:
                report['stock_locres'] = detail['stock_locres']
            issues = detail.get('issues', [])
            report['missing'] = sum(item.get('kind') == 'missing_en_key' for item in issues)
            report['source_changed'] = sum(item.get('kind') == 'source_changed' for item in issues)
        if probe is not None:
            failed = record_failure(state, probe['manifest_id'], fingerprint, run_id, str(exc), utc_now())
            try:
                report['channel_commit'] = publisher.write_channel(stable, failed, channel_head, 'Record failed Steam localization build')
            except Exception as state_error:
                report['state_error'] = str(state_error)
        else:
            report['status'] = 'probe_failed'
        write_json(work / 'live-build-report.json', report)
        print(f'LIVE UPDATE ERROR: {exc}', file=sys.stderr)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    live = sub.add_parser('run')
    live.add_argument('--force-rebuild', action='store_true')
    init = sub.add_parser('initialize')
    init.add_argument('--artifact-dir', type=Path, required=True)
    for command in (live, init):
        command.add_argument('--repository', required=True)
    args = parser.parse_args()
    publisher = GitHubPublisher(args.repository)
    if args.command == 'initialize':
        result = initialize(ROOT, args.repository, args.artifact_dir, publisher)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return run_update(ROOT, args.repository, publisher, force=args.force_rebuild,
                      run_id=os.environ.get('GITHUB_RUN_ID', 'local'))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.CalledProcessError) as exc:
        print(f'AUTOMATION ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
