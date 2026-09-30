"""Small Windows Steam library discovery helper for ARK: Survival Ascended."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP_ID = "2399830"
GAME_DIR = "ARK Survival Ascended"


def steam_roots() -> list[Path]:
    roots: list[Path] = []
    if sys.platform == "win32":
        import winreg

        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key_name in (r"Software\Valve\Steam", r"Software\WOW6432Node\Valve\Steam"):
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        value, _ = winreg.QueryValueEx(key, "SteamPath")
                    roots.append(Path(value))
                except OSError:
                    pass
    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        base = os.environ.get(env_name)
        if base:
            roots.append(Path(base) / "Steam")
    return list(dict.fromkeys(path.expanduser() for path in roots))


def steam_libraries() -> list[Path]:
    libraries: list[Path] = []
    for root in steam_roots():
        if (root / "steam.exe").is_file() or (root / "steamapps").is_dir():
            libraries.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        content = vdf.read_text(encoding="utf-8", errors="replace")
        libraries.extend(Path(value.replace("\\\\", "\\")) for value in re.findall(r'"path"\s+"([^"]+)"', content))
    return list(dict.fromkeys(path.resolve() for path in libraries))


def find_game() -> list[Path]:
    found = []
    for library in steam_libraries():
        manifest = library / "steamapps" / f"appmanifest_{APP_ID}.acf"
        game = library / "steamapps" / "common" / GAME_DIR
        if manifest.is_file() and game.is_dir():
            found.append(game.resolve())
    return found


if __name__ == "__main__":
    matches = find_game()
    if len(matches) == 1:
        print(matches[0])
    elif not matches:
        raise SystemExit("Steam install for ARK: Survival Ascended (App 2399830) was not found.")
    else:
        raise SystemExit("Multiple ARK installs found; pass an explicit game path: " + ", ".join(map(str, matches)))
