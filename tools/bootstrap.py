"""Cache verified repak and build a pinned open-source ooz Windows x64 DLL."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "work" / "tools"
URL = "https://github.com/trumank/repak/releases/download/v0.2.3/repak_cli-x86_64-pc-windows-msvc.zip"
EXPECTED_SHA256 = "6720d602144d75df477a99d5bedb6ea780997546afc335901d4937cafeaa73fa"
OOZ_COMMIT = '05038060aa68f9187ae9923b2388ca8db40e58d1'
OOZ_FILES = {
    'kraken.cpp': '20c48a30db54efa7681f8c9c674f2a16f081373872d033885a6fdf244b9cff01',
    'bitknit.cpp': '6e448d52fe485032e8b7aaf3efff2f0efd6394c776d0c6b14f91d2e1d286ed73',
    'lzna.cpp': '8fc3fa71d814918f4a286d076c38a155ae8d93375281d796e2feba8ab866c712',
    'stdafx.h': '92b798615ee1ac90ed53a2685fc62dfbe7133d5ba69e567733d8081d420cf701',
    'targetver.h': '7f988ed4cd4fe1acdede1f014931a08c508cc82f9407bc2b869ec2195c10c9c9',
}
GPL_HASH = '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
COMPILER_FLAGS = '/nologo /LD /O2 /MT /EHsc /std:c++17'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_download(url: str, target: Path, digest: str):
    if target.is_file() and sha256(target) == digest:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + '.partial')
    print(f'Downloading {target.name}...')
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'ASA-RU-Fix-bootstrap'})
        with urllib.request.urlopen(request, timeout=60) as response, partial.open('wb') as output:
            shutil.copyfileobj(response, output)
        actual = sha256(partial)
        if actual != digest:
            raise RuntimeError(f'{target.name} SHA-256 mismatch: {actual}')
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def write_changed(path: Path, data: bytes):
    if not path.is_file() or path.read_bytes() != data:
        path.write_bytes(data)


def prepare_repak():
    archive = TOOLS / 'repak_cli-x86_64-pc-windows-msvc.zip'
    ensure_download(URL, archive, EXPECTED_SHA256)
    with zipfile.ZipFile(archive) as package:
        for basename in ('repak.exe', 'LICENSE-MIT', 'LICENSE-APACHE'):
            matches = [name for name in package.namelist() if Path(name).name == basename]
            if len(matches) != 1:
                raise RuntimeError(f'Verified repak ZIP must contain exactly one {basename}')
            write_changed(TOOLS / basename, package.read(matches[0]))
    result = subprocess.run([str(TOOLS / 'repak.exe'), '--version'], capture_output=True, text=True, check=True)
    if result.stdout.strip() != 'repak_cli 0.2.3':
        raise RuntimeError(f'Unexpected repak version: {result.stdout}')
    print('repak v0.2.3 ready; release ZIP SHA-256 verified')


def compiler_setup() -> Path:
    installer = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    if installer.is_file():
        result = subprocess.run([str(installer), '-latest', '-products', '*', '-requires',
                                 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'],
                                capture_output=True, text=True, check=True)
        location = result.stdout.strip()
        if location:
            setup = Path(location) / 'VC/Auxiliary/Build/vcvars64.bat'
            if setup.is_file():
                return setup
    raise RuntimeError('Building ooz requires Visual Studio 2022 Build Tools: Desktop development with C++ (MSVC x64 and Windows SDK). Install it, then rerun bootstrap.')


def prepare_ooz():
    folder = TOOLS / 'ooz'
    source = folder / 'source'
    source.mkdir(parents=True, exist_ok=True)
    for name, digest in OOZ_FILES.items():
        ensure_download(f'https://raw.githubusercontent.com/powzix/ooz/{OOZ_COMMIT}/{name}', source / name, digest)
    ensure_download('https://www.gnu.org/licenses/gpl-3.0.txt', folder / 'GPL-3.0.txt', GPL_HASH)
    upstream = (source / 'kraken.cpp').read_text(encoding='utf-8')
    if 'either version 3 of the License, or' not in upstream or '(at your option) any later version.' not in upstream:
        raise RuntimeError('Pinned ooz license declaration was not found')
    # Remove the entire upstream CLI, including its proprietary DLL loader.
    # Keep the license and decoder unchanged. The marker is pinned by SHA above.
    marker = '// The decompressor will write outside of the target buffer.'
    if upstream.count(marker) != 1:
        raise RuntimeError('Pinned ooz decoder/CLI boundary changed')
    decoder = upstream.split(marker)[0].encode('utf-8')
    bridge = (ROOT / 'tools/ooz_bridge.cpp').read_bytes()
    recipe = hashlib.sha256(decoder + bridge + COMPILER_FLAGS.encode() + json.dumps(OOZ_FILES, sort_keys=True).encode()).hexdigest()
    library, record = folder / 'ooz.dll', folder / 'build.json'
    if library.is_file() and record.is_file():
        try:
            cached = json.loads(record.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            cached = {}
        if cached.get('recipe') == recipe and cached.get('dll_sha256') == sha256(library):
            print(f'ooz {OOZ_COMMIT[:12]} ready; cached DLL hash verified (no compiler/network needed)')
            return
    setup = compiler_setup()
    decoder_path, bridge_path = source / 'kraken_decoder.cpp', source / 'ooz_bridge.cpp'
    write_changed(decoder_path, decoder)
    write_changed(bridge_path, bridge)
    script = folder / 'compile.cmd'
    # These paths come only from the local workspace and vswhere, never input
    # from an archive. Reject shell-expanding characters before writing a batch.
    paths = (setup, source, library, decoder_path, bridge_path)
    if any(any(char in str(path) for char in '\r\n"%&|<>^!') for path in paths):
        raise RuntimeError('Compiler/workspace path contains unsupported batch characters')
    command = (f'@echo off\ncall "{setup}" >nul\nif errorlevel 1 exit /b 1\n'
               f'cd /d "{folder}"\n'
               f'cl {COMPILER_FLAGS} "{decoder_path}" "{source / "lzna.cpp"}" "{source / "bitknit.cpp"}" "{bridge_path}" /link /OUT:"{library}"\n'
               'exit /b %errorlevel%\n')
    script.write_text(command, encoding='utf-8')
    print(f'Building GPL-3.0-or-later ooz {OOZ_COMMIT[:12]} with MSVC x64...')
    result = subprocess.run(['cmd.exe', '/d', '/c', str(script)], capture_output=True, text=True, errors='replace')
    if result.returncode or not library.is_file():
        raise RuntimeError(f'ooz compiler failed ({result.returncode}):\n{result.stdout[-6000:]}\n{result.stderr[-2000:]}')
    record.write_text(json.dumps({'source_commit': OOZ_COMMIT, 'recipe': recipe,
                                  'dll_sha256': sha256(library), 'compiler_setup': str(setup),
                                  'flags': COMPILER_FLAGS}, indent=2) + '\n', encoding='utf-8')
    print(f'ooz DLL ready: {library}; SHA-256 {sha256(library)}')


def main() -> int:
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise RuntimeError('Bootstrap requires Windows x64 and 64-bit Python')
    TOOLS.mkdir(parents=True, exist_ok=True)
    prepare_repak()
    prepare_ooz()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f'BOOTSTRAP ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
