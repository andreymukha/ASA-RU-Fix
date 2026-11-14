"""Reproduce the empty IoStore companions verified with the ASA translation PAK.

The embedded bytes come from retoc 0.1.5. To reproduce, create an empty input
directory and run the following with output basename exactly ASA_RU_Fix_P:

    retoc --override-toc-version ReplaceIoChunkHashWithIoHash \
      --override-container-header-version SoftPackageReferencesOffset \
      to-zen --version UE5_5 EMPTY_DIRECTORY ASA_RU_Fix_P.utoc

Keep the generated UTOC and UCAS only; retoc's empty PAK is not the patch.
Both companions contain only one ContainerHeader chunk and no game packages.
The production build needs neither retoc nor installed game assets for them.
"""
from __future__ import annotations

import hashlib
import struct
import tempfile
from pathlib import Path

UTOC = bytes.fromhex('''
    2d3d3d2d2d3d3d2d2d3d3d2d2d3d3d2d
    08000000900000000100000001000000
    0c000000000000002000000000000100
    0000000001000000a215a557d7f8da3a
    00000000000000000000000000000000
    0800000000000000ffffffffffffffff
    00000000000000000000000000000000
    00000000000000000000000000000000
    00000000000000000000000000000000
    a215a557d7f8da3a0000000600000000
    00000000004000000000004000004000
    00005bc477c64d01a762a1b0c3c9c06c
    6129b978937900000000
''')
UCAS = bytes.fromhex('''
    6e436f4905000000a215a557d7f8da3a
    00000000000000000000000000000000
    0000000000000000000000003c000000
    00000000040000000000000000000000
''')
CONTAINER_ID = 0x3ADAF8D757A515A2
EXPECTED = {
    '.utoc': (202, '4cf47c360360ed970df26b1db1c83072f3035a33f4b98e6cbb6d3d09d195c353'),
    '.ucas': (64, '81cf60aca4403cb235e1f34e43c2cb7b4a0d8f3540d2c27b43d30f7286c43425'),
}


def _verified(suffix: str, data: bytes) -> dict[str, int | str]:
    size, digest = len(data), hashlib.sha256(data).hexdigest()
    if (size, digest) != EXPECTED[suffix]:
        raise RuntimeError(f'Invalid {suffix[1:].upper()} companion size or SHA-256: {size} / {digest}')
    return {'size': size, 'sha256': digest}


def _verify_structure(utoc: bytes, ucas: bytes) -> None:
    if (utoc[:16] != b'-==-' * 4 or utoc[16] != 8
            or struct.unpack_from('<III', utoc, 20) != (144, 1, 1)
            or struct.unpack_from('<Q', utoc, 56)[0] != CONTAINER_ID
            or struct.unpack_from('<Q3xB', utoc, 144) != (CONTAINER_ID, 6)):
        raise RuntimeError('Invalid UTOC companion: expected one ContainerHeader chunk')
    if (ucas[:4] != b'nCoI'
            or struct.unpack_from('<IQI', ucas, 4) != (5, CONTAINER_ID, 0)):
        raise RuntimeError('Invalid UCAS companion: expected a ContainerHeader with no packages')


def write_companions(pak_path: Path) -> dict[str, dict[str, int | str]]:
    """Write and verify the two mount files alongside an existing patch PAK."""
    if pak_path.suffix.lower() != '.pak':
        raise ValueError('PAK output path must have a .pak extension')
    payloads = {'.ucas': UCAS, '.utoc': UTOC}
    for suffix, data in payloads.items():
        _verified(suffix, data)
    _verify_structure(UTOC, UCAS)
    with tempfile.TemporaryDirectory(prefix='.iostore-', dir=pak_path.parent) as folder:
        for suffix, data in payloads.items():
            (Path(folder) / suffix).write_bytes(data)
        result = {}
        for suffix in payloads:
            final = pak_path.with_suffix(suffix)
            (Path(folder) / suffix).replace(final)
            result[final.name] = _verified(suffix, final.read_bytes())
    return result
