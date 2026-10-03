"""Canonical physical order for the two uncompressed repak v0.2.3 V11 LOCRES.

The compact records and lookup indexes stay in lexical filename order. Only
physical blocks, compact data offsets, and the main index SHA-1 can change.
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
from pathlib import Path

from tools.pakv12 import Cursor

ENGINE = "Engine/Content/Localization/Engine/ru/Engine.locres"
SHOOTER = "ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres"
FILES = (ENGINE, SHOOTER)
FOOTER_SIZE = 221
HEADER_SIZE = 53
MAX_SIZE = 128 * 1024 * 1024


def _string(value: str) -> bytes:
    raw = value.encode("ascii") + b"\0"
    return struct.pack("<I", len(raw)) + raw


def _path_hash(path: str) -> int:
    value = 0xcbf29ce484222325
    for byte in path.lower().encode("utf-16-le"):
        value = ((value ^ byte) * 0x100000001b3) & ((1 << 64) - 1)
    return value


def _lookup_indexes() -> tuple[bytes, bytes]:
    """Expected repak lookup bytes for lexical compact slots 0 and 12."""
    phi = struct.pack("<I", len(FILES))
    directories: dict[str, dict[str, int]] = {"/": {}}
    for slot, path in enumerate(FILES):
        location = slot * 12
        phi += struct.pack("<QI", _path_hash(path), location)
        parts = path.split("/")
        for end in range(1, len(parts)):
            directories.setdefault("/".join(parts[:end]) + "/", {})
        directories["/".join(parts[:-1]) + "/"][parts[-1]] = location
    phi += struct.pack("<I", 0)
    fdi = struct.pack("<I", len(directories))
    for directory, files in sorted(directories.items()):
        fdi += _string(directory) + struct.pack("<I", len(files))
        for filename, location in sorted(files.items()):
            fdi += _string(filename) + struct.pack("<I", location)
    return phi, fdi


def _parse(data: bytes) -> tuple[int, int, int, dict[str, bytes], dict[str, int]]:
    if not FOOTER_SIZE < len(data) <= MAX_SIZE:
        raise RuntimeError("PAK size is outside the supported two-LOCRES range")
    footer_start = len(data) - FOOTER_SIZE
    footer = Cursor(data[footer_start:])
    if footer.take(17) != bytes(17):
        raise RuntimeError("Encrypted PAK index or nonzero encryption GUID is unsupported")
    if footer.number("I") != 0x5a6f12e1 or footer.number("I") != 11:
        raise RuntimeError("Canonical PAK ordering requires a standard V11 footer")
    index_offset, index_size = footer.number("Q"), footer.number("Q")
    digest = footer.take(20)
    if footer.take(160) != bytes(160):
        raise RuntimeError("Compression methods are unsupported; expected None")
    footer.finish()

    def hashed(offset: int, size: int, expected: bytes) -> bytes:
        if offset < index_offset or size <= 0 or size > 65536 or offset + size > footer_start:
            raise RuntimeError("Invalid PAK index range")
        raw = data[offset:offset + size]
        if hashlib.sha1(raw).digest() != expected:
            raise RuntimeError("PAK index SHA-1 mismatch")
        return raw

    main = Cursor(hashed(index_offset, index_size, digest))
    if main.string() != "../../../" or main.number("I") != 2 or main.number("Q") != 0:
        raise RuntimeError("Unsupported PAK mount, entry count, or path hash seed")
    indexes = []
    locations = []
    for _ in range(2):
        if main.number("I") != 1:
            raise RuntimeError("Both path hash and full directory indexes are required")
        offset, size = main.number("Q"), main.number("Q")
        indexes.append(hashed(offset, size, main.take(20)))
        locations.append((offset, size))
    if locations[0][0] != index_offset + index_size or (
        locations[1][0] != sum(locations[0]) or sum(locations[1]) != footer_start
    ):
        raise RuntimeError("PAK indexes must be adjacent with no gaps or overlaps")
    if tuple(indexes) != _lookup_indexes():
        raise RuntimeError("PAK lookup indexes do not describe exactly the supported two LOCRES")
    if main.number("I") != 24:
        raise RuntimeError("Expected exactly two 12-byte compact entries")
    encoded_start = main.position
    blocks = {}
    offsets = {}
    for name in FILES:
        if main.number("I") != 0xe0000000:
            raise RuntimeError("Unsupported compact entry compression, encryption, blocks, or width")
        offset, size = main.number("I"), main.number("I")
        if not 0 < size <= MAX_SIZE // 2 or offset + HEADER_SIZE + size > index_offset:
            raise RuntimeError("Invalid compact PAK payload range")
        header = Cursor(data[offset:offset + HEADER_SIZE])
        if (header.number("Q"), header.number("Q"), header.number("Q"), header.number("I")) != (0, size, size, 0):
            raise RuntimeError("Local PAK header disagrees with compact entry")
        payload_digest = header.take(20)
        if header.number("B") != 0 or header.number("I") != 0:
            raise RuntimeError("Local PAK encryption/deletion or compression blocks are unsupported")
        header.finish()
        payload = data[offset + HEADER_SIZE:offset + HEADER_SIZE + size]
        if hashlib.sha1(payload).digest() != payload_digest:
            raise RuntimeError("PAK payload SHA-1 mismatch")
        blocks[name] = data[offset:offset + HEADER_SIZE + size]
        offsets[name] = offset
    if main.number("I") != 0:
        raise RuntimeError("Noncompact PAK entries are unsupported")
    main.finish()
    expected_offset = 0
    for name in sorted(FILES, key=offsets.__getitem__):
        if offsets[name] != expected_offset:
            raise RuntimeError("PAK data blocks have gaps, overlaps, or duplicate offsets")
        expected_offset += len(blocks[name])
    if expected_offset != index_offset:
        raise RuntimeError("PAK data boundary disagrees with index offset")
    return index_offset, index_size, encoded_start, blocks, offsets


def canonicalize_pak(path: Path, order: list[str]) -> None:
    """Atomically reorder a generated PAK after checking the complete narrow layout.

    ``order`` must contain the two relative filenames shown by ``repak list``.
    Any unsupported/corrupt input fails without changing the source file.
    """
    if len(order) != 2 or set(order) != set(FILES):
        raise RuntimeError("Canonical PAK order must name each supported LOCRES exactly once")
    path = Path(path)
    temporary: Path | None = None
    try:
        if path.stat().st_size > MAX_SIZE:
            raise RuntimeError("PAK exceeds the supported size limit")
        original = path.read_bytes()
        index_offset, index_size, encoded_start, blocks, offsets = _parse(original)
        if sorted(FILES, key=offsets.__getitem__) == order:
            return
        result = bytearray(b"".join(blocks[name] for name in order) + original[index_offset:])
        new_offset = 0
        for name in order:
            slot = FILES.index(name)
            struct.pack_into("<I", result, index_offset + encoded_start + slot * 12 + 4, new_offset)
            new_offset += len(blocks[name])
        footer_start = len(result) - FOOTER_SIZE
        result[footer_start + 41:footer_start + 61] = hashlib.sha1(
            result[index_offset:index_offset + index_size]
        ).digest()
        _, _, _, checked_blocks, checked_offsets = _parse(bytes(result))
        if checked_blocks != blocks or sorted(FILES, key=checked_offsets.__getitem__) != order:
            raise RuntimeError("Canonical PAK validation changed payloads or failed requested order")
        descriptor, filename = tempfile.mkstemp(prefix=path.name + ".canonical-", suffix=".tmp", dir=path.parent)
        temporary = Path(filename)
        with os.fdopen(descriptor, "wb") as output:
            output.write(result)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise RuntimeError(f"Cannot canonicalize PAK: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
