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

from tools.channel_state import (BUNDLE_NAMES, PAK_NAME, artifact_identity, backoff, build_fingerprint,
                                 bundle_identities, decide, next_version, record_failure, record_success,
                                 record_transient_failure)
from tools.bootstrap import TransientNetworkError, is_transient_network_error
from tools.cloud_report import make_live_report, run_tests
from tools.github_publish import GitHubPublisher
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
        if (result.returncode == 75 and 'tools.bootstrap' in args
                and 'BOOTSTRAP TRANSIENT NETWORK ERROR:' in result.stderr):
            raise TransientNetworkError(result.stderr[-8000:])
        raise RuntimeError(f'command failed with exit {result.returncode}: {args!r}\n{output[-8000:]}')


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
    if 'bundle' in stable:
        bundle = stable['bundle']
        version = bundle['version']
        next_version(version)
        expected_artifacts = bundle_artifact_records(repository, version, channel_bundle_identities(bundle))
        actual_artifacts = {asset['filename']: asset for asset in bundle['artifacts']}
        bundle_release = bundle['release']
        if (version_key(version) <= version_key(stable['version'])
                or bundle_release['tag'] != 'v' + version
                or not re.fullmatch(r'[0-9a-f]{40}', bundle_release['commit'])
                or not bundle_release.get('published_at')
                or any(actual_artifacts[asset['filename']]['download_url'] != asset['download_url']
                       for asset in expected_artifacts)):
            raise ValueError('invalid trusted stable bundle metadata')


def version_key(version: str) -> tuple[int, ...]:
    return tuple(map(int, version.split('.')))


def next_bundle_version(stable: dict) -> str:
    if 'bundle' in stable:
        return next_version(stable['bundle']['version'])
    return max('1.0.2', next_version(stable['version']), key=version_key)


def channel_bundle_identities(bundle: dict) -> dict:
    artifacts = bundle['artifacts']
    if (not isinstance(artifacts, list) or len(artifacts) != len(BUNDLE_NAMES)
            or any(not isinstance(asset, dict) or not isinstance(asset.get('filename'), str) for asset in artifacts)
            or {asset['filename'] for asset in artifacts} != set(BUNDLE_NAMES)):
        raise ValueError('invalid trusted stable bundle artifact set')
    return {asset['filename']: artifact_identity(asset) for asset in artifacts}


def bundle_artifact_records(repository: str, version: str, identities: dict) -> list[dict]:
    prefix = f'https://github.com/{repository}/releases/download/v{version}/'
    return [{'filename': name, **identities[name], 'download_url': prefix + name} for name in BUNDLE_NAMES]


def legacy_release_fields(stable: dict) -> dict:
    return {key: stable[key] for key in ('version', 'release', 'artifact')}


def latest_release(stable: dict) -> dict:
    if 'bundle' in stable:
        bundle = stable['bundle']
        identities = channel_bundle_identities(bundle)
        return {'version': bundle['version'], 'tag': bundle['release']['tag'],
                'sha256': identities[PAK_NAME]['sha256'], 'artifacts': identities}
    return {'version': stable['version'], 'tag': stable['release']['tag'],
            'sha256': stable['artifact']['sha256']}


def update_stable(previous: dict, report: dict, published: dict | None, *,
                  repository: str | None = None) -> dict:
    stable = copy.deepcopy(previous)
    probe, source = report['steam'], report['source']
    stable['source'] = {
        'steam_app_id': probe['app_id'], 'depot_id': probe['depot_id'],
        'manifest_id': probe['manifest_id'], 'checked_at': probe['checked_at'],
        'server_pak_size': source['pak_size'], 'server_pak_sha256': source['pak_sha256'],
        'stock_locres': report['stock_locres'],
    }
    stable['build'] = {'fingerprint': report['build_fingerprint'], 'shooter_desired': 1243, 'engine_desired': 21}
    if published and repository is not None:
        stable['bundle'] = {'version': published['version'],
                            'release': {k: published[k] for k in ('tag', 'published_at', 'commit')},
                            'artifacts': bundle_artifact_records(repository, published['version'],
                                                                 bundle_identities(report))}
    elif published:
        stable['version'] = published['version']
        stable['release'] = {k: published[k] for k in ('tag', 'published_at', 'commit')}
        stable['artifact'] = {'filename': PAK_NAME, 'size': published['size'], 'sha256': published['sha256'],
                              'download_url': published['asset_url']}
    return stable


def stage_release(root: Path, repository: str, version: str, commit: str,
                  report: dict, pak: Path, report_name: str, *, legacy: dict | None = None) -> list[Path]:
    """Create only the small, verified public artifacts, never official stock data."""
    folder = root / 'work/release-staging' / ('v' + version)
    folder.mkdir(parents=True, exist_ok=True)
    identities = bundle_identities(report) if legacy is not None else {PAK_NAME: artifact_identity(report['final_pak'])}
    files = []
    for name, identity in identities.items():
        destination = folder / name
        shutil.copyfile(pak if name == PAK_NAME else pak.with_name(name), destination)
        if destination.stat().st_size != identity['size'] or file_sha256(destination) != identity['sha256']:
            raise ValueError(f'staged {name} differs from verified build report')
        files.append(destination)
    release = {'tag': 'v' + version, 'commit': commit}
    manifest = {'schema': 1, 'channel': 'stable', 'version': version, 'release': release,
                'source': report['steam'], 'build': {'fingerprint': report.get('build_fingerprint'),
                'shooter_desired': 1243, 'engine_desired': 21},
                'artifact': {'filename': PAK_NAME, **identities[PAK_NAME],
                             'download_url': f'https://github.com/{repository}/releases/download/v{version}/{PAK_NAME}'}}
    if legacy is not None:
        manifest.update(legacy_release_fields(legacy),
                        bundle={'version': version, 'release': release,
                                'artifacts': bundle_artifact_records(repository, version, identities)})
    write_json(folder / 'release-manifest.json', manifest)
    write_json(folder / report_name, report)
    files.extend((folder / 'release-manifest.json', folder / report_name))
    sums = folder / 'SHA256SUMS.txt'
    sums.write_text(''.join(f'{file_sha256(path)}  {path.name}\n' for path in sorted(files)), encoding='utf-8')
    return files + [sums]


def stage_local_bundle(root: Path, repository: str, stable: dict, report: dict, pak: Path) -> list[Path]:
    """Prepare a candidate from a verified report and local files without using GitHub or Steam."""
    validate_channel(stable, {'schema': 1}, repository)
    commit = report.get('git_commit', '')
    formatting = report.get('placeholder_printf_richtext_validation', {})
    if (not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit)
            or report.get('tests', {}).get('result') != 'PASS'
            or report.get('repak_validation') != 'PASS'
            or formatting.get('status') != 'PASS' or formatting.get('issues') != 0
            or report.get('translation_counts') != {'shooter_desired': 1243, 'engine_desired': 21}):
        raise ValueError('offline staging requires a verified cloud or live build report')
    identities = bundle_identities(report)
    if 'bundle' in stable and identities == channel_bundle_identities(stable['bundle']):
        raise ValueError('bundle identities match the current stable bundle')
    report_name = 'live-build-report.json' if 'build_fingerprint' in report else 'cloud-build-report.json'
    return stage_release(root, repository, next_bundle_version(stable), commit, report, pak, report_name,
                         legacy=stable)


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
               run_id: str = 'local', expected_first_pak: str | None = None) -> int:
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
    pending = state.get('pending_release')
    recovering = pending is not None
    bundle_mode = not recovering or pending.get('kind') == 'bundle'
    report['recovering_publication'] = recovering
    phase = 'recovery_prepare' if recovering else 'probe'
    try:
        delay = None if force or recovering else backoff(state, None, fingerprint, utc_now())
        if delay:
            report.update(status='backoff', decision=delay, warning='BACKOFF: manifest probe deferred')
            write_json(work / 'live-build-report.json', report)
            print(f"::warning::BACKOFF: manifest probe deferred until {delay['next_retry_at']}", flush=True)
            return 0
        if recovering:
            # Complete the recorded transaction, not the latest Steam manifest.
            # Existing recovery revalidates these inputs and preserves asset bytes.
            # The migration can still finish v1.0.1 by reproducing its exact PAK
            # below, even though the bundle build has a new fingerprint.
            expected_version = next_bundle_version(stable) if bundle_mode else next_version(stable['version'])
            if (pending['version'] != expected_version
                    or (bundle_mode and (pending['report']['build_fingerprint'] != fingerprint
                                         or pending['legacy'] != legacy_release_fields(stable)))
                    or (not bundle_mode and ('bundle' in stable or pending.get('kind') is not None
                                             or pending['version'] != '1.0.1'))):
                raise ValueError('pending Release belongs to different build inputs; explicit review required')
            probe = copy.deepcopy(pending['report']['steam'])
            decision = {'action': 'build', 'reason': 'pending Release recovery takes priority'}
            print(f"Recovering pending Release v{pending['version']} for manifest {probe['manifest_id']}", flush=True)
        else:
            execute(root, sys.executable, '-m', 'tools.bootstrap', '--probe-only')
            probe = probe_manifest(work / 'tools/depotdownloader/DepotDownloader.exe', work / 'manifest-probe')
            print(f"Current Steam manifest: {probe['manifest_id']}; probe PAK downloaded bytes: 0", flush=True)
            # A legacy single-PAK success does not establish the first bundle.
            decision_state = state if 'bundle' in stable else {**state, 'last_successful': None}
            decision = decide(decision_state, probe['manifest_id'], fingerprint, force, now=utc_now())
        report['steam'] = probe
        report['decision'] = decision
        if decision['action'] != 'build':
            report['status'] = 'skipped' if decision['action'] == 'skip' else decision['action']
            if decision['action'] in ('blocked', 'backoff'):
                report['warning'] = f"{decision['action'].upper()}: {decision['reason']}"
                if 'next_retry_at' in decision:
                    report['warning'] += f"; retry at {decision['next_retry_at']}"
                print(f"::warning::{report['warning']}", flush=True)
            write_json(work / 'live-build-report.json', report)
            print('Full bootstrap, ooz, repak, server PAK download, build, full tests, Release: SKIPPED', flush=True)
            return 0
        report.update(full_bootstrap=True, heavy_build=True)
        (work / 'build_failure.json').unlink(missing_ok=True)
        phase = 'bootstrap'
        execute(root, sys.executable, '-m', 'tools.bootstrap')
        phase = 'source_build'
        execute(root, sys.executable, 'build.py', '--profile', 'live', '--source', 'steam', '--manifest', probe['manifest_id'])
        phase = 'validation'
        tests = run_tests(work / 'live-validation.log')
        previous_bundle = channel_bundle_identities(stable['bundle']) if 'bundle' in stable else None
        previous_sha = previous_bundle[PAK_NAME]['sha256'] if previous_bundle else stable['artifact']['sha256']
        report.update(make_live_report(read_json(work / 'build_validation.json'), tests, probe,
                      fingerprint=fingerprint, commit=commit, run_id=run_id,
                      previous_sha=previous_sha))
        identities = bundle_identities(report) if bundle_mode else {PAK_NAME: artifact_identity(report['final_pak'])}
        if bundle_mode:
            if previous_bundle is None and expected_first_pak is not None and identities[PAK_NAME]['sha256'] != expected_first_pak:
                raise ValueError('first bundle PAK differs from the candidate verified in the ARK client')
            report['bundle_changed'] = identities != previous_bundle
        changed = report['bundle_changed'] if bundle_mode else report['pak_changed']
        if pending:
            original = pending['report']
            original_identities = (bundle_identities(original) if bundle_mode else
                                   {PAK_NAME: artifact_identity(original['final_pak'])})
            if (not changed or original['steam']['manifest_id'] != probe['manifest_id']
                    or original_identities != identities):
                raise ValueError('unresolved Release transaction belongs to other inputs; explicit review required')
        if changed:
            version = next_bundle_version(stable) if bundle_mode else next_version(stable['version'])
            report.update(release_created=True, release_tag='v' + version, version=version)
            if pending:
                release_report, release_commit = pending['report'], pending['commit']
                legacy = pending.get('legacy') if bundle_mode else None
            else:
                release_report, release_commit = copy.deepcopy(report), commit
                legacy = legacy_release_fields(stable)
            phase = 'release_staging'
            assets = stage_release(root, repository, version, release_commit, release_report,
                                   root / 'dist' / PAK_NAME, 'live-build-report.json', legacy=legacy)
            if not pending:
                state = copy.deepcopy(state)
                state['pending_release'] = {'kind': 'bundle', 'version': version, 'commit': commit,
                                            'report': release_report, 'legacy': copy.deepcopy(legacy)}
                phase = 'channel_prepare'
                channel_head = publisher.write_channel(stable, state, channel_head,
                                                       'Prepare verified immutable Release transaction')
            assets.sort(key=lambda path: path.name == PAK_NAME)
            phase = 'release_publish'
            published = publisher.publish_release(version, release_commit, assets,
                notes=f"Автоматически проверенный русский перевод. Steam manifest: {probe['manifest_id']}. Все 1264 перевода, форматирование, упаковка и тесты проверены.")
        else:
            print('Verified bundle identities unchanged: no Release and no version increment.', flush=True)
        updated = update_stable(stable, report, published, repository=repository if bundle_mode else None)
        updated_state = record_success(state, probe['manifest_id'], fingerprint, run_id, latest_release(updated), utc_now())
        updated_state.pop('pending_release', None)
        phase = 'channel_commit'
        sha = publisher.write_channel(updated, updated_state, channel_head, 'Record verified Steam localization build')
        report.update(status='success', channel_commit=sha, stable_version=updated['version'])
        if 'bundle' in updated:
            report['bundle_version'] = updated['bundle']['version']
        write_json(work / 'live-build-report.json', report)
        return 0
    except Exception as exc:
        report['failure_stage'] = phase
        if recovering or phase in ('channel_prepare', 'release_staging', 'release_publish', 'channel_commit'):
            report.update(status='publication_failed', failure_kind='publication', error=str(exc),
                          release_created=published is not None,
                          pending_release=copy.deepcopy(state.get('pending_release')))
            if published:
                report['published_release'] = published
            write_json(work / 'live-build-report.json', report)
            print(f'::error::PUBLICATION FAILURE [{phase}]: {exc}', file=sys.stderr, flush=True)
            return 2
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
        transient = (phase in ('probe', 'bootstrap', 'source_build')
                     and not report.get('validation_failure', {}).get('issues')
                     and is_transient_network_error(exc))
        report['failure_kind'] = 'transient' if transient else 'deterministic'
        if probe is not None or transient:
            if transient:
                failed = record_transient_failure(state, probe['manifest_id'] if probe else None,
                                                  fingerprint, run_id, str(exc), utc_now())
                report['next_retry_at'] = failed['transient_failure']['next_retry_at']
            else:
                failed = record_failure(state, probe['manifest_id'], fingerprint, run_id, str(exc), utc_now())
            try:
                report['channel_commit'] = publisher.write_channel(stable, failed, channel_head, 'Record failed Steam localization build')
            except Exception as state_error:
                report.update(status='publication_failed', failure_kind='publication',
                              failure_stage='failure_state_write', state_error=str(state_error))
                print(f'::error::CHANNEL STATE WRITE FAILURE: {state_error}', file=sys.stderr, flush=True)
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
    live.add_argument('--expected-first-pak', help='SHA-256 of the PAK verified in ARK before the first bundle release')
    init = sub.add_parser('initialize')
    init.add_argument('--artifact-dir', type=Path, required=True)
    stage = sub.add_parser('stage-bundle', help='stage a verified local bundle without network or publication')
    stage.add_argument('--stable-json', type=Path, required=True)
    stage.add_argument('--report', type=Path, required=True)
    stage.add_argument('--pak', type=Path, required=True)
    for command in (live, init, stage):
        command.add_argument('--repository', required=True)
    args = parser.parse_args()
    if args.command == 'stage-bundle':
        files = stage_local_bundle(ROOT, args.repository, read_json(args.stable_json), read_json(args.report), args.pak)
        for path in files:
            print(path)
        return 0
    expected_first_pak = getattr(args, 'expected_first_pak', None)
    if expected_first_pak is not None and not re.fullmatch(r'[0-9a-f]{64}', expected_first_pak):
        parser.error('--expected-first-pak must be a lowercase SHA-256')
    publisher = GitHubPublisher(args.repository)
    if args.command == 'initialize':
        result = initialize(ROOT, args.repository, args.artifact_dir, publisher)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return run_update(ROOT, args.repository, publisher, force=args.force_rebuild,
                      run_id=os.environ.get('GITHUB_RUN_ID', 'local'), expected_first_pak=expected_first_pak)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.CalledProcessError) as exc:
        print(f'AUTOMATION ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
