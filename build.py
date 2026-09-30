"""Extract the current ASA language resources, apply corrections, and verify a patch PAK."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from tools.locres import LocresError, load_edits, parse, serialize
from tools.steam import find_game, find_unrealpak

ROOT = Path(__file__).resolve().parent
PAK_REL = Path("ShooterGame/Content/Paks/pakchunk0-Windows.pak")
INTERNAL = "ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres"
GAME_LANG_DIR = "ShooterGame/Content/Localization/ShooterGame"
MAGIC = struct.pack("<I", 0x5A6F12E1)


def pak_version(path: Path) -> int | None:
    with path.open("rb") as file:
        file.seek(-512, 2)
        tail = file.read()
    index = tail.rfind(MAGIC)
    if index < 0 or index + 8 > len(tail):
        return None
    return struct.unpack_from("<I", tail, index + 4)[0]


def run_unrealpak(exe: Path, *args: str) -> str:
    result = subprocess.run([str(exe), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = result.stdout + result.stderr
    if result.returncode:
        raise RuntimeError(f"UnrealPak failed ({result.returncode}): {' '.join(args)}\n{output[-4000:]}")
    return output


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


def resolve_unrealpak(explicit: Path | None, parser: argparse.ArgumentParser) -> Path:
    if explicit:
        exe = explicit.expanduser().resolve()
        if not exe.is_file():
            parser.error(f"UnrealPak executable not found: {exe}")
        return exe
    import os

    env = os.environ.get("ASA_UNREALPAK")
    if env:
        exe = Path(env).expanduser().resolve()
        if exe.is_file():
            return exe
        parser.error(f"ASA_UNREALPAK does not point to a file: {exe}")
    candidates = find_unrealpak()
    if not candidates:
        parser.error("ARK DevKit UnrealPak not found; pass --unrealpak or set ASA_UNREALPAK")
    if len(candidates) > 1:
        parser.error("multiple ARK DevKit UnrealPak tools found; pass --unrealpak: " + ", ".join(map(str, candidates)))
    return candidates[0]


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
    located = shutil.which("repak.exe") or shutil.which("repak")
    for candidate in (local, Path(located) if located else None):
        if candidate and candidate.is_file():
            return candidate.resolve()
    parser.error("repak v0.2.3 not found; run `python tools/bootstrap.py` or pass --repak")


def run_repak(exe: Path, *args: str) -> str:
    result = subprocess.run([str(exe), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = result.stdout + result.stderr
    if result.returncode:
        raise RuntimeError(f"repak failed ({result.returncode}): {' '.join(args)}\n{output[-4000:]}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-path", type=Path, help="Explicit ASA installation directory")
    parser.add_argument("--unrealpak", type=Path, help="UnrealPak.exe from the locally installed ARK DevKit")
    parser.add_argument("--repak", type=Path, help="repak v0.2.3 executable")
    args = parser.parse_args()
    game = resolve_game(args.game_path, parser)
    unrealpak = resolve_unrealpak(args.unrealpak, parser)
    repak = resolve_repak(args.repak, parser)
    source_pak = game / PAK_REL
    if not source_pak.is_file():
        parser.error(f"required PAK not found: {source_pak}")
    version = pak_version(source_pak)
    if version != 12:
        parser.error(f"unsupported/current game PAK version {version}; this extractor path is validated for ASA PAK v12")

    work = ROOT / "work"
    extract_root = work / "source"
    en_rel = Path(GAME_LANG_DIR) / "en" / "ShooterGame.locres"
    ru_rel = Path(GAME_LANG_DIR) / "ru" / "ShooterGame.locres"
    en_path, ru_path = extract_root / en_rel, extract_root / ru_rel
    for path in (en_path, ru_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
    print(f"Game: {game}\nSource PAK v{version}: {source_pak}\nUnrealPak extractor: {unrealpak}\nrepak writer: {repak}")

    index = run_unrealpak(unrealpak, str(source_pak), "-List")
    for language in ("en", "ru"):
        expected = f"ShooterGame/Content/Localization/ShooterGame/{language}/ShooterGame.locres"
        lines = [line for line in index.splitlines() if f'"{expected}"' in line]
        if len(lines) != 1:
            raise RuntimeError(f"expected exactly one PAK index entry for {expected}; found {len(lines)}")
        if "compression: Oodle" not in lines[0]:
            print(f"Notice: PAK entry compression differs from prior observation: {lines[0].strip()}")
        run_unrealpak(unrealpak, str(source_pak), "-Extract", str(extract_root), f"-Filter={expected}")
    if not en_path.is_file() or not ru_path.is_file():
        raise RuntimeError("UnrealPak reported success but did not create both expected LOCRES files")

    en, ru = parse(en_path.read_bytes()), parse(ru_path.read_bytes())
    en_dump, ru_dump = en.as_dict(), ru.as_dict()
    (work / "en.json").write_text(json.dumps(en_dump, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (work / "ru.json").write_text(json.dumps(ru_dump, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"English: LOCRES v{en.version}, {len(en.entries):,} keys, {en_path.stat().st_size:,} bytes")
    print(f"Russian: LOCRES v{ru.version}, {len(ru.entries):,} keys, {ru_path.stat().st_size:,} bytes")

    additions_path = ROOT / "data" / "additions.json"
    additions = load_edits(additions_path)
    if additions:
        raise RuntimeError("additions.json is experimental and non-empty additions are not supported; clear it before building")
    corrections = load_edits(ROOT / "data" / "corrections.json")
    for key in corrections:
        if key not in ru_dump:
            raise LocresError(f"correction key is absent from current official RU LOCRES: {key!r}")
    rebuilt = serialize(ru, corrections)
    rebuilt_resource = parse(rebuilt)
    merged = {**ru_dump, **corrections}
    if rebuilt_resource.as_dict() != merged:
        raise LocresError("rebuilt LOCRES failed full dictionary verification")

    built_locres = work / "rebuilt" / Path(INTERNAL)
    built_locres.parent.mkdir(parents=True, exist_ok=True)
    built_locres.write_bytes(rebuilt)
    patched_dump = work / "ru_rebuilt.json"
    patched_dump.write_text(json.dumps(rebuilt_resource.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Corrections applied: {len(corrections)}; rebuilt LOCRES: {len(rebuilt):,} bytes")

    stage_root = work / "pak_stage"
    staged = stage_root / Path(INTERNAL)
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(rebuilt)
    dist = ROOT / "dist" / "ASA_RU_Fix_P.pak"
    dist.parent.mkdir(parents=True, exist_ok=True)
    dist.unlink(missing_ok=True)
    run_repak(repak, "pack", "--version", "V11", "--mount-point", "../../../", "--quiet", str(stage_root), str(dist))
    listing = run_repak(repak, "list", str(dist))
    entries = [line.strip().replace("\\", "/") for line in listing.splitlines() if line.strip()]
    if entries != [INTERNAL]:
        raise RuntimeError(f"patch PAK contains unexpected entries: {entries!r}")
    info = run_repak(repak, "info", str(dist))
    if "mount point: ../../../" not in info or "version: V11" not in info:
        raise RuntimeError(f"patch PAK has unexpected mount point/version:\n{info}")
    print(f"PAK mount point: ../../../; entry: {entries[0]}; version: V11")

    verify_root = work / "pak_verify"
    verify_root.mkdir(parents=True, exist_ok=True)
    extracted = verify_root / Path(INTERNAL)
    extracted.unlink(missing_ok=True)
    run_repak(repak, "unpack", "--quiet", "--force", "--output", str(verify_root), "--include", INTERNAL, str(dist))
    if not extracted.is_file():
        raise RuntimeError("patch PAK could not be extracted back to ShooterGame.locres")
    extracted_resource = parse(extracted.read_bytes())
    for key, value in corrections.items():
        if extracted_resource.as_dict().get(key) != value:
            raise RuntimeError(f"correction did not survive PAK round-trip: {key!r}")
    if extracted.read_bytes() != rebuilt:
        raise RuntimeError("LOCRES bytes extracted from patch PAK differ from the rebuilt input")
    detail = "; ".join(part.strip() for part in info.splitlines() if part.strip())
    print(f"Verified patch: {dist} ({dist.stat().st_size:,} bytes); {detail}; reopened and extracted LOCRES v{extracted_resource.version}, {len(extracted_resource.entries):,} keys")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, LocresError, RuntimeError) as exc:
        print(f"BUILD ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
