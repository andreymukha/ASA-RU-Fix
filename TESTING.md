# Build verification and in-game check

## Temporary test correction

- Key: `GraphLiteral<TAB>63761803`
- English source: `Play`
- Current official Russian text: `Играть`
- Temporary text: `Играть [RU FIX TEST]`
- Expected location: the early menu's Play action/button. The key and source were found in the current game LOCRES; the exact widget placement still needs visual confirmation in-game.
- Remove the one entry from `data/corrections.json` after the check, then rebuild to produce a clean patch.

## Automated checks performed

1. Found Epic manifest `C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests\9BE99B4594B4E05E7E64A99FC03BE16F.item`, DisplayName `ARK DevKit`, InstallLocation `D:\ARKDevkit`.
2. Found `D:\ARKDevkit\Engine\Binaries\Win64\UnrealPak.exe` (146,432 bytes). Help reports `-List` and `-Extract`; it read the current v12 PAK and decompressed Oodle-compressed entries. No `oo2core*_win64.dll` was found in the searched DevKit Oodle/Binaries/Plugins locations.
3. UnrealPak v5.5 listed the current installed `pakchunk0-Windows.pak`, footer version 12, and found exactly one EN and RU LOCRES entry. It extracted only those two files successfully.
4. Extracted LOCRES v3 sizes: EN 3,651,674 bytes / 39,201 keys; RU 4,975,204 bytes / 35,407 keys. The PAK index reported compressed sizes of 1,500,693 and 1,515,731 bytes respectively.
5. Built RU LOCRES with zero corrections and reparsed it. Source and rebuilt SHA-256 both equal `82631F8928A818CEBF922B4E4EE834F3E22DEB44AB4E26E645CB7CB0BF4BCB78` (byte-identical round-trip).
6. Applied the test correction. Rebuilt LOCRES reparsed as v3 with 35,407 keys and contains the expected test value.
7. Downloaded repak v0.2.3 to ignored `work/tools/`. The official release ZIP SHA-256 matched `6720d602144d75df477a99d5bedb6ea780997546afc335901d4937cafeaa73fa`. `repak --version` returned `repak_cli 0.2.3`; CLI help was checked. It cannot read source PAK v12, but reads its own v11 output.
8. repak created `dist/ASA_RU_Fix_P.pak` as PAK V11 with exact mount point `../../../` and entry `ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres`.
9. Reopened the built PAK with `repak list/info/unpack`, reparsed all 35,407 keys, confirmed the correction value, and confirmed extracted bytes equal the rebuilt input.
10. Python syntax, Steam and DevKit discovery, delta fixture, and PowerShell script parsing were checked. `install.ps1 -WhatIf` and `uninstall.ps1 -WhatIf` displayed their intended targets without copying or deleting anything.

## Tomorrow: manual game check

1. Inspect the patch and the temporary marker, then run `./install.ps1`.
2. Launch ARK manually and confirm the marked `Play` action appears in the expected early menu. This visual placement has not been verified yet.
3. Exit the game; remove the temporary correction from `data/corrections.json` and rebuild if you want a clean patch.
4. Remove the installed patch with `./uninstall.ps1` when desired.

ARK was not launched, and no installed game files were changed. The PAK was created only under this project and has not been installed.
