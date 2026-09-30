# ASA RU Fix

Windows-first project for Russian localization fixes in ARK: Survival Ascended. Each build extracts the currently installed official RU LOCRES and applies only project corrections; the full official translation is generated under ignored `work/` and is not kept in Git.

## Build

Requirements: Windows, Python 3.10+, Steam-installed ASA, ARK DevKit from Epic Games Launcher, and repak v0.2.3. Install repak into the ignored project cache with `python tools/bootstrap.py`; the script checks the official release ZIP SHA-256 before extracting it. The build auto-detects Steam libraries through `libraryfolders.vdf`, finds `UnrealPak.exe` from the Epic `ARK DevKit` manifest, and uses `work/tools/repak.exe` to write the patch.

```powershell
python tools/bootstrap.py
python build.py
# If automatic discovery is ambiguous or unavailable:
python build.py --game-path 'F:\SteamLibrary\steamapps\common\ARK Survival Ascended' --unrealpak 'D:\ARKDevkit\Engine\Binaries\Win64\UnrealPak.exe'
```

The current DevKit UnrealPak reads ASA's PAK v12 and extracts the two LOCRES files. repak writes a PAK v11 with mount point `../../../`; the build lists and unpacks it again to verify its exact path and contents. Output is `dist/ASA_RU_Fix_P.pak`; build never installs it. Extracted official files, dumps, staging files, tools, and verification files stay in ignored `work/`.

## Corrections

Edit `data/corrections.json` as a JSON object from `namespace\tkey` to replacement Russian text. The key must exist in the currently installed official Russian LOCRES or the build fails. The current entry is a temporary `[RU FIX TEST]` marker documented in [TESTING.md](TESTING.md); remove it after the in-game check. `data/additions.json` remains empty and experimental: additions are rejected by the build.

After an ARK update, run `python build.py` again to use the new official RU base. To review English-source changes between dumps, run `python delta.py OLD_EN.json NEW_EN.json`.

## Install / uninstall

After reviewing the PAK, install it later with `./install.ps1`; preview with `./install.ps1 -WhatIf`. It copies/replaces only `ASA_RU_Fix_P.pak`. Remove only that file with `./uninstall.ps1`; preview with `./uninstall.ps1 -WhatIf`.

No claim is made about official server or anti-cheat compatibility.

## Tools and references

- LOCRES extraction from the source PAK: locally installed ARK DevKit `UnrealPak.exe` (not copied into this repository). It handles the game's Oodle-compressed files; no Oodle DLL is copied or required by our Python code.
- Patch PAK writer/reader: [`trumank/repak`](https://github.com/trumank/repak), v0.2.3, MIT OR Apache-2.0. Bootstrap URL is the official Windows x64 release ZIP and its SHA-256 is pinned in `tools/bootstrap.py`. repak does not read the source game's PAK v12 in this workflow; it writes and reopens our PAK v11.
- [TradFR](https://github.com/valentin-gosselin/ark-ascended-fr) and [ASA_fix_ru_loc](https://github.com/LeXa4894/ASA_fix_ru_loc) were technical references only. No source or binary from either project was copied; neither repository page exposed a license file.
