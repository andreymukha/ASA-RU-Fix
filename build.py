"""Extract the current ASA language resources, apply corrections, and verify a patch PAK."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tools.locres import LocresError, load_edits, parse, serialize, insert_missing
from tools.corrections import validate_corrections, verify_applied
from tools.steam import find_game
from tools.pakv12 import PakReader

ROOT = Path(__file__).resolve().parent
PAK_REL = Path("ShooterGame/Content/Paks/pakchunk0-Windows.pak")
INTERNAL = "ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres"
ENGINE_INTERNAL = "Engine/Content/Localization/Engine/ru/Engine.locres"


def resolve_game(explicit: Path | None, parser: argparse.ArgumentParser) -> Path:
    if explicit:
        game = explicit.expanduser().resolve()
        if not game.is_dir():
            parser.error(f"game path does not exist or is not a directory: {game}")
        return game
    games = find_game()
    if not games:
        parser.error("Steam scan did not find ASA (App 2399830); pass --game-path")
    if len(games) != 1:
        parser.error("multiple ASA installs found; pass --game-path: " + ", ".join(map(str, games)))
    return games[0]


def resolve_repak(explicit: Path | None, parser: argparse.ArgumentParser) -> Path:
    if explicit:
        exe = explicit.expanduser().resolve()
        if not exe.is_file():
            parser.error(f"repak executable not found: {exe}")
        return exe
    env = os.environ.get("ASA_REPAK")
    if env:
        exe = Path(env).expanduser().resolve()
        if not exe.is_file():
            parser.error(f"ASA_REPAK does not point to a file: {exe}")
        return exe
    local = ROOT / "work" / "tools" / "repak.exe"
    if local.is_file():
        return local.resolve()
    located = shutil.which("repak.exe") or shutil.which("repak")
    if located:
        return Path(located).resolve()
    parser.error("repak v0.2.3 not found; run `python tools/bootstrap.py` or pass --repak")


def run_repak(exe: Path, *args: str) -> str:
    result = subprocess.run([str(exe), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = result.stdout + result.stderr
    if result.returncode:
        raise RuntimeError(f"repak failed ({result.returncode}): {' '.join(args)}\n{output[-4000:]}")
    return output


def build_resource(en, ru, corrections, additions):
    correction_validation = validate_corrections(corrections, en.as_dict(), ru.as_dict())
    base = insert_missing(ru, en, additions)
    addition_validation = validate_corrections(additions, en.as_dict(), base.as_dict())
    rebuilt = serialize(base, corrections)
    actual = parse(rebuilt)
    if actual.as_dict() != {**ru.as_dict(), **additions, **corrections}:
        raise LocresError('rebuilt LOCRES failed full dictionary verification')
    # Serialization must retain copied EN identity hashes and native position.
    expected_order = [(e.namespace_hash, e.namespace, e.key_hash, e.key, e.source_hash) for e in base.entries]
    actual_order = [(e.namespace_hash, e.namespace, e.key_hash, e.key, e.source_hash) for e in actual.entries]
    if expected_order != actual_order:
        raise LocresError('rebuilt LOCRES identity hashes/order changed')
    return rebuilt, {'corrections_preflight': correction_validation, 'additions_preflight': addition_validation,
                     'corrections_verification': verify_applied(corrections, actual.as_dict()),
                     'additions_verification': verify_applied(additions, actual.as_dict()),
                     'stock_en_keys': len(en.entries), 'stock_ru_keys': len(ru.entries),
                     'rebuilt_keys': len(actual.entries), 'native_order_and_hashes': 'PASS'}


def verify_package(repak, dist, verify_root, resources, edits):
    listing = run_repak(repak, 'list', str(dist))
    entries = [line.strip().replace('\\', '/') for line in listing.splitlines() if line.strip()]
    if sorted(entries) != sorted(resources):
        raise RuntimeError(f'patch PAK contains unexpected entries: {entries!r}')
    info = run_repak(repak, 'info', str(dist))
    if 'mount point: ../../../' not in info or 'version: V11' not in info:
        raise RuntimeError(f'patch PAK has unexpected mount point/version:\n{info}')
    verify_root.mkdir(parents=True, exist_ok=True)
    for name in resources:
        (verify_root / name).unlink(missing_ok=True)
    run_repak(repak, 'unpack', '--quiet', '--force', '--output', str(verify_root), str(dist))
    results = {}
    for name, built in resources.items():
        path = verify_root / name
        actual = path.read_bytes()
        if actual != built:
            raise RuntimeError(f'PAK-extracted LOCRES bytes differ: {name}')
        parsed = parse(actual).as_dict()
        if parsed != parse(built).as_dict():
            raise LocresError(f'PAK-extracted LOCRES dictionary differs: {name}')
        results[name] = verify_applied(edits[name], parsed)
    return {'files': sorted(entries), 'edits': results, 'repak_info': info,
            'list_info_unpack': 'PASS'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-path", type=Path, help="Explicit ASA installation directory")
    parser.add_argument("--repak", type=Path, help="repak v0.2.3 executable")
    args = parser.parse_args()
    game = resolve_game(args.game_path, parser)
    repak = resolve_repak(args.repak, parser)
    source_pak = game / PAK_REL
    if not source_pak.is_file():
        parser.error(f"required PAK not found: {source_pak}")
    reader = PakReader(source_pak)

    work = ROOT / "work"
    extract_root = work / "source"
    print(f"Game: {game}\nSource PAK V12: {source_pak}\nExtractor: tools.pakv12 + cached ooz DLL\nrepak writer: {repak}")
    resources, all_edits, reports = {}, {}, {}
    for name, internal, correction_file, addition_file in (
        ('ShooterGame', INTERNAL, 'corrections.json', 'additions.json'),
        ('Engine', ENGINE_INTERNAL, 'engine_ru.json', None),
    ):
        stock = {}
        stock_hashes = {}
        for language in ('en', 'ru'):
            relative = internal.replace('/ru/', f'/{language}/')
            raw = reader.extract('../../../' + relative)
            path = extract_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            stock[language] = parse(raw)
            stock_hashes[language] = hashlib.sha256(raw).hexdigest()
            dump_name = language if name == 'ShooterGame' else 'engine_' + language
            (work / (dump_name + '.json')).write_text(
                json.dumps(stock[language].as_dict(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        edits = load_edits(ROOT / 'data' / correction_file)
        if name == 'Engine':
            if any(not key.startswith('InputKeys\t') for key in edits):
                raise LocresError('Engine edits must belong to InputKeys')
            additions = {key: value for key, value in edits.items() if key not in stock['ru'].as_dict()}
            corrections = {key: value for key, value in edits.items() if key not in additions}
        else:
            corrections = edits
            additions = load_edits(ROOT / 'data' / addition_file)
        built, report = build_resource(stock['en'], stock['ru'], corrections, additions)
        report['stock_sha256'] = stock_hashes
        resources[internal] = built
        all_edits[internal] = {**corrections, **additions}
        reports[name] = report
        path = work / 'rebuilt' / internal
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(built)
        dump_name = 'ru_rebuilt' if name == 'ShooterGame' else 'engine_ru_rebuilt'
        (work / (dump_name + '.json')).write_text(
            json.dumps(parse(built).as_dict(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f"{name}: {len(corrections)} corrections; {len(additions)} additions; {report['rebuilt_keys']} keys")

    stage_root = work / 'pak_stage'
    # Refuse stale extra files rather than silently package an old resource.
    stale = {p.relative_to(stage_root).as_posix() for p in stage_root.rglob('*') if p.is_file()} - set(resources)
    if stale:
        raise RuntimeError(f'Unexpected stale PAK staging files: {sorted(stale)}')
    for internal, built in resources.items():
        staged = stage_root / internal
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(built)
    dist = ROOT / 'dist' / 'ASA_RU_Fix_P.pak'
    dist.parent.mkdir(parents=True, exist_ok=True)
    dist.unlink(missing_ok=True)
    run_repak(repak, 'pack', '--version', 'V11', '--mount-point', '../../../', '--quiet', str(stage_root), str(dist))
    package = verify_package(repak, dist, work / 'pak_verify', resources, all_edits)
    validation_report = {'resources': reports, 'package': package,
                         'pak_path': str(dist), 'pak_size': dist.stat().st_size,
                         'pak_sha256': hashlib.sha256(dist.read_bytes()).hexdigest()}
    (work / 'build_validation.json').write_text(json.dumps(validation_report, indent=2) + '\n', encoding='utf-8')
    for internal, result in package['edits'].items():
        print(f"{internal}: {result['actual']}/{result['expected']} MATCH; mismatches: {result['mismatches']}")
    print(f"Verified candidate: {dist} ({dist.stat().st_size:,} bytes); SHA-256 {validation_report['pak_sha256']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, LocresError, RuntimeError) as exc:
        print(f"BUILD ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
