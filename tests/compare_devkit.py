"""Optional oracle comparison; production does not import this script.

Run from the project root with an explicit --unrealpak path. Outputs and the
machine-readable comparison report are confined to ignored work/.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.locres import parse, serialize
from tools.pakv12 import PakReader
from tools.steam import find_game


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unrealpak', type=Path, required=True)
    parser.add_argument('--game-path', type=Path)
    args = parser.parse_args()
    games = [args.game_path] if args.game_path else find_game()
    if len(games) != 1:
        parser.error('Select one ASA installation with --game-path')
    exe = args.unrealpak.resolve()
    if not exe.is_file():
        parser.error('Reference UnrealPak executable is absent')
    source = games[0] / 'ShooterGame/Content/Paks/pakchunk0-Windows.pak'
    reader = PakReader(source)
    folder = ROOT / 'work/devkit_reference'
    folder.mkdir(parents=True, exist_ok=True)
    report = {'source_pak': str(source), 'source_pak_size': source.stat().st_size,
              'reference_tool': str(exe), 'languages': {}}
    for language in ('en', 'ru'):
        name = f'ShooterGame/Content/Localization/ShooterGame/{language}/ShooterGame.locres'
        reference = folder / name
        reference.unlink(missing_ok=True)
        result = subprocess.run([str(exe), str(source), '-Extract', str(folder), f'-Filter={name}'],
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        (folder / f'{language}-extraction.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode or not reference.is_file():
            raise RuntimeError(f'Reference extraction failed ({result.returncode}); see work/devkit_reference/{language}-extraction.log')
        a, b = reference.read_bytes(), reader.extract('../../../' + name)
        custom = ROOT / f'work/custom/{language}.locres'
        custom.parent.mkdir(parents=True, exist_ok=True)
        custom.write_bytes(b)
        ar, br = parse(a), parse(b)
        details = {'reference_sha256': hashlib.sha256(a).hexdigest(), 'custom_sha256': hashlib.sha256(b).hexdigest(),
                   'reference_size': len(a), 'custom_size': len(b), 'reference_version': ar.version,
                   'custom_version': br.version, 'reference_keys': len(ar.entries), 'custom_keys': len(br.entries),
                   'byte_match': a == b, 'noop_byte_match': serialize(br, {}) == b}
        report['languages'][language] = details
        print(language.upper(), json.dumps(details))
        if a != b or not details['noop_byte_match']:
            raise RuntimeError(f'{language}: byte comparison/LOCRES round-trip FAILED')
    (ROOT / 'work/comparison.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('EN and RU: byte-identical MATCH; both LOCRES no-op round-trips MATCH')


if __name__ == '__main__':
    main()
