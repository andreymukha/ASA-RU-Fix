# ASA RU Fix

Russian localization fixes for ARK: Survival Ascended on Windows 11 x64. **ARK DevKit: NOT REQUIRED.** Each build reads current official EN/RU resources from the installed game's PAK, applies corrections to the complete official RU LOCRES, and creates a verified patch. Official translations and generated/downloaded binaries are not committed.

## Build

Requirements:

- Windows x64, 64-bit Python 3.10+, Steam-installed ASA.
- First ooz compilation: **Visual Studio 2022 Build Tools**, Desktop development with C++, MSVC x64 and Windows SDK. This compiler is independent of DevKit. A cached verified DLL needs no compiler on subsequent builds/bootstrap runs.
- Internet for the first bootstrap download.

```powershell
python tools/bootstrap.py
python build.py
# Optional explicit game installation:
python build.py --game-path 'F:\SteamLibrary\steamapps\common\ARK Survival Ascended'
```

Review `dist/ASA_RU_Fix_P.pak`. Build never installs it. After an ARK update, run `python build.py` again: it freshly extracts the official resources without reusing a stale translation dump.

Our `tools/pakv12.py` validates footer/index SHA-1, full directory exact lookup, compact entries, local headers and Oodle blocks. It uses a reusable local **ooz DLL through ctypes**, prepared once by bootstrap. No proprietary Oodle DLL or other installed game is required. repak v0.2.3 writes V11 with mount `../../../`; build verifies list/info/unpack and compares all extracted LOCRES bytes with the rebuilt input.

Scope: ASA's current **unencrypted PAK V12**, compact entries, None/Oodle compression. Unsupported versions, encrypted index/payload, missing exact paths, unknown compression and malformed ranges fail explicitly. Metadata and each extracted resource are capped at 64 MiB. Future storage-format changes may require reader updates; no silent alternative extractor exists. Use trusted installed game content: upstream ooz is not fuzz safe.

## Bootstrap cache

Artifacts, pinned source and licenses stay in ignored `work/tools/`. repak's official v0.2.3 ZIP and every ooz source file have pinned SHA-256. Bootstrap reuses verified downloads, restores repak from its cached ZIP if needed, and reuses ooz only when its source/build recipe and recorded DLL hash match. It does not download or compile on every run. Delete `work/tools/ooz/build.json` to rebuild from pinned source. Nothing is downloaded by `build.py`.

## Corrections

Edit `data/corrections.json`: JSON `namespace\tkey` -> replacement Russian text. Every key must exist in current official RU LOCRES. Only corrections are stored in Git; the complete merged resource is generated in ignored `work/`.

Follow the Russian UI sentence case rules in [TRANSLATION_STYLE.md](TRANSLATION_STYLE.md). The first correction fixes the mode selection screen's Back button: official `спина` -> `Назад`, with an uppercase first letter even though the EN source is `back`. Its in-game end-to-end test passed, as reported by the user in [TESTING.md](TESTING.md). `data/additions.json` stays empty and experimental; non-empty additions are rejected. Review English changes with `python delta.py OLD_EN.json NEW_EN.json`.

## Optional validation

```powershell
python -m unittest discover -s tests -v
python tests/standalone_build.py
```

The second command runs the complete production build with filesystem, DLL, import and process guards; only cached repak may run. `tests/compare_devkit.py --unrealpak PATH_TO_REFERENCE_TOOL` is an optional development oracle comparison, never imported by production and not needed after removing DevKit. Recorded results: [TESTING.md](TESTING.md).

## Install / uninstall later

When you choose to install, preview with `./install.ps1 -WhatIf`, then run `./install.ps1`. It copies/replaces only `ASA_RU_Fix_P.pak`. Preview removal with `./uninstall.ps1 -WhatIf`; `./uninstall.ps1` removes only that patch. Game launch is separate. Future corrections need manual context checks; server/anti-cheat compatibility is not established by the verified Back button fix.

## Third-party components

- [repak](https://github.com/trumank/repak), **v0.2.3**, **MIT OR Apache-2.0**: official Windows x64 release, SHA-256 pinned; existing patch writer preserved.
- [powzix/ooz](https://github.com/powzix/ooz/tree/05038060aa68f9187ae9923b2388ca8db40e58d1), commit **05038060aa68f9187ae9923b2388ca8db40e58d1**, **GPL-3.0-or-later**: bootstrap compiles its decoder with our GPL C ABI bridge. Source, full license and DLL remain cache artifacts.
- [TradFR](https://github.com/valentin-gosselin/ark-ascended-fr) was studied as a format reference. No explicit project license was found at the inspected commit; no source was copied verbatim.

Provenance, license evidence and compilation details: [THIRD_PARTY.md](THIRD_PARTY.md).
