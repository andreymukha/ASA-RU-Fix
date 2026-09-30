# Standalone extraction implementation plan

**Goal:** Build ASA RU Fix using installed ASA without any required DevKit component.

**Architecture:** Replace only source extraction with a bounded, validating PAK V12 reader. Load a cached GPL-3.0-or-later ooz DLL through ctypes. Preserve the LOCRES merge and repak V11 pipeline. Optional reference tests are isolated from production imports.

**Tech stack:** Python standard library, MSVC x64 Build Tools, pinned powzix/ooz, repak 0.2.3.

- [x] Verify current TradFR format reference and ooz licensing; no TradFR code copying.
- [x] Add synthetic reader tests; observe import failure before implementing reader.
- [x] Implement checked footer/index/directory/entry/block extraction and cached ctypes backend.
- [x] Make bootstrap verify/cache repak and pinned source, compile DLL only when necessary.
- [x] Isolate explicit DevKit reference extraction; compare EN/RU bytes, hashes, sizes and counts.
- [x] Replace production extraction; preserve correction merge and repak checks.
- [x] Run complete build under filesystem/process/import guards excluding DevKit.
- [x] Run malformed-input tests, LOCRES no-op round-trip, bootstrap cache/recovery checks.
- [x] Update README and reproducible verification report; inspect/stage only source/doc changes.
- [x] Create new commit after 227b491 and confirm clean status.
