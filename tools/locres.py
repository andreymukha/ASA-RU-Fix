"""Minimal reader/writer for Unreal LOCRES versions 2 and 3."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, replace
from pathlib import Path

MAGIC = bytes.fromhex("0e147475674a03fc4a15909dc3377f1b")
HEADER = struct.Struct("<16sBQI")


class LocresError(ValueError):
    pass


@dataclass
class FString:
    value: str
    utf16: bool


@dataclass
class Entry:
    namespace_hash: int
    namespace: FString
    key_hash: int
    key: FString
    source_hash: int
    value_index: int


@dataclass
class Resource:
    version: int
    entries: list[Entry]
    strings: list[FString]
    ref_counts: list[int]

    def as_dict(self) -> dict[str, str]:
        return {f"{e.namespace.value}\t{e.key.value}": self.strings[e.value_index].value for e in self.entries}


def read_fstring(data: bytes, offset: int) -> tuple[FString, int]:
    if offset + 4 > len(data):
        raise LocresError(f"truncated FString length at 0x{offset:X}")
    length = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    if length == 0:
        return FString("", False), offset
    if length > 0:
        size = length
        end = offset + size
        if end > len(data) or data[end - 1] != 0:
            raise LocresError(f"invalid UTF-8 FString bounds/terminator at 0x{offset - 4:X} (length={length})")
        try:
            return FString(data[offset : end - 1].decode("utf-8"), False), end
        except UnicodeDecodeError as exc:
            raise LocresError(f"invalid UTF-8 FString at 0x{offset:X}") from exc
    chars = -length
    size = chars * 2
    end = offset + size
    if end > len(data) or data[end - 2 : end] != b"\0\0":
        raise LocresError("invalid UTF-16 FString bounds/terminator")
    try:
        return FString(data[offset : end - 2].decode("utf-16-le"), True), end
    except UnicodeDecodeError as exc:
        raise LocresError(f"invalid UTF-16 FString at 0x{offset:X}") from exc


def write_fstring(value: FString) -> bytes:
    if value.utf16 or any(ord(char) > 0x7F for char in value.value):
        raw = value.value.encode("utf-16-le") + b"\0\0"
        return struct.pack("<i", -(len(raw) // 2)) + raw
    raw = value.value.encode("utf-8") + b"\0"
    return struct.pack("<i", len(raw)) + raw


def parse(data: bytes) -> Resource:
    if len(data) < HEADER.size:
        raise LocresError("file is shorter than LOCRES header")
    magic, version, string_offset, total_keys = HEADER.unpack_from(data)
    if magic != MAGIC:
        raise LocresError("not a modern Unreal LOCRES file (magic mismatch)")
    if version < 2 or version > 3:
        raise LocresError(f"unsupported LOCRES version {version}; expected version 2 or 3")
    if string_offset < HEADER.size or string_offset >= len(data):
        raise LocresError(f"localized string table offset outside file: {string_offset}")

    if HEADER.size + 4 > string_offset:
        raise LocresError("missing namespace count")
    namespace_count = struct.unpack_from("<I", data, HEADER.size)[0]
    entries: list[Entry] = []
    namespace_data = data[:string_offset]
    pos = HEADER.size
    pos += 4
    for _ in range(namespace_count):
        if pos + 4 > string_offset:
            raise LocresError(f"namespace table ended after {len(entries)} of {total_keys} keys")
        namespace_hash = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        namespace, pos = read_fstring(namespace_data, pos)
        if pos + 4 > string_offset:
            raise LocresError("truncated namespace key count")
        count = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if count == 0 or len(entries) + count > total_keys:
            raise LocresError(f"invalid key count {count} for namespace {namespace.value!r}")
        for _ in range(count):
            if pos + 4 > string_offset:
                raise LocresError("truncated key hash")
            key_hash = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            key, pos = read_fstring(namespace_data, pos)
            if pos + 8 > string_offset:
                raise LocresError("truncated source hash/string index")
            source_hash, value_index = struct.unpack_from("<Ii", data, pos)
            pos += 8
            entries.append(Entry(namespace_hash, namespace, key_hash, key, source_hash, value_index))
    if len(entries) != total_keys:
        raise LocresError(f"header declares {total_keys} keys, namespace table contains {len(entries)}")

    pos = string_offset
    if pos + 4 > len(data):
        raise LocresError("missing localized string count")
    string_count = struct.unpack_from("<i", data, pos)[0]
    pos += 4
    if string_count < 0 or string_count > total_keys + 1_000_000:
        raise LocresError(f"invalid localized string count {string_count}")
    strings: list[FString] = []
    refs: list[int] = []
    for _ in range(string_count):
        value, pos = read_fstring(data, pos)
        if pos + 4 > len(data):
            raise LocresError("truncated localized string refcount")
        ref_count = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        if ref_count < 0:
            raise LocresError("negative localized string refcount")
        strings.append(value)
        refs.append(ref_count)
    if pos != len(data):
        raise LocresError(f"unexpected {len(data) - pos} trailing bytes after string table")
    seen: set[str] = set()
    actual_refs = [0] * string_count
    for entry in entries:
        if entry.value_index < 0 or entry.value_index >= string_count:
            raise LocresError(f"string index {entry.value_index} is out of range")
        key = f"{entry.namespace.value}\t{entry.key.value}"
        if key in seen:
            raise LocresError(f"duplicate localization key: {key!r}")
        seen.add(key)
        actual_refs[entry.value_index] += 1
    if actual_refs != refs:
        raise LocresError("localized string reference counts do not match namespace entries")
    return Resource(version, entries, strings, refs)


def insert_missing(ru: Resource, en: Resource, additions: dict[str, str]) -> Resource:
    """Insert explicitly requested EN entries into RU in native EN order.

    Preserve every existing RU entry, including unrelated RU-only keys.
    Shared entries must retain their EN order; additions use EN anchors.
    """
    if not additions:
        return ru
    identity = lambda e: f"{e.namespace.value}\t{e.key.value}"
    ru_entries = {identity(e): e for e in ru.entries}
    en_entries = {identity(e): e for e in en.entries}
    if set(additions) & set(ru_entries) or set(additions) - set(en_entries):
        raise LocresError('additions require EN exists + RU missing')
    if ru.version != en.version:
        raise LocresError('EN/RU LOCRES versions differ')
    if [identity(e) for e in en.entries if identity(e) in ru_entries] != [
            identity(e) for e in ru.entries if identity(e) in en_entries]:
        raise LocresError('stock RU order is not a native EN subsequence')
    strings = list(ru.strings)
    entries = list(ru.entries)
    en_position = {identity(e): i for i, e in enumerate(en.entries)}
    namespace_position = {}
    for source in en.entries:
        namespace_position.setdefault(source.namespace.value, len(namespace_position))
    for source in en.entries:
        key = identity(source)
        if key in additions:
            if not isinstance(additions[key], str) or not additions[key].strip():
                raise LocresError('addition must be nonempty text')
            same_namespace = [i for i, entry in enumerate(entries)
                              if entry.namespace.value == source.namespace.value]
            if same_namespace:
                position = next((i for i in same_namespace
                                 if en_position.get(identity(entries[i]), -1) > en_position[key]),
                                same_namespace[-1] + 1)
            else:
                position = next((i for i, entry in enumerate(entries)
                                 if namespace_position.get(entry.namespace.value, -1) >
                                 namespace_position[source.namespace.value]), len(entries))
            entries.insert(position, replace(source, namespace=replace(source.namespace),
                                             key=replace(source.key), value_index=len(strings)))
            strings.append(FString(additions[key], any(ord(c) > 127 for c in additions[key])))
    refs = [0] * len(strings)
    for entry in entries:
        refs[entry.value_index] += 1
    return Resource(ru.version, entries, strings, refs)


def serialize(resource: Resource, edits: dict[str, str]) -> bytes:
    by_key = {f"{e.namespace.value}\t{e.key.value}": e for e in resource.entries}
    missing = sorted(set(edits) - set(by_key))
    if missing:
        sample = ", ".join(repr(key) for key in missing[:5])
        raise LocresError(f"{len(missing)} correction key(s) absent from base RU LOCRES: {sample}")

    unique_values: list[FString] = []
    indices: dict[str, int] = {}
    new_indices: dict[int, int] = {}
    ref_counts: list[int] = []
    for entry in resource.entries:
        key = f"{entry.namespace.value}\t{entry.key.value}"
        old = resource.strings[entry.value_index]
        value = edits.get(key, old.value)
        if value not in indices:
            indices[value] = len(unique_values)
            unique_values.append(FString(value, old.utf16 if value == old.value else any(ord(c) > 0x7F for c in value)))
            ref_counts.append(0)
        new_indices[id(entry)] = indices[value]
        ref_counts[indices[value]] += 1

    namespace_bytes = bytearray()
    cursor = 0
    while cursor < len(resource.entries):
        first = resource.entries[cursor]
        end = cursor + 1
        while end < len(resource.entries) and resource.entries[end].namespace.value == first.namespace.value:
            end += 1
        namespace_bytes += struct.pack("<I", first.namespace_hash)
        namespace_bytes += write_fstring(first.namespace)
        namespace_bytes += struct.pack("<I", end - cursor)
        for entry in resource.entries[cursor:end]:
            namespace_bytes += struct.pack("<I", entry.key_hash)
            namespace_bytes += write_fstring(entry.key)
            namespace_bytes += struct.pack("<Ii", entry.source_hash, new_indices[id(entry)])
        cursor = end

    string_offset = HEADER.size + 4 + len(namespace_bytes)
    out = bytearray(HEADER.pack(MAGIC, resource.version, string_offset, len(resource.entries)))
    namespace_count = 0
    previous_namespace: str | None = None
    for entry in resource.entries:
        if entry.namespace.value != previous_namespace:
            namespace_count += 1
            previous_namespace = entry.namespace.value
    out += struct.pack("<I", namespace_count)
    out += namespace_bytes
    out += struct.pack("<i", len(unique_values))
    for value, count in zip(unique_values, ref_counts):
        out += write_fstring(value)
        out += struct.pack("<i", count)
    return bytes(out)


def load_edits(path: Path) -> dict[str, str]:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise LocresError(f"duplicate JSON key in {path}: {key!r}")
            result[key] = value
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise LocresError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()):
        raise LocresError(f"expected a JSON object mapping namespace<TAB>key to text in {path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    dump = sub.add_parser("dump")
    dump.add_argument("source", type=Path)
    dump.add_argument("output", type=Path)
    build = sub.add_parser("build")
    build.add_argument("source", type=Path)
    build.add_argument("corrections", type=Path)
    build.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        resource = parse(args.source.read_bytes())
        if args.command == "dump":
            args.output.write_text(json.dumps(resource.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"LOCRES v{resource.version}: {len(resource.entries)} keys -> {args.output}")
        else:
            edits = load_edits(args.corrections)
            built = serialize(resource, edits)
            check = parse(built)
            if check.as_dict() != {**resource.as_dict(), **edits}:
                raise LocresError("post-write LOCRES verification mismatch")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(built)
            print(f"LOCRES v{check.version}: {len(check.entries)} keys, {len(edits)} corrections -> {args.output} ({len(built):,} bytes)")
        return 0
    except (OSError, LocresError) as exc:
        print(f"LOCRES error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
