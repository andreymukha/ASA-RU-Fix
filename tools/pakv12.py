"""Read the unencrypted V12 PAK layout used by ASA, with checked ranges.

This deliberately supports compact entries and None/Oodle compression only.
Metadata and individual extracted resources are capped at 64 MiB. No game
content is read until its index entry and local header have been validated.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

LIMIT = 64 * 1024 * 1024
MAGIC = struct.pack('<I', 0x5A6F12E1)


class PakError(RuntimeError):
    pass


class Cursor:
    def __init__(self, data: bytes, position: int = 0):
        self.data, self.position = data, position

    def take(self, size: int) -> bytes:
        if size < 0 or self.position < 0 or size > len(self.data) - self.position:
            raise PakError('Truncated or invalid PAK metadata range')
        start = self.position
        self.position += size
        return self.data[start:self.position]

    def number(self, format: str) -> int:
        return struct.unpack('<' + format, self.take(struct.calcsize('<' + format)))[0]

    def count(self, minimum_size: int = 1) -> int:
        value = self.number('i')
        if value < 0 or value > (len(self.data) - self.position) // minimum_size:
            raise PakError(f'Invalid PAK metadata count: {value}')
        return value

    def flag(self) -> bool:
        value = self.number('i')
        if value not in (0, 1):
            raise PakError('Invalid index presence flag')
        return bool(value)

    def string(self) -> str:
        length = self.number('i')
        if length == 0:
            return ''
        width = 2 if length < 0 else 1
        raw = self.take(abs(length) * width)
        if raw[-width:] != bytes(width):
            raise PakError('PAK FString has no terminator')
        try:
            text = raw[:-width].decode('utf-16-le' if length < 0 else 'utf-8')
        except UnicodeError as exc:
            raise PakError('Invalid PAK FString encoding') from exc
        if '\0' in text:
            raise PakError('Embedded NUL in PAK FString')
        return text

    def finish(self):
        if self.position != len(self.data):
            raise PakError('Unexpected trailing PAK metadata')


@dataclass(frozen=True)
class Entry:
    offset: int
    size: int
    stored_size: int
    method: int
    block_size: int
    blocks: tuple[int, ...]


class PakReader:
    def __init__(self, path: Path, decompressor: Callable[[bytes, int], bytes] | None = None):
        self.path = Path(path)
        self.file_size = self.path.stat().st_size
        self.decompressor = decompressor
        self._footer()
        self._index()

    def _read(self, offset: int, size: int, boundary: int | None = None) -> bytes:
        end = self.file_size if boundary is None else boundary
        if offset < 0 or size < 0 or size > LIMIT or offset > end or size > end - offset:
            raise PakError(f'Invalid PAK range: offset={offset}, size={size}, boundary={end}')
        with self.path.open('rb') as file:
            file.seek(offset)
            data = file.read(size)
        if len(data) != size:
            raise PakError('PAK changed or was truncated while reading')
        return data

    def _hashed(self, offset: int, size: int, digest: bytes) -> bytes:
        data = self._read(offset, size, self.footer_start)
        if hashlib.sha1(data).digest() != digest:
            raise PakError('PAK index SHA-1 mismatch')
        return data

    def _footer(self):
        tail_size = min(4096, self.file_size)
        tail = self._read(self.file_size - tail_size, tail_size)
        location = tail.rfind(MAGIC)
        if location < 17:
            raise PakError('PAK footer magic/GUID/encryption flag not found')
        cursor = Cursor(tail, location + 4)
        version = cursor.number('I')
        if version != 12:
            raise PakError(f'Unsupported PAK version {version}; expected V12')
        if tail[location - 1] != 0:
            raise PakError('Encrypted PAK index is unsupported')
        self.footer_start = self.file_size - tail_size + location - 17
        self.index_offset, self.index_size = cursor.number('Q'), cursor.number('Q')
        self.index_digest = cursor.take(20)
        self.methods = []
        for _ in range(5):
            raw = cursor.take(32)
            try:
                name = raw.split(b'\0', 1)[0].decode('ascii')
            except UnicodeError as exc:
                raise PakError('Invalid compression method name') from exc
            self.methods.append(name)
        # ASA appends two custom uint32 fields to the standard footer. Neither
        # participates in extraction. Reject unrelated tail layouts.
        if len(tail) - cursor.position not in (0, 8):
            raise PakError('Unsupported V12 footer extension length')

    def _index(self):
        cursor = Cursor(self._hashed(self.index_offset, self.index_size, self.index_digest))
        self.mount = cursor.string()
        self.payload_boundary = self.index_offset
        count = cursor.count()
        cursor.number('Q')  # path hash seed; exact lookup uses full directory
        if cursor.flag():
            offset, size, digest = cursor.number('Q'), cursor.number('Q'), cursor.take(20)
            self._hashed(offset, size, digest)
            self.payload_boundary = min(self.payload_boundary, offset)
        if not cursor.flag():
            raise PakError('Full directory index is required')
        offset, size, digest = cursor.number('Q'), cursor.number('Q'), cursor.take(20)
        directory = Cursor(self._hashed(offset, size, digest))
        self.payload_boundary = min(self.payload_boundary, offset)
        self.encoded = cursor.take(cursor.count())
        if cursor.number('i') != 0:
            raise PakError('Unencoded PAK entries are unsupported')
        cursor.finish()
        self.files = {}
        for _ in range(directory.count(8)):
            folder = directory.string()
            for _ in range(directory.count(8)):
                filename = directory.string()
                location = directory.number('I')
                name = self.mount + folder + filename
                if name in self.files:
                    raise PakError(f'Duplicate full directory filename: {name}')
                self.files[name] = location
        directory.finish()
        if len(self.files) != count:
            raise PakError('PAK index entry count disagrees with full directory')

    def _entry(self, name: str) -> Entry:
        if name not in self.files:
            raise PakError(f'Exact PAK filename is absent: {name}')
        cursor = Cursor(self.encoded, self.files[name])
        bits = cursor.number('I')
        method = (bits >> 23) & 63
        if bits & (1 << 22):
            raise PakError('Encrypted PAK payload is unsupported')
        if method and (method > len(self.methods) or self.methods[method - 1] != 'Oodle'):
            raise PakError(f'Unsupported compression method index {method}')
        blocks = (bits >> 6) & 65535
        code = bits & 63
        block_size = cursor.number('I') if code == 63 else code * 2048
        offset = cursor.number('I' if bits & (1 << 31) else 'Q')
        size = cursor.number('I' if bits & (1 << 30) else 'Q')
        stored = cursor.number('I' if bits & (1 << 29) else 'Q') if method else size
        if not size or size > LIMIT or not stored or stored > LIMIT:
            raise PakError('Resource size outside supported range (1..64 MiB)')
        if method:
            if not block_size or blocks != (size + block_size - 1) // block_size:
                raise PakError('Compression block count/size disagree with resource size')
            sizes = (stored,) if blocks == 1 else tuple(cursor.number('I') for _ in range(blocks))
            if not all(sizes) or sum(sizes) != stored:
                raise PakError('Compact compression block sizes disagree with stored size')
        else:
            if blocks:
                raise PakError('Uncompressed resource has compression blocks')
            sizes = ()
        return Entry(offset, size, stored, method, block_size, sizes)

    def extract(self, name: str) -> bytes:
        entry = self._entry(name)
        header_size = 53 + (4 + 16 * len(entry.blocks) if entry.method else 0)
        cursor = Cursor(self._read(entry.offset, header_size, self.payload_boundary))
        local_offset = cursor.number('Q')
        stored, size, method = cursor.number('Q'), cursor.number('Q'), cursor.number('I')
        digest = cursor.take(20)
        if local_offset not in (0, entry.offset) or (stored, size, method) != (entry.stored_size, entry.size, entry.method):
            raise PakError('Local PAK header disagrees with compact entry')
        ranges = []
        if entry.method:
            if cursor.number('I') != len(entry.blocks):
                raise PakError('Local compression block count disagrees with compact entry')
            expected = header_size
            for compressed_size in entry.blocks:
                start, end = cursor.number('Q'), cursor.number('Q')
                if start != expected or end - start != compressed_size:
                    raise PakError('Malformed local compression block offsets/sizes')
                ranges.append((start, end))
                expected = end
        if cursor.number('B') != 0:
            raise PakError('Encrypted/deleted local PAK payload is unsupported')
        local_block_size = cursor.number('I')
        if entry.method and local_block_size != entry.block_size:
            raise PakError('Local compression block size disagrees with compact entry')
        cursor.finish()
        payload = self._read(entry.offset + header_size, entry.stored_size, self.payload_boundary)
        if hashlib.sha1(payload).digest() != digest:
            raise PakError('PAK payload SHA-1 mismatch')
        if not entry.method:
            return payload
        if self.decompressor is None:
            from tools.oodle import OozBackend
            self.decompressor = OozBackend().decompress
        output = bytearray()
        for start, end in ranges:
            expected_size = min(entry.block_size, entry.size - len(output))
            block = self.decompressor(payload[start - header_size:end - header_size], expected_size)
            if len(block) != expected_size:
                raise PakError('Oodle returned incorrect block size')
            output.extend(block)
        if len(output) != entry.size:
            raise PakError('Decompressed resource size mismatch')
        return bytes(output)
