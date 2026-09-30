# Standalone verification — 2026-09-30

## FINAL V1 CANDIDATE

See [V1_CANDIDATE.md](V1_CANDIDATE.md) for the current artifact, counts, targeted widget evidence and manual test plan. The stable 1019-correction version was reported by the user as working in the real game. The new additions/Engine candidate requires a new manual game test; the agent does not launch ARK or install the patch.

Production commands:

```powershell
python build.py
python -m unittest discover -s tests -v
python tests/standalone_build.py
```

**2026-10-01 candidate:** 1167/1167 corrections, 43/43 ShooterGame additions and 21/21 Engine edits match after PAK extraction. **62 tests pass**; the guarded build reports zero forbidden accesses and four cached repak calls. WEIGHT/Crafting Requirements EN/RU/asset source hashes match, so source-hash sync is not implemented. The explicit regression test ensures ordinary corrections retain stock source hashes.

Final cleanup batch 29: 4 NEW, 0 REVISION, 1 EXACT_DUPLICATE; batch 30: 1 NEW, 2 REVISION, 0 EXACT_DUPLICATE. Corrections increase 1162 -> 1167; additions/Engine JSON bytes remain unchanged. Reopened PAK samples confirm Back, Carcharo Saddle, Burrowbuck Saddle, Greenhouse Triangle Roof & Corner, Tinkering Desk, both Hide Hat identities, Companion Speed Booster, Adobe Gateway and three Engine InputKeys. Placeholder/RichText issues: zero. repak info/list/unpack: PASS. All ten root review files were archived with SHA-256 verification; no root review CSV/JSON remains. Current artifact and compact smoke-test are recorded in V1_CANDIDATE.md; WEIGHT/Crafting Requirements are accepted v1 limitations.

Tests cover requested EN-only insertion in native position, EN namespace/key/source hash copying, namespace positioning, incompatible order rejection, corrections coexisting with additions, Engine existing/missing keys, both PAK entries, unexpected PAK files, every post-unpack edit and the screenshot regressions. Widget orphan creation is not implemented because no orphan identity was confirmed. All current placeholder/RichText preflights and reopened resource verification must pass. Historical results below refer to their earlier artifacts.

## Historical stable batch — 1019 corrections

Input: `review_cumulative_1059_corrections_candidate.json`, 1059 external semantic-review candidates; original SHA-256 `a95aa3060c4967aed9a9de04918a0b43d7ed4e0d6ef7c6a10fcc264a8a271b76`. Fresh production extraction confirmed 39,201 EN and 35,407 RU keys. The initial preflight rejected 41 keys absent from stock RU and three damaged RichColor replacements. Following the user's instructions, the 41 keys were preserved in ignored `work/review/deferred_missing_ru.json`; the three exact user-provided replacements were applied only in `work/review/importable_1018.json`. Original review files were archived unchanged in `work/review/`.

Final merge: **1018 new + 1 existing = 1019 corrections**, zero conflicts and zero invalid/missing keys in the imported subset. `data/additions.json` remains empty. Mechanical preflight passed for all corrections, including 236 strings with placeholders and 23 with RichText. Source template boundaries such as `{color} ... </>` remain identical to EN; decorative `<<TEXT>>` is excluded from markup parsing.

`python build.py` passed with cached standalone tools. repak pack/info/list/unpack verified V11, mount `../../../`, and exactly the RU LOCRES entry. The reopened PAK-extracted LOCRES contains all **1019 / 1019 matching corrections; zero mismatches**, and its complete dictionary equals stock RU plus corrections. The extracted bytes equal the rebuilt input. Report: ignored `work/build_validation.json`.

- Historical stable PAK: `dist/ASA_RU_Fix_P.pak`
- Size: **4,964,623 bytes**
- SHA-256: `5486fad804ee4215aea29cc57e7719562646b59d39812d6d8cf069968812c28d`

Regression checks confirm `Content<TAB>1408111756 = Назад`, `GraphLiteral<TAB>63761803 = Играть`, and imported corrections for Master Volume, Music Volume, SFX Volume, Turret and Manta Ray. Placeholder samples were compared against EN, stock RU and the reopened PAK resource; their exact source tokens survive.

The post-import stock audit reports **1019 already_corrected** entries. Every audit RU value still equals stock RU, and every `our_ru` matches corrections. Stock EN/RU dump hashes and stock diagnostic counts are unchanged by the batch, proving that patched localization does not hide official errors.

**51 unit tests pass**, including candidate merge/identical duplicates, conflict rejection, invalid and missing keys, placeholder names with spaces, repetition, printf positions/precision, Cyrillic token corruption, RichText balance/source fragments, duplicate JSON rejection, and verification of all applied corrections. The batch PAK was not installed or tested in the running game by the agent; the earlier user-confirmed Back-button test below remains the in-game evidence.

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

Our LOCRES writer gave byte-identical no-op round-trips for **both EN and RU**. Modified RU: V3, 35,407 keys, 4,975,184 bytes. Complete dictionary equals official RU plus one correction.

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
- Size: **4,975,848 bytes**.
- SHA-256: `29e5ce8fff961b924ef8c63dd6f88d1d39ed834921d8648362ac801dd6650ae0`.
- **V11**, mount **../../../**, no encryption/compression.
- Exactly one file: `ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres`.
- repak info/list/unpack passed. Reopened LOCRES equals rebuilt input byte for byte; V3, all 35,407 keys verified.

Correction confirmed after final PAK extraction:

| Key | Official EN | Official RU | Patch |
|---|---|---|---|
| `Content<TAB>1408111756` | back | спина | Назад |

## In-game end-to-end test — PASSED

On 2026-09-30, the user reported a successful end-to-end test in the real game.
The temporary marked translation appeared instead of stock `спина` on the mode
selection screen: cards for Dragontopia, Tides of Fortune, Join Game, Create or
Resume Game and Mod List; the Back button is at the bottom center. This visually
confirms the string's location and that the patch PAK overrides stock localization.

Confirmed key: `Content<TAB>1408111756`; EN source: lowercase `back`;
official RU: `спина`; final corrected RU: **Назад**. The uppercase first letter
follows [TRANSLATION_STYLE.md](TRANSLATION_STYLE.md).

The successful game test used the temporary marker. Finalization removes that
marker; the final unmarked artifact was checked through repak info/list/unpack
and a repeated LOCRES parse. `Content<TAB>1408111756` equals `Назад`, and
`GraphLiteral<TAB>63761803` equals official `Играть`. No test marker remains in
corrections, any final LOCRES string, or its UTF-8/UTF-16 bytes. The complete
parsed dictionary equals official RU plus the one final correction.

During finalization the agent did not launch ARK, install the new PAK, access
DevKit or change installed game files. The final unmarked PAK has not been
retested in the running game by the agent. Server/anti-cheat compatibility is
not established by the reported UI test.

**DevKit can be removed without affecting this verified standalone build.** Future updates in the supported V12/Oodle/LOCRES format are read afresh. Format changes deliberately produce an explicit error, requiring a reader update.
