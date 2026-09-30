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

Review the **FINAL V1 CANDIDATE** `dist/ASA_RU_Fix_P.pak` and [manual test plan](V1_CANDIDATE.md). Build never installs it. After an ARK update, run `python build.py` again: it freshly extracts the official resources without reusing a stale translation dump.

Our `tools/pakv12.py` validates footer/index SHA-1, full directory exact lookup, compact entries, local headers and Oodle blocks. It uses a reusable local **ooz DLL through ctypes**, prepared once by bootstrap. No proprietary Oodle DLL or other installed game is required. repak v0.2.3 writes V11 with mount `../../../`; build verifies list/info/unpack and compares all extracted LOCRES bytes with the rebuilt input. Every correction is checked against stock EN/RU keys, exact placeholders and RichText structure before serialization. After unpacking the PAK, every correction must match its expected value; counts and artifact SHA-256 are recorded in ignored `work/build_validation.json`.

Scope: ASA's current **unencrypted PAK V12**, compact entries, None/Oodle compression. Unsupported versions, encrypted index/payload, missing exact paths, unknown compression and malformed ranges fail explicitly. Metadata and each extracted resource are capped at 64 MiB. Future storage-format changes may require reader updates; no silent alternative extractor exists. Use trusted installed game content: upstream ooz is not fuzz safe.

## Bootstrap cache

Artifacts, pinned source and licenses stay in ignored `work/tools/`. repak's official v0.2.3 ZIP and every ooz source file have pinned SHA-256. Bootstrap reuses verified downloads, restores repak from its cached ZIP if needed, and reuses ooz only when its source/build recipe and recorded DLL hash match. It does not download or compile on every run. Delete `work/tools/ooz/build.json` to rebuild from pinned source. Nothing is downloaded by `build.py`.

## Corrections

Edit `data/corrections.json`: JSON `namespace\tkey` -> replacement Russian text. Every key must exist in current official RU LOCRES. Only explicit translations are stored in Git; the complete rebuilt resources are generated in ignored `work/`.

Follow the Russian UI sentence case rules in [TRANSLATION_STYLE.md](TRANSLATION_STYLE.md). The first correction fixes the mode selection screen's Back button: official `спина` -> `Назад`, with an uppercase first letter even though the EN source is `back`. Its in-game end-to-end test passed, as reported by the user in [TESTING.md](TESTING.md). `data/additions.json` stores explicitly reviewed EN-only ShooterGame keys. Build copies their EN namespace/key/source hashes and inserts them in native EN order into the stock RU base, then rebuilds string tables/refcounts. Keys already present in RU, unknown EN keys or incompatible stock order fail explicitly. Review English changes with `python delta.py OLD_EN.json NEW_EN.json`.

The current **FINAL V1 CANDIDATE** extends the user-confirmed stable 1019-correction batch with screenshot batches 26–30. Later batches override earlier reviewed values explicitly; ordinary candidate import still rejects unexplained conflicts. Batch 27 JSON was absent, so its exact 61 `FIX` values were recovered from the supplied CSV into ignored `work/review/`. Two of those keys are EN-only and included in the **43 additions**, separate from **1167 corrections**; `MOD ARKS` follows the user’s final `КАРТЫ ИЗ МОДОВ` revision. See [V1_CANDIDATE.md](V1_CANDIDATE.md) for counts and limitations.

`data/engine_ru.json` contains only confirmed `InputKeys` identities. Engine EN/RU resources are freshly extracted from the same installed V12 PAK. Existing RU keys are corrected; an explicitly requested EN-only key is inserted by the same safe merge. Production packs both Engine RU and ShooterGame RU LOCRES, then reopens both and verifies every translation and byte. `Tilde` has no confirmed InputKeys entry in the current resources and is not guessed.

Targeted widget research found collected FText for `WEIGHT` and `Crafting Requirements`, but no proven orphan identity explaining the reported English UI instances. Fresh source-hash checks also confirmed matching EN/RU/asset hashes for both strings, so no source-hash synchronization is needed. No orphan entries are generated. Research tools/assets remain in ignored `work/` and are not production dependencies.

Final cleanup imported only batches 29/30: five new corrections, two authorized Hide Hat revisions to `Кожаная шапка`, and one exact SHOW BUFFS duplicate. Companion Speed Booster is `Усилитель скорости компаньона`. Ten root review CSV/JSON files were archived byte-for-byte under ignored `work/review/archive-2026-09-30/`; the root is clear of review artifacts. Only the user’s [manual smoke-test](V1_CANDIDATE.md#manual-smoke-test-plan) remains before v1. WEIGHT/Crafting Requirements remain documented limitations and do not count as a v1 smoke-test failure.

For future reviewed candidates, first run the production build to refresh the stock dumps, then run `python -m tools.corrections --candidate PATH_TO_CUMULATIVE.json` for a dry-run preflight. `--expected-new` and `--expected-total` can enforce batch counts; `--apply` writes a sorted UTF-8 corrections file only after validation succeeds. Conflicting existing values, duplicate JSON keys, missing official keys, empty replacements, changed placeholders and damaged RichText fail explicitly. Rebuild with `python build.py` after importing.

## Deterministic translation audit

After a build refreshes official `work/en.json` and `work/ru.json`, run:

```powershell
python tools/audit.py
```

The standard-library script deterministically exports `audit/all_strings.csv`, `audit/suspicious.csv`, separate missing-key and grouped consistency CSVs, and `audit/summary.json`. CSVs use UTF-8 with BOM and proper quoting. The audit uses mechanical filters only: it uses no AI, does not judge translation quality, and never edits translations or corrections. It always reads **stock** `work/en.json` and `work/ru.json`; `our_ru` and `already_corrected` expose project corrections separately, without masking official errors. It never reads patched `work/ru_rebuilt.json`. Generated `audit/` files are gitignored.

`python -m unittest discover -s tests -v` includes focused audit fixtures for CSV quoting, placeholders, markup, missing keys, repeated source/translation, known terms and corrections.

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
