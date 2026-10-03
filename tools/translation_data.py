"""Validate desired translations against reviewed EN identities and current stock RU.

New desired keys require explicit ``accept-source --key Namespace<TAB>Key``.
Acceptance changes only the named identities and never copies official EN text.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections.abc import Mapping
from pathlib import Path

from tools.corrections import CorrectionError, validate_corrections
from tools.locres import Entry, LocresError, Resource, load_edits, parse
from tools.server_depot import PINNED_MANIFEST

ROOT = Path(__file__).resolve().parents[1]
HASH_FIELDS = ('namespace_hash', 'key_hash', 'source_hash')
RESOURCE_FILES = {'ShooterGame': 'shootergame_ru.json', 'Engine': 'engine_ru.json'}


class TranslationDataError(LocresError):
    def __init__(self, issues: list[dict]):
        self.issues = issues
        super().__init__('Translation data validation failed:\n' + '\n'.join(
            f"{item['kind']}: {item['full_key']!r}: {item['detail']}" for item in issues
        ))


def identity_of(entry: Entry) -> dict[str, int]:
    return {field: getattr(entry, field) for field in HASH_FIELDS}


def _issue(key: str, kind: str, detail: str) -> dict:
    return {'full_key': key, 'kind': kind, 'detail': detail}


def _identities(baseline: Mapping, resource_name: str) -> Mapping:
    if resource_name not in RESOURCE_FILES:
        raise TranslationDataError([_issue('', 'invalid_resource', resource_name)])
    if (not isinstance(baseline, Mapping) or type(baseline.get('schema')) is not int
            or baseline['schema'] != 1 or baseline.get('manifest_id') != PINNED_MANIFEST
            or not isinstance(baseline.get('resources'), Mapping)
            or set(baseline['resources']) != set(RESOURCE_FILES)
            or any(not isinstance(value, Mapping) for value in baseline['resources'].values())):
        raise TranslationDataError([_issue('', 'invalid_baseline',
                                          'expected schema 1, pinned manifest_id and ShooterGame/Engine identity maps')])
    return baseline['resources'][resource_name]


def _valid_identity(value: object) -> bool:
    return (isinstance(value, Mapping) and set(value) == set(HASH_FIELDS)
            and all(type(value[field]) is int and 0 <= value[field] <= 0xFFFFFFFF
                    for field in HASH_FIELDS))


def load_source_identity(path: Path) -> dict:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise TranslationDataError([_issue(key, 'invalid_baseline', 'duplicate JSON key')])
            result[key] = value
        return result
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise TranslationDataError([_issue('', 'invalid_baseline', str(exc))]) from exc
    _identities(data, 'ShooterGame')
    return data


def _validate_desired(desired: Mapping, en: Resource, ru: Resource) -> dict:
    if not isinstance(desired, Mapping):
        raise TranslationDataError([_issue('', 'invalid_desired', 'expected a translation mapping')])
    en_text, ru_text = en.as_dict(), ru.as_dict()
    try:
        # EN-only entries are legitimate additions; keep the same formatting
        # checks used by the existing corrections API.
        return validate_corrections(desired, en_text, {**en_text, **ru_text})
    except CorrectionError as exc:
        raise TranslationDataError(exc.issues) from exc


def classify_desired(desired: Mapping[str, str], en: Resource, ru: Resource,
                     baseline: Mapping, *, resource_name: str = 'ShooterGame') -> dict:
    identities = _identities(baseline, resource_name)
    try:
        validation = _validate_desired(desired, en, ru)
    except TranslationDataError as exc:
        raise TranslationDataError([{**issue, 'resource': resource_name} for issue in exc.issues]) from exc
    entries = {f'{entry.namespace.value}\t{entry.key.value}': entry for entry in en.entries}
    issues = []
    for key in sorted(desired):
        reviewed = identities.get(key)
        if reviewed is None:
            issues.append(_issue(key, 'baseline_missing', 'explicit accept-source is required'))
        elif not _valid_identity(reviewed):
            issues.append(_issue(key, 'invalid_baseline', 'expected three unsigned 32-bit hashes'))
        else:
            current = identity_of(entries[key])
            changed = [field for field in HASH_FIELDS if reviewed[field] != current[field]]
            if changed:
                issues.append({**_issue(key, 'source_changed',
                                       f'changed {", ".join(changed)}: reviewed={dict(reviewed)!r}; current={current!r}'),
                               'old_identity': dict(reviewed), 'current_identity': current,
                               'old_source_hash': reviewed['source_hash'], 'current_source_hash': current['source_hash']})
    if issues:
        raise TranslationDataError([{**issue, 'resource': resource_name} for issue in issues])
    current_ru = ru.as_dict()
    result = {'corrections': {}, 'additions': {}, 'already_correct': {}}
    for key, value in sorted(desired.items()):
        category = ('additions' if key not in current_ru else
                    'already_correct' if current_ru[key] == value else 'corrections')
        result[category][key] = value
    result['counts'] = {category: len(values) for category, values in result.items()}
    result['counts'].update(missing=0, source_changed=0, desired=len(desired))
    result['validation'] = validation
    return result


def accept_source_identities(desired: Mapping[str, str], en: Resource, baseline: Mapping,
                             keys: list[str], *, resource_name: str = 'ShooterGame') -> tuple[dict, list[dict]]:
    """Return a copied baseline with only explicitly named desired keys accepted."""
    reviewed = _identities(baseline, resource_name)
    if not keys:
        raise TranslationDataError([_issue('', 'explicit_keys_required', 'at least one --key is required')])
    if not isinstance(desired, Mapping):
        raise TranslationDataError([_issue('', 'invalid_desired', 'expected a translation mapping')])
    issues = []
    for key in keys:
        if not isinstance(key, str) or key.count('\t') != 1 or not all(key.split('\t')):
            issues.append(_issue(key, 'invalid_key', 'expected nonempty namespace<TAB>key'))
        elif key not in desired:
            issues.append(_issue(key, 'unknown_desired_key', 'key is absent from desired translations'))
        elif key in reviewed and not _valid_identity(reviewed[key]):
            issues.append(_issue(key, 'invalid_baseline', 'expected three unsigned 32-bit hashes'))
    if issues:
        raise TranslationDataError(issues)
    selected = {key: desired[key] for key in sorted(set(keys))}
    _validate_desired(selected, en, en)
    entries = {f'{entry.namespace.value}\t{entry.key.value}': entry for entry in en.entries}
    updated = copy.deepcopy(dict(baseline))
    changes = []
    for key in selected:
        current = identity_of(entries[key])
        changes.append({'full_key': key, 'old': reviewed.get(key), 'new': current})
        updated['resources'][resource_name][key] = current
    return updated, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    accept = commands.add_parser('accept-source', help='Review explicitly named EN identities')
    accept.add_argument('--resource', choices=tuple(RESOURCE_FILES), required=True)
    accept.add_argument('--stock-en', type=Path, required=True)
    accept.add_argument('--key', action='append', required=True, help='Exact Namespace<TAB>Key; repeatable')
    accept.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'data/source_identity.json'
    updated, changes = accept_source_identities(
        load_edits(ROOT / 'data' / RESOURCE_FILES[args.resource]), parse(args.stock_en.read_bytes()),
        load_source_identity(path), args.key, resource_name=args.resource)
    print(json.dumps({'resource': args.resource, 'identities': changes}, ensure_ascii=False, indent=2, sort_keys=True))
    if args.apply:
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, LocresError) as exc:
        print(str(exc))
        raise SystemExit(2)
