"""Small synthetic archives exercise validation without any game files."""
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from tools.pakv12 import PakError, PakReader


def string(value):
    raw = value.encode() + b'\0'
    return struct.pack('<i', len(raw)) + raw


def archive(version=12, encrypted_index=False, flags=0, method=0, missing=False,
            bad_offset=False, corrupt=False, payload=b'test resource', block_size=2048, wide=False):
    block_count = (len(payload) + block_size - 1) // block_size if method else 0
    header_size = 53 + (4 + 16 * block_count if method else 0)
    sizes = [min(block_size, len(payload) - i * block_size) for i in range(block_count)]
    blocks = struct.pack('<I', block_count) if method else b''
    offset = header_size
    for size in sizes:
        blocks += struct.pack('<QQ', offset, offset + size)
        offset += size
    header = struct.pack('<QQQI', 0, len(payload), len(payload), method) + hashlib.sha1(payload).digest()
    header += blocks + struct.pack('<BI', flags, block_size if method else 0)
    code = block_size // 2048 if method else 0
    extended = method and (block_size % 2048 != 0 or code >= 63)
    bits = (0 if wide else 7 << 29) | (method << 23) | (flags << 22) | (block_count << 6) | (63 if extended else code)
    entry = struct.pack('<I', bits)
    if extended:
        entry += struct.pack('<I', block_size)
    entry += struct.pack('<QQ' if wide else '<II', 0xfffffff0 if bad_offset else 0, len(payload))
    if method:
        entry += struct.pack('<Q' if wide else '<I', len(payload))
        if block_count > 1:
            entry += struct.pack('<' + 'I' * block_count, *sizes)
    directory = struct.pack('<i', 1) + string('folder/') + struct.pack('<i', 1) + string('other' if missing else 'file') + struct.pack('<I', 0)
    directory_offset = len(header) + len(payload)
    index = string('../../../') + struct.pack('<iQi', 1, 0, 0)
    index += struct.pack('<iQQ', 1, directory_offset, len(directory)) + hashlib.sha1(directory).digest()
    index += struct.pack('<i', len(entry)) + entry + struct.pack('<i', 0)
    index_offset = directory_offset + len(directory)
    names = b'Oodle'.ljust(32, b'\0') + bytes(128)
    footer = bytes(16) + bytes([encrypted_index]) + struct.pack('<IIQQ', 0x5a6f12e1, version, index_offset, len(index))
    footer += hashlib.sha1(index).digest() + names
    result = header + payload + directory + index + footer
    if corrupt:
        result = result[:index_offset] + b'X' + result[index_offset + 1:]
    return result


class PakTests(unittest.TestCase):
    def extract(self, data, decompressor=None):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.pak'
            path.write_bytes(data)
            return PakReader(path, decompressor=decompressor).extract('../../../folder/file')

    def test_plain(self):
        self.assertEqual(self.extract(archive()), b'test resource')

    def test_oodle_block(self):
        self.assertEqual(self.extract(archive(method=1), lambda data, size: data), b'test resource')

    def test_multiple_blocks(self):
        data = bytes(range(256)) * 20
        self.assertEqual(self.extract(archive(method=1, payload=data), lambda data, size: data), data)

    def test_wide_entry_and_explicit_block_size(self):
        data = b'x' * 4000
        self.assertEqual(self.extract(archive(method=1, payload=data, block_size=1000, wide=True), lambda data, size: data), data)

    def test_local_header_and_payload_corruption(self):
        data = bytearray(archive())
        for offset in (8, 48, 53):
            broken = data.copy()
            broken[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(PakError):
                self.extract(bytes(broken))

    def test_wrong_decompressed_size(self):
        with self.assertRaises(PakError):
            self.extract(archive(method=1), lambda data, size: b'')

    def test_rejections(self):
        for options in ({'version': 11}, {'encrypted_index': True}, {'flags': 1},
                        {'method': 2}, {'missing': True}, {'bad_offset': True}, {'corrupt': True}):
            with self.subTest(options=options), self.assertRaises(PakError):
                self.extract(archive(**options))

    def test_truncated(self):
        for data in (b'', archive()[:-40], archive()[:60]):
            with self.subTest(size=len(data)), self.assertRaises(PakError):
                self.extract(data)


if __name__ == '__main__':
    unittest.main()
