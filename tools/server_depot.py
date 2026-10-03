"""Pinned Steam Dedicated Server source and LOCRES input validation."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from tools.locres import LocresError, parse

APP_ID = "2430930"
DEPOT_ID = "2430931"
PINNED_MANIFEST = "3251368963427721326"
SERVER_PAK_RELATIVE = Path("ShooterGame/Content/Paks/pakchunk0-WindowsServer.pak")
EXPECTED_PAK_SIZE = 10_795_036
EXPECTED_PAK_SHA256 = "914589668aa41516915a68ef233873f4aeeedf570db70a7232e36ff9e8c04f2b"


@dataclass(frozen=True)
class StockSpec:
    relative_path: str
    size: int
    sha256: str
    entries: int
    version: int = 3


PINNED_STOCK: dict[str, StockSpec] = {
    "ShooterGame EN": StockSpec(
        "../../../ShooterGame/Content/Localization/ShooterGame/en/ShooterGame.locres",
        3_669_617, "efb6606905da0c3b5883c2472b253db5e22f5cd2e948cb0d1601b565ce41a216", 39_444),
    "ShooterGame RU": StockSpec(
        "../../../ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres",
        4_996_378, "be8b5d46901bc3780be0454dbc9545908cdb35b6cc59cd5dd48315d9887a1d44", 35_598),
    "Engine EN": StockSpec(
        "../../../Engine/Content/Localization/Engine/en/Engine.locres",
        3_909_182, "c0ae7e3dc9fb0f38ab39064f4556737c7ebf3a7ed8bd3971dd6dd0912ddf2d30", 48_284),
    "Engine RU": StockSpec(
        "../../../Engine/Content/Localization/Engine/ru/Engine.locres",
        5_805_962, "4e9e6bc08b577c947ec67bc1168633916f464d45ce973c8a5f6de54159a9d475", 45_771),
}


def validate_stock_resources(
    resources: Mapping[str, bytes],
    *,
    specs: Mapping[str, StockSpec | Mapping[str, object]] = PINNED_STOCK,
    require_all: bool = True,
) -> dict[str, dict[str, object]]:
    """Fail closed unless pinned bytes and parsed LOCRES metadata match."""
    if require_all and set(resources) != set(specs):
        raise RuntimeError(
            f"stock LOCRES set mismatch: expected {sorted(specs)}, got {sorted(resources)}"
        )
    report: dict[str, dict[str, object]] = {}
    for name, raw in resources.items():
        if name not in specs:
            raise RuntimeError(f"unexpected stock LOCRES: {name}")
        configured = specs[name]
        if isinstance(configured, StockSpec):
            expected = {
                "size": configured.size, "sha256": configured.sha256,
                "version": configured.version, "entries": configured.entries,
            }
        else:
            expected = configured
        actual_size = len(raw)
        if actual_size != expected["size"]:
            raise RuntimeError(f"{name} size mismatch: expected {expected['size']}, got {actual_size}")
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != expected["sha256"]:
            raise RuntimeError(f"{name} SHA-256 mismatch: expected {expected['sha256']}, got {actual_hash}")
        try:
            resource = parse(raw)
        except LocresError as exc:
            raise RuntimeError(f"{name} LOCRES parse failed: {exc}") from exc
        if resource.version != expected["version"]:
            raise RuntimeError(f"{name} LOCRES version mismatch: expected {expected['version']}, got {resource.version}")
        if len(resource.entries) != expected["entries"]:
            raise RuntimeError(f"{name} entry count mismatch: expected {expected['entries']}, got {len(resource.entries)}")
        report[name] = {
            "size": actual_size, "sha256": actual_hash,
            "version": resource.version, "entries": len(resource.entries), "status": "PASS",
        }
    return report


def download_server_pak(
    executable: Path,
    work_root: Path,
    *,
    manifest: str = PINNED_MANIFEST,
    run: Callable = subprocess.run,
) -> dict[str, object]:
    """Download only the required server PAK using anonymous DepotDownloader."""
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise RuntimeError(f"DepotDownloader is missing: {executable}; run python tools/bootstrap.py")
    work_root = Path(work_root).resolve()
    content_root = work_root / "content"
    filelist = work_root / "server-pak-filelist.txt"
    content_root.mkdir(parents=True, exist_ok=True)
    filelist.parent.mkdir(parents=True, exist_ok=True)
    filelist.write_text(SERVER_PAK_RELATIVE.as_posix() + "\n", encoding="utf-8")
    pak_path = content_root / SERVER_PAK_RELATIVE
    pak_path.unlink(missing_ok=True)
    command = [
        str(executable), "-app", APP_ID, "-depot", DEPOT_ID, "-manifest", str(manifest),
        "-filelist", str(filelist), "-dir", str(content_root), "-os", "windows",
        "-language", "english", "-validate",
    ]
    result = run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = result.stdout + result.stderr
    if result.returncode:
        raise RuntimeError(f"DepotDownloader failed ({result.returncode}):\n{output[-6000:]}")
    if not pak_path.is_file() or not pak_path.stat().st_size:
        raise RuntimeError(f"DepotDownloader completed without required server PAK: {pak_path}\n{output[-4000:]}")
    pak_files = sorted(path.relative_to(content_root).as_posix() for path in content_root.rglob("*.pak"))
    if pak_files != [SERVER_PAK_RELATIVE.as_posix()]:
        raise RuntimeError(f"DepotDownloader produced unexpected PAK files: {pak_files}")
    match = re.search(r"Total downloaded:\s*([0-9,]+)\s+bytes", output)
    downloaded_bytes = int(match.group(1).replace(",", "")) if match else None
    return {
        "path": pak_path,
        "app_id": APP_ID,
        "depot_id": DEPOT_ID,
        "manifest": str(manifest),
        "downloaded_bytes": downloaded_bytes,
        "pak_size": pak_path.stat().st_size,
        "output": output,
    }
