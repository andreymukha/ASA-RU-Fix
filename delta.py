"""Report key and English-source changes between two generated LOCRES JSON dumps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_dump(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read JSON dump {path}: {exc}") from exc
    if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()):
        raise SystemExit(f"Expected a JSON object mapping namespace<TAB>key to text: {path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_en", type=Path, help="Previous generated English dump")
    parser.add_argument("new_en", type=Path, help="Current generated English dump")
    parser.add_argument("--corrections", type=Path, default=ROOT / "data/corrections.json")
    args = parser.parse_args()
    old, new, corrections = map(read_dump, (args.old_en, args.new_en, args.corrections))
    old_keys, new_keys = set(old), set(new)
    added, removed = sorted(new_keys - old_keys), sorted(old_keys - new_keys)
    changed = sorted(key for key in old_keys & new_keys if old[key] != new[key])
    orphaned = sorted(set(corrections) - new_keys)
    for title, keys in (("New keys", added), ("Removed keys", removed), ("English source changed", changed), ("Corrections with missing keys", orphaned)):
        print(f"{title}: {len(keys)}")
        for key in keys:
            print(f"  {key}" + (f"\n    old: {old[key]}\n    new: {new[key]}" if key in changed else ""))
    return 1 if orphaned else 0


if __name__ == "__main__":
    raise SystemExit(main())
