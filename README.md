# ASA RU Fix

Russian localization fixes for ARK: Survival Ascended on Windows 11 x64. **ARK client and DevKit are not required to build.** The production pipeline reads the four pinned official EN/RU LOCRES files from the Steam Dedicated Server depot, applies corrections to the complete official RU LOCRES resources, and creates a verified patch. Official translations and generated/downloaded binaries are not committed.

## Build

Requirements:

- Windows x64 and 64-bit Python 3.12.
- First ooz compilation: **Visual Studio 2022 Build Tools**, Desktop development with C++, MSVC x64 and Windows SDK. This compiler is independent of DevKit. A cached verified DLL needs no compiler on subsequent builds/bootstrap runs.
- Internet for downloading pinned build tools and the selected Steam depot. The game client itself is not needed.

```powershell
python tools/bootstrap.py
python build.py
# Optional developer source using a local game install:
python build.py --source installed-game --game-path 'F:\SteamLibrary\steamapps\common\ARK Survival Ascended'
```

Review the **FINAL V1** artifact `dist/ASA_RU_Fix_P.pak` and [verification notes](V1_CANDIDATE.md). Russian correction conventions are documented in [TRANSLATION_STYLE.md](TRANSLATION_STYLE.md). `python build.py` only creates the patch; use the launcher below to rebuild and install it after a game update.

## Стабильная локальная v1

На время миграции стабильная локальная версия сохранена отдельно в `E:\Projects\ARK Survival\ASA-RU-Fix-legacy-v1`. Для обычного обновления перевода после патча ARK используйте этот снимок v1 и его файл **«Обновить перевод.vbs»**. Текущий `master` предназначен для сборки из закреплённого серверного манифеста и ручной облачной проверки; он не отслеживает новые версии ARK автоматически.

`python build.py` selects only `pakchunk0-WindowsServer.pak` from pinned Dedicated Server manifest `3251368963427721326`, then validates all four LOCRES files by size, SHA-256, version and entry count before translation. `--source server-pak --server-pak PATH` is available for local repeatable checks. `--source installed-game` is a developer fallback. `tools/pakv12.py` validates footer/index SHA-1, full directory exact lookup, compact entries, local headers and Oodle blocks. It uses a reusable local **ooz DLL through ctypes**, prepared once by bootstrap. No proprietary Oodle DLL or installed game is required. repak v0.2.3 writes V11 with mount `../../../`; build verifies list/info/unpack and compares all extracted LOCRES bytes with the rebuilt input. Every correction is checked against stock EN/RU keys, exact placeholders and RichText structure before serialization. The production build fails unless the final PAK matches the pinned v1 size and SHA-256; details are recorded in ignored `work/build_validation.json`.

Scope: ASA's current **unencrypted PAK V12**, compact entries, None/Oodle compression. Unsupported versions, encrypted index/payload, missing exact paths, unknown compression and malformed ranges fail explicitly. Metadata and each extracted resource are capped at 64 MiB. Future storage-format changes may require reader updates; no silent alternative extractor exists. Use trusted installed game content: upstream ooz is not fuzz safe.

## Bootstrap cache

Artifacts, pinned source and licenses stay in ignored `work/tools/`. repak v0.2.3 and DepotDownloader 3.4.0 release archives, plus every ooz source file, have pinned SHA-256. Bootstrap reuses verified downloads, restores tools from their cached archives if needed, and reuses ooz only when its source/build recipe and recorded DLL hash match. It does not download or compile on every run. Delete `work/tools/ooz/build.json` to rebuild from pinned source.

## Manual cloud build

The GitHub Actions workflow [cloud-build.yml](.github/workflows/cloud-build.yml) is triggered only by `workflow_dispatch`. It runs on `windows-latest` with Python 3.12, bootstraps pinned tools, downloads only the required server PAK from the pinned manifest, runs the production build and full tests, then uploads `ASA_RU_Fix_P.pak`, `cloud-build-report.json` and a compact validation log as `asa-ru-fix-cloud-build` for three days. It does not publish releases or change repository contents. Build pins, input hashes and local/cloud verification notes are in [docs/cloud-build.md](docs/cloud-build.md) and [TESTING.md](TESTING.md). Start it from the repository's Actions tab when a cloud verification is needed.

## Corrections

Edit `data/corrections.json`: JSON `namespace\tkey` -> replacement Russian text. Every key must exist in current official RU LOCRES. Only explicit translations are stored in Git; the complete rebuilt resources are generated in ignored `work/`.

Follow the Russian UI sentence case rules in [TRANSLATION_STYLE.md](TRANSLATION_STYLE.md). The first correction fixes the mode selection screen's Back button: official `спина` -> `Назад`, with an uppercase first letter even though the EN source is `back`. Its in-game end-to-end test passed, as reported by the user in [TESTING.md](TESTING.md). `data/additions.json` stores explicitly reviewed EN-only ShooterGame keys. Build copies their EN namespace/key/source hashes and inserts them in native EN order into the stock RU base, then rebuilds string tables/refcounts. Keys already present in RU, unknown EN keys or incompatible stock order fail explicitly. Review English changes with `python delta.py OLD_EN.json NEW_EN.json`.

The current **FINAL V1** contains 1200 corrections, 43 ShooterGame additions and 21 Engine edits. Batch 33 distinguishes equipment slots: LEGS remains «Ноги» and FEET is «Ступни». The artifact passed production build, repak info/list/unpack, repeated LOCRES validation and all 67 original tests. See [V1_CANDIDATE.md](V1_CANDIDATE.md) for artifact details, verification and known limitations.

`data/engine_ru.json` contains only confirmed `InputKeys` identities. Engine EN/RU resources are freshly extracted from the same installed V12 PAK. Existing RU keys are corrected; an explicitly requested EN-only key is inserted by the same safe merge. Production packs both Engine RU and ShooterGame RU LOCRES, then reopens both and verifies every translation and byte. `Tilde` has no confirmed InputKeys entry in the current resources and is not guessed.

Targeted widget research found collected FText for `WEIGHT` and `Crafting Requirements`, but no proven orphan identity explaining the reported English UI instances. Fresh source-hash checks also confirmed matching EN/RU/asset hashes for both strings, so no source-hash synchronization is needed. No orphan entries are generated. Research tools/assets remain in ignored `work/` and are not production dependencies.

Final cleanup imported only batches 29/30: five new corrections, two authorized Hide Hat revisions to `Кожаная шапка`, and one exact SHOW BUFFS duplicate. Companion Speed Booster is `Усилитель скорости компаньона`. Ten root review CSV/JSON files were archived byte-for-byte under ignored `work/review/archive-2026-09-30/`; the root is clear of review artifacts. The project status is FINAL V1; an optional [manual smoke-test](V1_CANDIDATE.md#manual-smoke-test-plan) is documented for the user. WEIGHT/Crafting Requirements remain documented limitations and do not count as a v1 smoke-test failure.

Историческая сверка после обновления ARK перенесла `GraphLiteral\t2415568346` (`Teleport Destination`) из additions в corrections: ключ появился в stock RU с другим переводом. Этот перенос предшествовал Batch 32/33; актуальные totals FINAL V1 приведены выше. Сверка сохранена в ignored `work/review/update_reconciliation.json`.

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

The second command reruns the complete production build from the already downloaded server PAK with filesystem, DLL, import and process guards; only cached repak may run. Set `ASA_TEST_SERVER_PAK` to use a server PAK from another cache location. `tests/compare_devkit.py --unrealpak PATH_TO_REFERENCE_TOOL` is a historical optional development oracle comparison, never imported by production and not needed for this pipeline. Recorded results: [TESTING.md](TESTING.md).

## Install / uninstall later

When you choose to install, preview with `./install.ps1 -WhatIf`, then run `./install.ps1`. It copies/replaces only `ASA_RU_Fix_P.pak`. Preview removal with `./uninstall.ps1 -WhatIf`; `./uninstall.ps1` removes only that patch. Game launch is separate. Future corrections need manual context checks; server/anti-cheat compatibility is not established by the verified Back button fix.

## Third-party components

- [repak](https://github.com/trumank/repak), **v0.2.3**, **MIT OR Apache-2.0**: official Windows x64 release, SHA-256 pinned; existing patch writer preserved.
- [powzix/ooz](https://github.com/powzix/ooz/tree/05038060aa68f9187ae9923b2388ca8db40e58d1), commit **05038060aa68f9187ae9923b2388ca8db40e58d1**, **GPL-3.0-or-later**: bootstrap compiles its decoder with our GPL C ABI bridge. Source, full license and DLL remain cache artifacts.
- [TradFR](https://github.com/valentin-gosselin/ark-ascended-fr) was studied as a format reference. No explicit project license was found at the inspected commit; no source was copied verbatim.

Provenance, license evidence and compilation details: [THIRD_PARTY.md](THIRD_PARTY.md).
