# Third-party provenance

## powzix/ooz

- Repository: https://github.com/powzix/ooz
- Pinned commit: `05038060aa68f9187ae9923b2388ca8db40e58d1` (README identifies upstream CLI v7.0).
- License evidence: opening notice of [kraken.cpp at the pinned commit](https://github.com/powzix/ooz/blob/05038060aa68f9187ae9923b2388ca8db40e58d1/kraken.cpp) expressly states GNU GPL version 3 or, at the recipient's option, any later version: **GPL-3.0-or-later**. Checked in actual source; there is no separate upstream LICENSE file.
- Bootstrap downloads only `kraken.cpp`, `lzna.cpp`, `bitknit.cpp`, `stdafx.h`, `targetver.h` from immutable commit URLs. Each raw file SHA-256 is pinned in `tools/bootstrap.py`. Original source and its license notice are retained in `work/tools/ooz/source/`.
- Full [official GPLv3 text](https://www.gnu.org/licenses/gpl-3.0.txt) is saved in `work/tools/ooz/GPL-3.0.txt`, pinned SHA-256 `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`.
- Generated `kraken_decoder.cpp` retains the upstream license/decoder and removes all CLI code at its documented boundary, including proprietary DLL loading. Our `tools/ooz_bridge.cpp` is **GPL-3.0-or-later** and exports one C ABI function. No proprietary DLL/source is used.
- Build: independent MSVC x64 and Windows SDK, `/LD /O2 /MT /EHsc /std:c++17`. Static C runtime avoids a separate Visual C++ redistributable. `vswhere` finds Visual Studio Build Tools. Recipe, compiler setup and DLL SHA-256 are recorded in `work/tools/ooz/build.json`.
- ctypes loads the DLL once and calls it for successive blocks. Buffers include 64 spare bytes, required by upstream vector writes; return length must match expected output.
- Upstream is not fuzz safe. Outer ranges/headers and index/compressed-payload SHA-1 are checked before decoding trusted installed game content. This does not establish safety for adversarial compressed streams.
- No upstream source or compiled DLL is committed/distributed here. Keep GPL notices, license and matching source with any separately distributed ooz derivative.

## trumank/repak

- Version **0.2.3**, **MIT OR Apache-2.0**; both license files come from its official release ZIP.
- Asset: https://github.com/trumank/repak/releases/download/v0.2.3/repak_cli-x86_64-pc-windows-msvc.zip
- ZIP SHA-256: `6720d602144d75df477a99d5bedb6ea780997546afc335901d4937cafeaa73fa`.
- Writes/reopens our V11 patch, not the source V12 PAK. ZIP, executable and licenses stay in ignored `work/tools/`.

## Technical references only

- TradFR: https://github.com/valentin-gosselin/ark-ascended-fr
- Inspected commit `8527fc5f89246fec9f67fefcb849c82db1533f7c`.
- Studied `tools/pakv12.py`, `tools/locres.py`, `tools/construire_ooz.sh`, `build.py`: serialized layout, block offsets and workflow. Root tracked tree has no LICENSE/COPYING or explicit reuse grant. No code was copied into our reader/bootstrap.
- Earlier reference: https://github.com/LeXa4894/ASA_fix_ru_loc; no source/binary copied.

Reference clones are ignored `work/reference/` artifacts. DevKit UnrealPak is only an explicit optional oracle executable in `tests/compare_devkit.py`, neither downloaded nor used by production.
