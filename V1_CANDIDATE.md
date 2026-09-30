# Russian localization v1 candidate — 2026-10-01

This is a candidate for manual testing, not a final release. The user confirmed the preceding stable 1019 corrections work in game. New additions and Engine output require fresh game verification. The agent did not launch ARK, install a patch, access the editor toolchain, or scan installed mods.

## Current prepared artifact

- Corrections: **1162** (1019 stable + 143 new screenshot keys).
- ShooterGame additions: **43** (41 from the preserved deferred review + 2 confirmed batch 27 EN-only keys).
- Engine edits: **21** InputKeys entries, including 20 existing RU keys and 1 EN-only insertion (`InputKeys<TAB>Insert`).
- Targeted orphan widget entries created: **0**.
- PAK: `dist/ASA_RU_Fix_P.pak`, **10,773,598 bytes**.
- SHA-256: `4f427f0ee2dbe01bae43f30689bf6f17087a10b0e441478dc289c99813bf265f`.
- V11, mount `../../../`, exactly these files:

```text
Engine/Content/Localization/Engine/ru/Engine.locres
ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres
```

The user authorized both additional batch 27 EN-only keys on 2026-10-01. They are included in additions: `GraphLiteral<TAB>1863176983` (`, WIND:` -> `, ВЕТЕР:`) and `GraphLiteral<TAB>3285020872` (`MOD ARKS` -> `КАРТЫ ИЗ МОДОВ`). The latter translation follows the user's latest revision, overriding the archived CSV's `МОДОВЫЕ КАРТЫ`. All 43 additions remain separate from corrections; no review archive was rewritten.

## Screenshot import

Applied explicit priority 28 > 27 > 26 > stable data. Count before each step:

| Batch | Input | New corrections | Revisions | Exact duplicates | EN-only keys |
|---|---:|---:|---:|---:|---:|
| 26 | 88 | 78 | 10 | 0 | 0 |
| 27 | 61 | 59 | 0 | 0 | 2 |
| 28 | 9 | 6 | 3 | 0 | 0 |

Batch 27 JSON was absent. Its 61 exact `FIX`/`proposed_ru` CSV rows were recovered without semantic changes into `work/review/review_batch_27_corrections_candidate_recovered.json`. Source review files were preserved. Per-key revisions and preflight results are in `work/review/screenshot_import_validation.json`. Ordinary generic candidate import continues to reject different existing values; these revisions were explicitly authorized for this batch sequence.

## Missing RU mechanism and validation

RU remains the base. Only requested missing keys are copied from current EN, including namespace/key FStrings and namespace/key/source hashes. Existing RU entry metadata and translations remain intact except requested corrections. Insertion follows actual EN sequence, with no arbitrary append; incompatible RU/EN order is rejected. Serialization rebuilds unique strings and refcounts. Both current stock RU resources are EN subsequences.

Fresh production build and standalone guarded build passed. After repak info/list/unpack and repeated LOCRES parse:

- **1162/1162 corrections**, **43/43 ShooterGame additions**, **21/21 Engine edits**: MATCH, zero mismatches.
- ShooterGame: 35,407 stock RU + 43 additions = **35,450 keys**.
- Engine: 45,771 stock RU + Insert = **45,772 keys**.
- Full dictionaries equal stock RU plus explicit edits; every stock identity hash remains unchanged.
- Copied EN hashes and native insertion order independently verified after PAK extraction.
- Zero placeholder mismatches and zero invalid RichText structures. The known source fragment `{color} ... </>` preserves its original contract.
- `Content<TAB>1408111756 = Назад`; `GraphLiteral<TAB>63761803 = Играть`.
- No `RU FIX TEST` in edit values or either LOCRES string table.
- **62 unit tests PASS**; standalone guard: **0 forbidden accesses**, four cached repak calls.

Reports/logs: `work/build_validation.json`, `work/review/candidate_full_verification.json`, `work/review/candidate_build.log`, `work/review/candidate_unit_tests.log`, `work/review/candidate_standalone_build.log`, `work/review/source_hash_investigation.json`.

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

## Manual test plan

1. Confirm ordinary corrections remain active, especially `Назад` and both crosshair color labels. If they disappear after enabling additions, **FAIL**: the rebuilt resource may have been rejected; retain evidence and return to the stable PAK.
2. Check Adobe Gateway / Adobe Gate, then the three other Adobe examples above.
3. Check physical key labels: Пробел, Левый/Правый Ctrl and Shift, wheel directions, Num 0 / Num / / Num *, Тильда, Insert and brackets.
4. Check the exact visible `WEIGHT` and `Crafting Requirements` instances. Expected `ВЕС` and `Для создания требуется:`. A remaining EN instance is an unresolved limitation, not a passing result.
5. Check Carcha Saddle, Tek Crop Plot and Charged: `Седло для Кархародонтозавра`, `Тек-грядка`, `Заряженный`; also Yi Ling Saddle, Hide Hat and Tek Gateway.

Record all five manual results. The remaining English widget instances are a documented v1 limitation under the user’s 2026-10-01 instructions; they are not claimed fixed. The user decides whether to release this candidate with that limitation.
