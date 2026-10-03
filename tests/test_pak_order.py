"""Small independent repak V11 fixtures, with no external tools/game content."""

import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.pak_order import canonicalize_pak

ENGINE = "Engine/Content/Localization/Engine/ru/Engine.locres"
SHOOTER = "ShooterGame/Content/Localization/ShooterGame/ru/ShooterGame.locres"
PAYLOADS = {ENGINE: b"engine translation", SHOOTER: b"shooter translation payload"}
ORDER = [SHOOTER, ENGINE]


def string(text):
    raw = text.encode("ascii") + b"\0"
    return struct.pack("<I", len(raw)) + raw


def fixture(order):
    data = bytearray()
    offsets = {}
    for name in order:
        payload = PAYLOADS[name]
        offsets[name] = len(data)
        data.extend(struct.pack("<QQQI20sBI", 0, len(payload), len(payload), 0,
                                hashlib.sha1(payload).digest(), 0, 0))
        data.extend(payload)
    encoded = b"".join(struct.pack("<III", 0xe0000000, offsets[name], len(PAYLOADS[name]))
                       for name in sorted(PAYLOADS))
    hashes = []
    for name in sorted(PAYLOADS):
        value = 0xcbf29ce484222325
        for byte in name.lower().encode("utf-16-le"):
            value = ((value ^ byte) * 0x100000001b3) & ((1 << 64) - 1)
        hashes.append(value)
    phi = struct.pack("<IQIQII", 2, hashes[0], 0, hashes[1], 12, 0)
    dirs = {"/": {}}
    for i, name in enumerate(sorted(PAYLOADS)):
        parts = name.split("/")
        for end in range(1, len(parts)):
            dirs.setdefault("/".join(parts[:end]) + "/", {})
        dirs["/".join(parts[:-1]) + "/"][parts[-1]] = i * 12
    fdi = struct.pack("<I", len(dirs))
    for directory, files in sorted(dirs.items()):
        fdi += string(directory) + struct.pack("<I", len(files))
        for name, position in sorted(files.items()):
            fdi += string(name) + struct.pack("<I", position)
    index_offset = len(data)
    index_size = 138
    phi_offset = index_offset + index_size
    fdi_offset = phi_offset + len(phi)
    index = string("../../../") + struct.pack("<IQIQQ", 2, 0, 1, phi_offset, len(phi))
    index += hashlib.sha1(phi).digest()
    index += struct.pack("<IQQ", 1, fdi_offset, len(fdi)) + hashlib.sha1(fdi).digest()
    index += struct.pack("<I", len(encoded)) + encoded + struct.pack("<I", 0)
    footer = bytes(17) + struct.pack("<IIQQ", 0x5a6f12e1, 11, index_offset, len(index))
    footer += hashlib.sha1(index).digest() + bytes(160)
    return bytes(data) + index + phi + fdi + footer


def rehash_main(data):
    footer = len(data) - 221
    offset, size = struct.unpack_from("<QQ", data, footer + 25)
    data[footer + 41:footer + 61] = hashlib.sha1(data[offset:offset + size]).digest()


class PakOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "generated.pak"

    def test_both_physical_orders_produce_identical_canonical_bytes(self):
        expected = fixture(ORDER)
        for physical_order in (ORDER, list(reversed(ORDER))):
            with self.subTest(order=physical_order):
                self.path.write_bytes(fixture(physical_order))
                self.assertIsNone(canonicalize_pak(self.path, ORDER))
                self.assertEqual(self.path.read_bytes(), expected)

    def test_reversed_requested_order_and_idempotence(self):
        expected = fixture(list(reversed(ORDER)))
        self.path.write_bytes(fixture(ORDER))
        canonicalize_pak(self.path, list(reversed(ORDER)))
        self.assertEqual(self.path.read_bytes(), expected)
        canonicalize_pak(self.path, list(reversed(ORDER)))
        self.assertEqual(self.path.read_bytes(), expected)

    def test_incomplete_duplicate_extra_and_wrong_order_paths_fail_unchanged(self):
        original = fixture(ORDER)
        for order in ([SHOOTER], [SHOOTER, SHOOTER], ORDER + ["extra.locres"],
                      ["../../../" + SHOOTER, ENGINE], [SHOOTER, "unexpected.locres"]):
            with self.subTest(order=order):
                self.path.write_bytes(original)
                with self.assertRaises(RuntimeError):
                    canonicalize_pak(self.path, order)
                self.assertEqual(self.path.read_bytes(), original)

    def test_unsupported_footer_fields_fail_unchanged(self):
        raw = fixture(ORDER)
        footer = len(raw) - 221
        for position in (footer, footer + 16, footer + 17, footer + 21, footer + 61):
            with self.subTest(position=position):
                data = bytearray(raw)
                data[position] ^= 1
                self.path.write_bytes(data)
                with self.assertRaises(RuntimeError):
                    canonicalize_pak(self.path, ORDER)
                self.assertEqual(self.path.read_bytes(), data)

    def test_corrupt_main_secondary_indexes_and_payload_fail_unchanged(self):
        raw = fixture(ORDER)
        index_offset = len(raw) - 221 - 434 - 32 - 138
        for position in (53, index_offset, index_offset + 138, index_offset + 138 + 32):
            with self.subTest(position=position):
                data = bytearray(raw)
                data[position] ^= 1
                self.path.write_bytes(data)
                with self.assertRaisesRegex(RuntimeError, "SHA-1"):
                    canonicalize_pak(self.path, ORDER)
                self.assertEqual(self.path.read_bytes(), data)

    def test_local_header_fields_are_checked_independently(self):
        raw = fixture(ORDER)
        for position in (0, 8, 16, 24, 48, 49):
            with self.subTest(position=position):
                data = bytearray(raw)
                data[position] ^= 1
                self.path.write_bytes(data)
                with self.assertRaises(RuntimeError):
                    canonicalize_pak(self.path, ORDER)
                self.assertEqual(self.path.read_bytes(), data)

    def test_valid_hash_cannot_hide_bad_compact_offsets_sizes_or_flags(self):
        raw = fixture(ORDER)
        index_offset = len(raw) - 221 - 434 - 32 - 138
        for position in (index_offset + 110, index_offset + 114, index_offset + 118,
                         index_offset + 122, index_offset + 126):
            with self.subTest(position=position):
                data = bytearray(raw)
                data[position] ^= 1
                rehash_main(data)
                self.path.write_bytes(data)
                with self.assertRaises(RuntimeError):
                    canonicalize_pak(self.path, ORDER)
                self.assertEqual(self.path.read_bytes(), data)

    def test_valid_hash_cannot_hide_extra_entries_missing_indexes_or_seed_changes(self):
        raw = fixture(ORDER)
        index_offset = len(raw) - 221 - 434 - 32 - 138
        # Count, seed, index presence, encoded size, noncompact entry count.
        for relative in (14, 18, 26, 66, 106, 134):
            with self.subTest(relative=relative):
                data = bytearray(raw)
                data[index_offset + relative] ^= 1
                rehash_main(data)
                self.path.write_bytes(data)
                with self.assertRaises(RuntimeError):
                    canonicalize_pak(self.path, ORDER)
                self.assertEqual(self.path.read_bytes(), data)

    def test_rehashed_lookup_corruption_is_rejected_by_exact_expected_structure(self):
        raw = fixture(ORDER)
        index_offset = len(raw) - 221 - 434 - 32 - 138
        for pointer, digest_relative in ((index_offset + 138, 46),
                                         (index_offset + 138 + 32, 86)):
            with self.subTest(pointer=pointer):
                data = bytearray(raw)
                data[pointer] ^= 1
                size = 32 if digest_relative == 46 else 434
                data[index_offset + digest_relative:index_offset + digest_relative + 20] = hashlib.sha1(data[pointer:pointer + size]).digest()
                rehash_main(data)
                self.path.write_bytes(data)
                with self.assertRaisesRegex(RuntimeError, "lookup indexes"):
                    canonicalize_pak(self.path, ORDER)
                self.assertEqual(self.path.read_bytes(), data)

    def test_truncated_trailing_or_empty_data_are_rejected(self):
        raw = fixture(ORDER)
        for data in (b"", raw[:53], raw[:-1], raw + b"tail"):
            with self.subTest(size=len(data)):
                self.path.write_bytes(data)
                with self.assertRaises(RuntimeError):
                    canonicalize_pak(self.path, ORDER)

    def test_failure_to_replace_preserves_original_and_removes_temporary_file(self):
        original = fixture(list(reversed(ORDER)))
        self.path.write_bytes(original)
        with patch("tools.pak_order.os.replace", side_effect=OSError("cannot replace")):
            with self.assertRaisesRegex(RuntimeError, "cannot replace"):
                canonicalize_pak(self.path, ORDER)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
