"""Download and verify the official repak v0.2.3 Windows x64 release."""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "work" / "tools"
URL = "https://github.com/trumank/repak/releases/download/v0.2.3/repak_cli-x86_64-pc-windows-msvc.zip"
EXPECTED_SHA256 = "6720d602144d75df477a99d5bedb6ea780997546afc335901d4937cafeaa73fa"


def main() -> int:
    TOOLS.mkdir(parents=True, exist_ok=True)
    archive = TOOLS / "repak_cli-x86_64-pc-windows-msvc.zip"
    try:
        with urllib.request.urlopen(URL, timeout=60) as response, archive.open("wb") as output:
            output.write(response.read())
    except (OSError, urllib.error.URLError) as exc:
        raise SystemExit(f"Could not download repak from the official GitHub release: {exc}") from exc
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        archive.unlink(missing_ok=True)
        raise SystemExit(f"repak archive SHA-256 mismatch: {digest}")
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
        executable = next((name for name in names if Path(name).name.lower() == "repak.exe"), None)
        if executable is None:
            raise SystemExit("Verified repak ZIP does not contain repak.exe")
        target = TOOLS / "repak.exe"
        target.write_bytes(package.read(executable))
        for license_name in ("LICENSE-MIT", "LICENSE-APACHE"):
            match = next((name for name in names if Path(name).name == license_name), None)
            if match:
                (TOOLS / license_name).write_bytes(package.read(match))
    print(f"Installed repak v0.2.3 to {TOOLS / 'repak.exe'}")
    print(f"Verified release archive SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
