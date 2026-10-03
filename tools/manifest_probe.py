"""Read the current public Steam manifest with DepotDownloader 3.4.0 only."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

APP_ID = "2430930"
DEPOT_ID = "2430931"
DEPOTDOWNLOADER_VERSION = "3.4.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _reject_paks(work_root: Path) -> None:
    if any(path.is_file() and path.suffix.lower() == ".pak" for path in work_root.rglob("*")):
        raise RuntimeError(f"PAK files are forbidden in manifest probe work directory: {work_root}")


def _execute(command: list[str], cwd: Path, run: Callable, timeout: int) -> str:
    try:
        result = run(
            command, cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"DepotDownloader could not complete: {exc}") from exc
    output = result.stdout + result.stderr
    if result.returncode:
        raise RuntimeError(f"DepotDownloader failed ({result.returncode}):\n{output[-6000:]}")
    if "was not used." in output:
        raise RuntimeError(f"DepotDownloader rejected an argument:\n{output[-6000:]}")
    return output


def _read_manifest_id(content_root: Path) -> str:
    files = list(content_root.glob("manifest_*.txt"))
    if len(files) != 1 or not files[0].is_file():
        raise RuntimeError(f"Expected exactly one fresh manifest text file, found {len(files)}")
    path = files[0]
    filename = re.fullmatch(r"manifest_([0-9]+)_([0-9]+)\.txt", path.name)
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Cannot read manifest text: {exc}") from exc
    # Exact header emitted by DumpManifestToTextFile in the pinned 3.4.0 source.
    if not filename or filename[1] != DEPOT_ID or len(lines) < 10:
        raise RuntimeError("Invalid manifest text filename or incomplete header")
    if lines[0].rstrip() != f"Content Manifest for Depot {DEPOT_ID}" or lines[1] != "":
        raise RuntimeError("Invalid manifest text depot header")
    ids = [match[1] for line in lines if (match := re.fullmatch(
        r"Manifest ID / date     : ([0-9]+) / .+?\s*", line))]
    if len(ids) != 1 or not re.fullmatch(r"Manifest ID / date     : ([0-9]+) / .+?\s*", lines[2]):
        raise RuntimeError("Missing or ambiguous manifest text ID header")
    manifest_id = ids[0]
    if manifest_id != filename[2] or len(manifest_id) > 20 or not 0 < int(manifest_id) < (1 << 64) - 1:
        raise RuntimeError("Manifest text ID does not match its filename or is invalid")
    for line, label in zip(lines[3:7], (
        "Total number of files  ", "Total number of chunks ",
        "Total bytes on disk    ", "Total bytes compressed ",
    )):
        if not re.fullmatch(re.escape(label) + r": [0-9]+\s*", line):
            raise RuntimeError("Invalid manifest text metadata header")
    if lines[7:9] != ["", ""] or lines[9] != (
        "          Size Chunks File SHA                                 Flags Name"
    ):
        raise RuntimeError("Invalid manifest text file table header")
    return manifest_id


def probe_manifest(
    executable: Path, work_root: Path, run: Callable = subprocess.run,
) -> dict[str, object]:
    """Fetch fresh metadata for the current public manifest; download no depot files.

    ``downloaded_bytes`` counts depot content chunks. Steam metadata network traffic
    is not included; ``metadata_bytes_on_disk`` reports the temporary metadata size.
    """
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise RuntimeError(f"DepotDownloader is missing: {executable}")
    work_root = Path(work_root).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    _reject_paks(work_root)
    with tempfile.TemporaryDirectory(prefix="current-public-", dir=work_root) as directory:
        isolated_root = Path(directory)
        version_output = _execute([str(executable), "--version"], isolated_root, run, 30)
        versions = re.findall(r"^DepotDownloader v([^\r\n]+)$", version_output, re.MULTILINE)
        if len(versions) != 1 or not re.fullmatch(r"3\.4\.0(?:\+[A-Za-z0-9.-]+)?\r?", versions[0]):
            raise RuntimeError(f"Manifest probe requires DepotDownloader {DEPOTDOWNLOADER_VERSION}:\n{version_output[-2000:]}")
        content_root = isolated_root / "content"
        command = [
            str(executable), "-app", APP_ID, "-depot", DEPOT_ID,
            "-branch", "public", "-manifest-only", "-dir", str(content_root),
        ]
        output = _execute(command, isolated_root, run, 300)
        _reject_paks(work_root)
        summaries = re.findall(
            r"^Total downloaded: ([0-9]+) bytes \(([0-9]+) bytes uncompressed\) from ([0-9]+) depots\r?$",
            output, re.MULTILINE,
        )
        if summaries != [("0", "0", "1")]:
            raise RuntimeError(f"Invalid manifest-only download summary:\n{output[-4000:]}")
        manifest_id = _read_manifest_id(content_root)
        metadata_bytes = sum(path.stat().st_size for path in isolated_root.rglob("*") if path.is_file())
        return {
            "app_id": APP_ID, "depot_id": DEPOT_ID, "manifest_id": manifest_id,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "downloaded_bytes": 0, "metadata_bytes_on_disk": metadata_bytes,
            "depotdownloader_version": versions[0].strip(), "branch": "public",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the JSON result to this path")
    args = parser.parse_args(argv)
    try:
        report = probe_manifest(
            PROJECT_ROOT / "work/tools/depotdownloader/DepotDownloader.exe",
            PROJECT_ROOT / "work/manifest-probe",
        )
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
    except (RuntimeError, OSError) as exc:
        print(f"Manifest probe failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
