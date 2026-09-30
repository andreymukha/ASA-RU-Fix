# Standalone verification — 2026-09-30

## Fresh oracle comparison

Source: installed ASA `F:\SteamLibrary\steamapps\common\ARK Survival Ascended\ShooterGame\Content\Paks\pakchunk0-Windows.pak`, 1,565,454,770 bytes, V12, mount `../../../`, 2,360 entries, Oodle.

Optional development command, never a production prerequisite:

```powershell
python tests/compare_devkit.py --unrealpak 'D:\ARKDevkit\Engine\Binaries\Win64\UnrealPak.exe'
```

It freshly extracted exactly EN/RU using the supplied UnrealPak and our reader + independent ooz DLL. Direct byte equality and SHA-256 equality both passed. Machine-readable report: ignored `work/comparison.json`; logs/resources: `work/devkit_reference/`, `work/custom/`.

| Resource | Oracle bytes | Custom bytes | Oracle/custom LOCRES version | Oracle/custom keys | Bytes and SHA-256 |
|---|---:|---:|---:|---:|---|
| EN | 3,651,674 | 3,651,674 | 3 / 3 | 39,201 / 39,201 | MATCH |
| RU | 4,975,204 | 4,975,204 | 3 / 3 | 35,407 / 35,407 | MATCH |

EN SHA-256:

```text
UnrealPak: f5763373a3490c9c30f155beedad85c7eeb2d21da82c96b3ca2debb5a85a1681
Custom:    f5763373a3490c9c30f155beedad85c7eeb2d21da82c96b3ca2debb5a85a1681
Result: MATCH
```

RU SHA-256:

```text
UnrealPak: 82631f8928a818cebf922b4e4ee834f3e22deb44ab4e26e645cb7cb0bf4bcb78
Custom:    82631f8928a818cebf922b4e4ee834f3e22deb44ab4e26e645cb7cb0bf4bcb78
Result: MATCH
```

Our LOCRES writer gave byte-identical no-op round-trips for **both EN and RU**. Modified RU: V3, 35,407 keys, 4,975,232 bytes. Complete dictionary equals official RU plus one correction.

## Bootstrap

Bootstrap verified all source/release hashes and compiled ooz commit `05038060aa68f9187ae9923b2388ca8db40e58d1` with independent Visual Studio 2022 Build Tools. License: GPL-3.0-or-later notice in upstream kraken.cpp; MIT OR Apache-2.0 for repak. Details: [THIRD_PARTY.md](THIRD_PARTY.md).

Repeat bootstrap passed with `urllib.request.urlopen` and compiler discovery monkeypatched to raise on any call. Executable/DLL modification timestamps stayed unchanged: no network or compilation. A missing cached repak executable was also restored from its verified ZIP without network access. Unit tests confirm cache reuse and rejection of mismatching downloads without replacing the existing file.

## Production and independence proof

```powershell
python build.py
python tests/standalone_build.py
python -m unittest discover -s tests -v
```

The guard runs actual `build.py`, denies paths containing ARKDevkit/UnrealPak/EpicGamesLauncher, checks audited file/DLL opens, filesystem probes/enumeration and optional reference imports, and allows only exact cached repak process creation. It sets poisoned `ASA_UNREALPAK`. Self-tests reject a DevKit stat and an UnrealPak launch before the real build. Production succeeds with **zero forbidden accesses and four repak processes**: pack/list/info/unpack.

Static search covers all seven production code files: build.py, tools/steam.py, tools/locres.py, tools/pakv12.py, tools/oodle.py, tools/bootstrap.py, tools/ooz_bridge.cpp. No DevKit/UnrealPak/Epic lookup/reference remains. Optional oracle code is not imported; generated ooz excludes its proprietary DLL loader.

**12 unit tests pass**, covering plain/single/multiple blocks, 64-bit compact fields, explicit block size, unsupported version/method, encrypted index/payload, missing exact filename, invalid offsets, corrupt/truncated index, corrupt local header/payload, wrong decompressed size, bootstrap cache/hash rejection and Windows process audits.

## Verified artifact

- Path: `E:\Projects\ARK Survival\ASA-RU-Fix\dist\ASA_RU_Fix_P.pak`
- Size: **4,975,896 bytes**.
- SHA-256: `b49eca8222f6d6f4671ae5f9903b09ad0759a1b56c44ebbce4d1365e384dcb0e`.
- **V11**, mount **../../../**, no encryption/compression.
- Exactly one file: `ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres`.
- repak info/list/unpack passed. Reopened LOCRES equals rebuilt input byte for byte; V3, all 35,407 keys verified.

Correction confirmed after final PAK extraction:

| Key | Official EN | Official RU | Patch |
|---|---|---|---|
| `GraphLiteral<TAB>63761803` | Play | Играть | Играть [RU FIX TEST] |

## Separate manual check

ARK was not launched. PAK was not installed. No game or DevKit files were modified/deleted.

When you choose to test visually, install separately and check the early menu Play action. Widget placement, actual game loading and server/anti-cheat compatibility remain unverified. Remove the temporary correction after checking and rebuild.

**DevKit can be removed without affecting this verified standalone build.** Future updates in the supported V12/Oodle/LOCRES format are read afresh. Format changes deliberately produce an explicit error, requiring a reader update.
