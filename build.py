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
from tools.translation_data import classify_desired, load_source_identity
from tools.steam import find_game
from tools.pakv12 import PakReader
from tools.pak_order import canonicalize_pak
from tools.server_depot import (
    EXPECTED_PAK_SHA256,
    EXPECTED_PAK_SIZE,
    PINNED_MANIFEST,
    PINNED_STOCK,
    download_server_pak,
    validate_stock_resources,
    file_sha256,
)

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


def build_desired_resource(en, ru, desired, identities, resource_name):
    classified = classify_desired(desired, en, ru, identities, resource_name=resource_name)
    built, report = build_resource(en, ru, classified['corrections'], classified['additions'])
    report['classification'] = classified['counts']
    report['desired_preflight'] = classified['validation']
    report['desired_verification'] = verify_applied(desired, parse(built).as_dict())
    return built, report


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


def resolve_source(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[Path, dict]:
    if args.source == 'steam':
        depotdownloader = ROOT / 'work' / 'tools' / 'depotdownloader' / 'DepotDownloader.exe'
        try:
            result = download_server_pak(depotdownloader, ROOT / 'work' / 'server-depot', manifest=args.manifest)
        except RuntimeError as exc:
            parser.error(str(exc))
        return result['path'], {
            'kind': 'steam-dedicated-server', 'app_id': result['app_id'],
            'depot_id': result['depot_id'], 'manifest': result['manifest'],
            'downloaded_bytes': result['downloaded_bytes'], 'pak_size': result['pak_size'],
        }
    if args.source == 'server-pak':
        if not args.server_pak:
            parser.error('--source server-pak requires --server-pak')
        source_pak = args.server_pak.expanduser().resolve()
        if not source_pak.is_file():
            parser.error(f'server PAK not found: {source_pak}')
        return source_pak, {'kind': 'server-pak-file', 'pak_size': source_pak.stat().st_size}
    if args.server_pak:
        parser.error('--server-pak is only valid with --source server-pak')
    game = resolve_game(args.game_path, parser)
    source_pak = game / PAK_REL
    if not source_pak.is_file():
        parser.error(f'required PAK not found: {source_pak}')
    return source_pak, {'kind': 'installed-game', 'game_path': str(game), 'pak_size': source_pak.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('pinned', 'live'), default='pinned')
    parser.add_argument('--source', choices=('steam', 'server-pak', 'installed-game'), default='steam',
                        help='Input source (default: pinned Steam Dedicated Server depot)')
    parser.add_argument('--manifest', help='Exact resolved server depot manifest ID (required for live)')
    parser.add_argument('--server-pak', type=Path, help='Local server PAK for deterministic developer verification')
    parser.add_argument("--game-path", type=Path, help="Explicit ASA installation directory (developer source)")
    parser.add_argument("--repak", type=Path, help="repak v0.2.3 executable")
    parser.add_argument('--output', type=Path, help='Output PAK path (defaults to dist/ASA_RU_Fix_P.pak)')
    args = parser.parse_args()
    if args.profile == 'pinned':
        if args.manifest not in (None, PINNED_MANIFEST):
            parser.error('pinned profile requires the pinned manifest')
        args.manifest = PINNED_MANIFEST
    elif not args.manifest or not args.manifest.isdecimal():
        parser.error('live profile requires an exact numeric --manifest from the probe')
    (ROOT / 'work').mkdir(parents=True, exist_ok=True)
    (ROOT / 'work/build_failure.json').unlink(missing_ok=True)
    (ROOT / 'work/build_progress.json').unlink(missing_ok=True)
    repak = resolve_repak(args.repak, parser)
    source_pak, source_report = resolve_source(args, parser)
    source_report['manifest'] = args.manifest
    source_report['pak_sha256'] = file_sha256(source_pak)
    reader = PakReader(source_pak)

    work = ROOT / "work"
    extract_root = work / "source"
    print(f"Source: {source_report['kind']}\nSource PAK V12: {source_pak}\n"
          f"Extractor: tools.pakv12 + cached ooz DLL\nrepak writer: {repak}")
    resources, all_edits, reports = {}, {}, {}
    stock_bytes = {}
    for name, spec in PINNED_STOCK.items():
        stock_bytes[name] = reader.extract(spec.relative_path)
    stock_validation = validate_stock_resources(stock_bytes, profile=args.profile)
    (work / 'build_progress.json').write_text(json.dumps({
        'profile': args.profile, 'source': source_report, 'stock_locres': stock_validation,
    }, indent=2) + '\n', encoding='utf-8')
    identities = load_source_identity(ROOT / 'data/source_identity.json')
    for name, internal, desired_file in (
        ('ShooterGame', INTERNAL, 'shootergame_ru.json'),
        ('Engine', ENGINE_INTERNAL, 'engine_ru.json'),
    ):
        stock = {}
        stock_hashes = {}
        for language in ('en', 'ru'):
            input_name = f'{name} {language.upper()}'
            relative = PINNED_STOCK[input_name].relative_path.removeprefix('../../../')
            raw = stock_bytes[input_name]
            path = extract_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            stock[language] = parse(raw)
            stock_hashes[language] = hashlib.sha256(raw).hexdigest()
            dump_name = language if name == 'ShooterGame' else 'engine_' + language
            (work / (dump_name + '.json')).write_text(
                json.dumps(stock[language].as_dict(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        edits = load_edits(ROOT / 'data' / desired_file)
        if name == 'Engine':
            if any(not key.startswith('InputKeys\t') for key in edits):
                raise LocresError('Engine edits must belong to InputKeys')
        built, report = build_desired_resource(stock['en'], stock['ru'], edits, identities, name)
        report['stock_sha256'] = stock_hashes
        resources[internal] = built
        all_edits[internal] = edits
        reports[name] = report
        path = work / 'rebuilt' / internal
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(built)
        dump_name = 'ru_rebuilt' if name == 'ShooterGame' else 'engine_ru_rebuilt'
        (work / (dump_name + '.json')).write_text(
            json.dumps(parse(built).as_dict(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f"{name}: {report['classification']}; {report['rebuilt_keys']} keys")

    stage_root = work / 'pak_stage'
    # Refuse stale extra files rather than silently package an old resource.
    stale = {p.relative_to(stage_root).as_posix() for p in stage_root.rglob('*') if p.is_file()} - set(resources)
    if stale:
        raise RuntimeError(f'Unexpected stale PAK staging files: {sorted(stale)}')
    for internal, built in resources.items():
        staged = stage_root / internal
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(built)
    dist = (args.output.expanduser().resolve() if args.output else ROOT / 'dist' / 'ASA_RU_Fix_P.pak')
    if dist == source_pak.resolve():
        raise RuntimeError('output PAK path must not overwrite the source PAK')
    dist.parent.mkdir(parents=True, exist_ok=True)
    dist.unlink(missing_ok=True)
    run_repak(repak, 'pack', '--version', 'V11', '--mount-point', '../../../', '--quiet', str(stage_root), str(dist))
    canonicalize_pak(dist, [INTERNAL, ENGINE_INTERNAL])
    package = verify_package(repak, dist, work / 'pak_verify', resources, all_edits)
    pak_size = dist.stat().st_size
    pak_sha256 = hashlib.sha256(dist.read_bytes()).hexdigest()
    deterministic_match = pak_size == EXPECTED_PAK_SIZE and pak_sha256 == EXPECTED_PAK_SHA256
    if args.profile == 'pinned' and not deterministic_match:
        raise RuntimeError(
            f'Pinned production PAK mismatch: expected {EXPECTED_PAK_SIZE} bytes / {EXPECTED_PAK_SHA256}, '
            f'got {pak_size} bytes / {pak_sha256}'
        )
    counts = {
        'shooter_desired': reports['ShooterGame']['desired_verification']['expected'],
        'engine_desired': reports['Engine']['desired_verification']['expected'],
    }
    if counts != {'shooter_desired': 1243, 'engine_desired': 21}:
        raise RuntimeError(f'unexpected production translation counts: {counts}')
    if args.profile == 'pinned':
        for resource, expected in (('ShooterGame', (1199, 43, 1)), ('Engine', (16, 1, 4))):
            actual = reports[resource]['classification']
            if tuple(actual[k] for k in ('corrections', 'additions', 'already_correct')) != expected:
                raise RuntimeError(f'pinned classification mismatch: {resource}: {actual}')
    preflights = [reports[resource]['desired_preflight'] for resource in ('ShooterGame', 'Engine')]
    quality_validation = {
        'status': 'PASS' if all(item['issues'] == 0 for item in preflights) else 'FAIL',
        'entries_checked': sum(item['checked'] for item in preflights),
        'placeholder_strings': sum(item['placeholder_strings'] for item in preflights),
        'richtext_strings': sum(item['richtext_strings'] for item in preflights),
        'source_markup_fragments': sum(item['source_markup_fragments'] for item in preflights),
        'issues': sum(item['issues'] for item in preflights),
    }
    if quality_validation['status'] != 'PASS':
        raise RuntimeError(f'placeholder/RichText validation failed: {quality_validation}')
    validation_report = {'profile': args.profile, 'resources': reports, 'package': package,
                         'stock_input_validation': stock_validation,
                         'source': source_report,
                         'counts': counts,
                         'translation_validation': quality_validation,
                         'pak_path': str(dist), 'pak_size': pak_size,
                         'pak_sha256': pak_sha256,
                         'expected_pak_sha256': EXPECTED_PAK_SHA256 if args.profile == 'pinned' else None,
                         'deterministic_match': deterministic_match}
    (work / 'build_validation.json').write_text(json.dumps(validation_report, indent=2) + '\n', encoding='utf-8')
    for internal, result in package['edits'].items():
        print(f"{internal}: {result['actual']}/{result['expected']} MATCH; mismatches: {result['mismatches']}")
    print(f"Placeholder/printf/RichText preflight: {quality_validation['entries_checked']} entries, "
          f"{quality_validation['issues']} issues; PASS")
    print(f"Verified {args.profile} PAK: {dist} ({pak_size:,} bytes); SHA-256 {pak_sha256}; "
          f"matches pinned v1: {deterministic_match}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, LocresError, RuntimeError) as exc:
        (ROOT / 'work').mkdir(parents=True, exist_ok=True)
        progress = ROOT / 'work/build_progress.json'
        context = json.loads(progress.read_text(encoding='utf-8')) if progress.is_file() else {}
        (ROOT / 'work/build_failure.json').write_text(json.dumps(
            {**context, 'status': 'FAIL', 'error': str(exc), 'issues': getattr(exc, 'issues', [])},
            ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f"BUILD ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
