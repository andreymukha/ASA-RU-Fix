"""Validate the one-file Windows publish and emit deterministic release assets."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.github_publish import GitHubPublisher, _file_hash


EXE_NAME = 'ASA-RU-Fix.exe'
SDK_VERSION = '10.0.401'
RUNTIME_VERSION = '10.0.12'
ASSET_NAMES = (EXE_NAME, 'SHA256SUMS.txt', 'client-manifest.json')


def validate_version(version: str) -> str:
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('client version must be an unprefixed stable major.minor.patch')
    return version


def validate_project_version(project: Path, version: str | None = None) -> str:
    versions = [entry.text for entry in ET.parse(project).getroot().iter('Version')]
    if len(versions) != 1 or not versions[0]:
        raise ValueError('Directory.Build.props must define exactly one literal Version')
    actual = validate_version(versions[0])
    if version is not None and validate_version(version) != actual:
        raise ValueError(f'requested version differs from project Version {actual}')
    return actual


def build_manifest(publish_dir: Path, version: str, commit: str, repository: str) -> dict:
    validate_version(version)
    if not re.fullmatch(r'[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', commit):
        raise ValueError('client source commit must be a full commit SHA')
    GitHubPublisher(repository)  # Reuse the repository validation, without network calls.
    entries = list(publish_dir.iterdir())
    if len(entries) != 1 or entries[0].name != EXE_NAME or not entries[0].is_file() or entries[0].is_symlink():
        raise ValueError(f'user publish must contain exactly one file: {EXE_NAME}')
    exe = entries[0]
    with exe.open('rb') as source:
        if source.read(2) != b'MZ':
            raise ValueError('published EXE is not a Windows executable')
    tag = f'updater-v{version}'
    return {
        'schema': 1, 'version': version,
        'release': {'tag': tag, 'commit': commit.lower()},
        'artifact': {'filename': EXE_NAME, 'size': exe.stat().st_size, 'sha256': _file_hash(exe),
                     'download_url': f'https://github.com/{repository}/releases/download/{tag}/{EXE_NAME}'},
        'build': {'sdk': SDK_VERSION, 'runtime': RUNTIME_VERSION, 'runtime_identifier': 'win-x64',
                  'self_contained': True, 'single_file': True, 'trimmed': False,
                  'native_libraries_self_extract': True, 'debug_type': 'embedded', 'signing': 'unsigned'},
    }


def json_bytes(record: dict) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def create_build_assets(publish_dir: Path, output_dir: Path, version: str,
                        commit: str, repository: str) -> list[Path]:
    if output_dir.resolve() == publish_dir.resolve() or publish_dir.resolve() in output_dir.resolve().parents:
        raise ValueError('metadata directory must be outside the user publish directory')
    record = build_manifest(publish_dir, version, commit, repository)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / 'client-manifest.json'
    manifest.write_bytes(json_bytes(record))
    sums = output_dir / 'SHA256SUMS.txt'
    sums.write_bytes(f'{record["artifact"]["sha256"]}  {EXE_NAME}\n'.encode('ascii'))
    return [manifest, sums]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--project', type=Path, default=Path('client/Directory.Build.props'))
    parser.add_argument('--version')
    parser.add_argument('--commit', required=True)
    parser.add_argument('--repository', required=True)
    args = parser.parse_args(argv)
    version = validate_project_version(args.project, args.version)
    create_build_assets(args.publish_dir, args.output_dir, version, args.commit, args.repository)
    print(json.dumps({'version': version, 'artifact': str(args.publish_dir / EXE_NAME),
                      'metadata': str(args.output_dir)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
