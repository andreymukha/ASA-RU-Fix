# FINAL V1 — серверный stable channel

Серверная автоматизация готова. Проверенный [Release v1.0.0](https://github.com/andreymukha/ASA-RU-Fix/releases/tag/v1.0.0) и [stable.json](https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/stable.json) доступны публично. Клиентский updater и пользовательская доставка ещё не реализованы.

Текущие authoritative данные: 1243 desired ShooterGame в `data/shootergame_ru.json`, 21 Engine в `data/engine_ru.json`, 1264 принятые EN identities. На текущем manifest `3251368963427721326` динамические классы ShooterGame = 1199/43/1; Engine = 16/1/4 (corrections/additions/already_correct). Старые corrections/additions объединены без изменения русских текстов.

PAK: 10795036 bytes; SHA-256 `914589668aa41516915a68ef233873f4aeeedf570db70a7232e36ff9e8c04f2b`. Pinned и live hosted builds, все desired values, format/repak проверки и 168 tests — PASS. Повторный hosted run доказал fast path без скачивания server PAK; расписание включено после PASS. Подробные доказательства — [серверный отчёт](docs/server-automation-verification.md) и [TESTING.md](TESTING.md).

Известные ограничения сохранены: WEIGHT / Crafting Requirements могут оставаться английскими в отдельных виджетах; CS/Cybers Structures не относятся к базовому переводу. ARK, DevKit и локальная установка в этом этапе не запускались. Legacy snapshot сохранён; массового перевода или нового asset scan не было.

## Архив финализации локального v1

Ниже сохранены прежние исследования и batch history. Старые количества corrections/additions описывают соответствующий снимок; актуальные единые данные и динамические классы указаны выше.

# FINAL V1 — 2026-10-02

Status: **FINAL V1**. Batches 32 and 33, the fresh-stock saddle audit and slot corrections are integrated. The user confirmed the earlier Back correction in game. This final artifact passed production build, full LOCRES/PAK validation and the complete test suite. The agent did not launch ARK, install a patch, access the editor toolchain, or scan installed mods.

## Current prepared artifact

- Corrections: **1200** (including Batch 33 equipment slot corrections).
- ShooterGame additions: **43** (including the 1 new Batch 32 EN-only saddle title).
- Engine edits: **21** InputKeys entries, including 20 existing RU keys and 1 EN-only insertion (`InputKeys<TAB>Insert`).
- Targeted orphan widget entries created: **0**.
- PAK: `dist/ASA_RU_Fix_P.pak`, **10,795,036 bytes**.
- SHA-256: `914589668aa41516915a68ef233873f4aeeedf570db70a7232e36ff9e8c04f2b`.
- V11, mount `../../../`, exactly these files:

```text
Engine/Content/Localization/Engine/ru/Engine.locres
ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres
```

The user authorized both additional batch 27 EN-only keys on 2026-10-01. They were included in additions: `GraphLiteral<TAB>1863176983` (`, WIND:` -> `, ВЕТЕР:`) and `GraphLiteral<TAB>3285020872` (`MOD ARKS` -> `КАРТЫ ИЗ МОДОВ`). The latter translation follows the user's latest revision, overriding the archived CSV's `МОДОВЫЕ КАРТЫ`. They were separate from corrections in the pre-update artifact. After the update, `GraphLiteral<TAB>2415568346` moved into corrections, leaving 42 active additions.

## Historical screenshot import — batches 26–28

Applied explicit priority 28 > 27 > 26 > stable data. Count before each step:

| Batch | Input | New corrections | Revisions | Exact duplicates | EN-only keys |
|---|---:|---:|---:|---:|---:|
| 26 | 88 | 78 | 10 | 0 | 0 |
| 27 | 61 | 59 | 0 | 0 | 2 |
| 28 | 9 | 6 | 3 | 0 | 0 |

Batch 27 JSON was absent. Its 61 exact `FIX`/`proposed_ru` CSV rows were recovered without semantic changes into `work/review/review_batch_27_corrections_candidate_recovered.json`. Source review files were preserved. Per-key revisions and preflight results are in `work/review/screenshot_import_validation.json`. Ordinary generic candidate import continues to reject different existing values; these revisions were explicitly authorized for this batch sequence.

## Reconciled against the 2026-10-01 installed game update

The production backend extracted all four current stock LOCRES from the installed source PAK (SHA-256 `0c5be928a4c59c66dffa34561daea87e40136618d084390b6919b7bb15c7f027`). New ShooterGame counts: EN **39,444**, RU **35,598**. Previous counts were 39,201 EN / 35,407 RU, for net changes of +243 / +191. Engine counts stayed 48,284 EN / 45,771 RU. The old full key lists and value snapshots were not preserved, so exact set-addition/removal counts and stock changed-value counts cannot be recovered from count deltas alone.

Of 43 previous additions, **42 remain EN-present/RU-missing**. `GraphLiteral<TAB>2415568346` now exists in EN and RU: EN `Teleport Destination`, our value `Точка назначения телепорта`, new stock RU `Пункт назначения телепортации`. It was moved to corrections to preserve our translation. No addition is now redundant with stock RU; no addition key disappeared from EN. All **1167** previous corrections remain in RU with EN present. The correction-to-addition, removed-key and anomaly counts are zero. All 21 Engine keys still exist in EN; 20 have RU entries and `InputKeys<TAB>Insert` remains a valid EN-only insertion.

Stock deltas and classifications: `work/review/update_reconciliation.json`. Fresh dumps replace the prior ignored JSON dumps. `python tools/audit.py` ran mechanically on current stock resources: 4,266 missing RU keys, 7 missing EN keys and 1,936 suspicious candidates; no semantic review was performed.

## Final cleanup — batches 29–30

Only these two new candidate JSON files were imported; older review files were not merged again. Authorized priority: batch 30 > batch 29 > previous authoritative corrections.

| Batch | NEW | REVISION | EXACT_DUPLICATE | CONFLICT |
|---|---:|---:|---:|---:|
| 29 | 4 | 0 | 1 | 0 |
| 30 | 1 | 2 | 0 | 0 |

Corrections: **1167 -> 1168** after migrating one now-present addition. Additions: **43 -> 42**. SHOW BUFFS is an exact duplicate and adds no key. Both Hide Hat identities now equal **Кожаная шапка**: the screenshot confirms an item of clothing, with `hide` meaning leather. Companion Speed Booster equals **Усилитель скорости компаньона**. The Engine data file remains byte-identical to the previous candidate (21 edits).

All **10** root review CSV/JSON artifacts were moved without overwrite to ignored `work/review/archive-2026-09-30/`. Each SHA-256 was verified before and after the move; `manifest.json` records filename, hash, size and purpose. No root review CSV/JSON remains; no review artifact is committed. Reports: `work/review/final_cleanup_preflight.json` and `work/review/final_v1_verification.json`.

## Earlier production snapshot — 2026-10-01 (superseded by FINAL V1 below)

The following 2026-10-01 figures describe the previous snapshot only. Current FINAL V1 totals and validation are recorded in the Batch 33 section below.

## Missing RU mechanism and validation

RU remains the base. Only requested missing keys are copied from current EN, including namespace/key FStrings and namespace/key/source hashes. Existing RU entry metadata and translations remain intact except requested corrections. Insertion follows actual EN sequence, with no arbitrary append; incompatible RU/EN order is rejected. Serialization rebuilds unique strings and refcounts. Both current stock RU resources are EN subsequences.

Fresh production build and standalone guarded build passed. After repak info/list/unpack and repeated LOCRES parse:

- **1168/1168 corrections**, **42/42 ShooterGame additions**, **21/21 Engine edits**: MATCH, zero mismatches.
- ShooterGame: 35,598 stock RU + 42 additions = **35,640 keys**.
- Engine: 45,771 stock RU + Insert = **45,772 keys**.
- Full dictionaries equal stock RU plus explicit edits; every stock identity hash remains unchanged.
- Copied EN hashes and native insertion order independently verified after PAK extraction.
- Zero placeholder mismatches and zero invalid RichText structures. The known source fragment `{color} ... </>` preserves its original contract.
- `Content<TAB>1408111756 = Назад`; `GraphLiteral<TAB>63761803 = Играть`.
- No `RU FIX TEST` in edit values or either LOCRES string table.
- **62 unit tests PASS**; standalone guard: **0 forbidden accesses**, four cached repak calls.

Reports/logs: `work/build_validation.json`, `work/review/final_v1_verification.json`, `work/review/final_v1_build.log`, `work/review/final_v1_unit_tests.log`, `work/review/final_v1_standalone_build.log`, `work/review/update_reconciliation.json`, `work/review/update_unit_tests.log`, `work/review/update_standalone_build.log`. The earlier `work/review/source_hash_investigation.json` remains the documented widget research evidence; no further widget repair was attempted in final cleanup.

## Adobe additions smoke test

| Key | EN source | Candidate RU |
|---|---|---|
| `Content<TAB>2584334722` | Adobe Triangle & Quarter Foundation | Саманный фундамент: треугольник и четверть |
| `Content<TAB>2814222038` | Adobe Doors & Windows | Саманные двери и окна |
| `Content<TAB>433968946` | Adobe Gateway | Саманная рама ворот |
| `Content<TAB>321451122` | Adobe Gate | Саманные ворота |
| `Content<TAB>381460240` | Adobe Behemoth Gateway | Огромная саманная рама |

## Physical keys

`data/engine_ru.json` uses confirmed `InputKeys<TAB>key` identities. Insert is copied from EN because RU lacks it. Tilde is absent in current Engine EN/RU, but the reviewed ShooterGame correction already supplies `Globals<TAB>87912519 = Тильда`. ShooterGame also corrects the actually bad `Globals<TAB>1661194396` SpaceBar (`Космический промежуток` -> `Пробел`); Engine SpaceBar already had stock `Пробел`. No invented Engine Tilde entry is created.

## Targeted widget FText — documented limitation

Studied [TradFR](https://github.com/valentin-gosselin/ark-ascended-fr/tree/8527fc5f89246fec9f67fefcb849c82db1533f7c/tools) `textes_assets.py`, `balayer_assets.py`, `cityhash.py` and orphan creation approach. Used [retoc v0.1.5](https://github.com/trumank/retoc/releases/tag/v0.1.5) to read the stock IoStore manifest and only **19 selected base UI assets** around inventory, stat panels and item/dino tooltips. ZIP SHA-256: `cc036b06ad3bdcf7003690b00d82719980c374e48a95bf0654f9959148d263aa`. No global asset translation pass and no mod scanning.

Observed exact serialized Base FText:

| Source | Asset | Namespace / key | Source hash |
|---|---|---|---|
| WEIGHT | `/Game/PrimalEarth/UI/Inventory/CharacterStatsPanel` | `Content<TAB>3707105056` | `0xDCF5EF20` |
| WEIGHT | `/Game/PrimalEarth/UI/Inventory/StructureStatsPanel` | same | same |
| WEIGHT | `/Game/PrimalEarth/UI/Inventory/CarStatsPanel` | same | same |
| Crafting Requirements | `/Game/PrimalEarth/UI/ToolTipWidgetPrimalItem` | `Content<TAB>1849252834` | `0x6E395BE2` |
| Crafting Requirements | `/Game/PrimalEarth/UI/ToolTipWidgetPrimalDino` | same | same |
| Crafting Requirements | `/Game/PrimalEarth/UI/ToolTipWidgetPrimalDino_MinimalUI` | same | same |

These triples already exist in stock EN **and RU**, with matching source hashes and RU `ВЕС` / `Для создания требуется:`. They do not establish the identity of the specific still-English instances seen by the user. No confirmed orphan was found, so no speculative entry or orphan hash implementation was added. Resolving those visible instances remains open if the manual test still shows EN. Exact asset chunks, byte offsets and SHA-256 are retained in ignored `work/review/widget_ftext_evidence.json`.

## Targeted source-hash investigation — 2026-10-01

Fresh EN/RU ShooterGame resources were extracted from the currently installed V12 PAK. Cached asset bytes were checked against their recorded SHA-256 and the exact Base FText namespace/key/source triples were read again at the recorded offsets. All found target widget FText use `Content`: WEIGHT in CharacterStatsPanel, StructureStatsPanel and CarStatsPanel; Crafting Requirements in ToolTipWidgetPrimalItem, ToolTipWidgetPrimalDino (two occurrences) and ToolTipWidgetPrimalDino_MinimalUI. No found target uses GraphLiteral or Globals; those two related identities were checked separately in LOCRES.

| Namespace/key | EN source | EN source hash | Stock RU source hash | Reopened PAK RU |
|---|---|---|---|---|
| `Content<TAB>3707105056` | WEIGHT | `0xDCF5EF20` (3707105056) | `0xDCF5EF20` (3707105056) | ВЕС |
| `GraphLiteral<TAB>3707105056` | WEIGHT | `0xDCF5EF20` (3707105056) | `0xDCF5EF20` (3707105056) | ВЕС |
| `Content<TAB>1849252834` | Crafting Requirements | `0x6E395BE2` (1849252834) | `0x6E395BE2` (1849252834) | Для создания требуется: |
| `Globals<TAB>1849252834` | Crafting Requirements | `0x6E395BE2` (1849252834) | `0x6E395BE2` (1849252834) | Для создания требуется: |

The asset source CRC32 equals current EN and RU hashes for every found Content FText. EN/RU key and namespace hashes also agree for all four identities and remain identical after rebuild/unpack. WEIGHT key hash is `1642218118`; Crafting Requirements key hash is `3397969226`. Namespace hashes: Content `2787407426`, GraphLiteral `898694521`, Globals `2087161395`. The GraphLiteral WEIGHT correction `ВЕС` was already present in the screenshot batch and remains applied; stock RU is `МАССА`.

**No source-hash mismatch was confirmed.** No source-hash sync mechanism or `data/source_hash_sync.json` was added. Production continues to retain every existing RU source hash, with a regression test explicitly proving ordinary corrections do not automatically copy EN hashes. English display of the reported widget instances remains a documented v1 limitation. No unsupported workaround or speculative orphan entry is created. Exact source/hash/value checks after repeated LOCRES parse are in ignored `work/review/source_hash_investigation.json`.

The independent ooz research adapter and compile intermediates were removed after extraction. retoc remains only in ignored `work/tools/` and is not required by production.

## Batch 32 and saddle audit — 2026-10-01

Batch 32 contained 35 reviewed corrections: **27 NEW, 3 REVISIONS, 5 exact duplicates**. Its one EN-only addition, `Content<TAB>1664294528` (`Liopleurodon Saddle`), remains absent from stock RU and is inserted natively from EN order. The resulting data has 1197 corrections, 43 additions, and 21 Engine edits.

The fresh-stock title scan found 157 short `Content` entries ending in `Saddle`. After excluding 40 special or non-creature titles (Tek/platform/lost/styled/submarine/steampunk variants, generic saddle and carriage), 117 ordinary creature saddles remain. Before this batch and audit, 115 followed the standard. Two were normalized: `Content<TAB>382284212` (`Cerberax Saddle`) → «Седло для Церберакса» and `Content<TAB>1099891526` (`Gargantar Saddle`) → «Седло для Гаргантара». All 117 now follow «Седло для <Существа>»; none remain ambiguous. See [TRANSLATION_STYLE.md](TRANSLATION_STYLE.md).

Smithy remains the stock `Content<TAB>3983703546` value «Верстак» and has no correction. Regression samples from the unpacked PAK include Tinkering Desk, Warbench, Acro, Megaraptor, Bison, Rhyniognatha and Liopleurodon saddles. Reopened PAK checks: **1197/1197 corrections, 43/43 additions, 21/21 Engine edits**; repak info/list/unpack and repeated LOCRES parse passed. Unit tests: **63 passed**; standalone guarded build passed with zero forbidden accesses. WEIGHT / Crafting Requirements remain documented noncritical limitations. No CS/Cybers Structures strings were translated.

## Batch 33 and FINAL v1 verification — 2026-10-02

Batch 33 added only three equipment slot corrections: `Content<TAB>478560471` (`FEET`) → «СТУПНИ», `Content<TAB>1576228423` (`Feet`) → «Ступни», and `GraphLiteral<TAB>1576228423` (`Feet`) → «Ступни». Existing LEGS corrections were not changed. The plain `Legs` entry remains «Ноги»; the two existing uppercase `LEGS` corrections retain their previous «НОГИ» casing.

Final counts: **1200 corrections, 43 additions, 21 Engine edits**. After repak info/list/unpack and a repeated LOCRES parse, all edits matched: **1200/1200, 43/43, 21/21**. Full correction preflight reported zero key, placeholder, printf-placeholder and RichText errors. The complete suite passed: **67 tests**. The final artifact is `dist/ASA_RU_Fix_P.pak`, 10,795,036 bytes, SHA-256 `914589668aa41516915a68ef233873f4aeeedf570db70a7232e36ff9e8c04f2b`.

Known limitations remain: WEIGHT / Crafting Requirements may still display in English despite matching LOCRES data; CS / Cybers Structures text belongs to third-party mods and is outside the base translation. No broad translation or new audit was performed for Batch 33.

## Manual smoke-test plan

1. Settings: Sound / Graphics / UI / Camera.
2. Physical key names from Engine.locres.
3. EN-only additions: Adobe Gateway / Adobe Gate / Adobe Behemoth Gateway.
4. Carcharo Saddle: **Седло для Кархародонтозавра**.
5. Hide Hat: **Кожаная шапка**.
6. Companion Speed Booster: **Усилитель скорости компаньона**.
7. The original **Назад** correction remains active.

This checklist is available for optional in-game confirmation by the user. It was not run by the agent. WEIGHT / Crafting Requirements are documented noncritical v1 limitations. Third-party CS / Cybers Structures and other mod text are outside this project’s scope.
