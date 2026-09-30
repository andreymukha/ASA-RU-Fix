"""Create deterministic, non-semantic review CSVs from official EN/RU LOCRES dumps."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGS = (
    'untranslated', 'missing_ru', 'missing_en', 'latin_in_ru',
    'placeholder_mismatch', 'tag_mismatch', 'newline_mismatch',
    'suspicious_length', 'same_en_multiple_ru', 'same_ru_multiple_en',
    'case_suspicious', 'known_bad_term',
)
ALL_FIELDS = (
    'key', 'namespace', 'full_key', 'en', 'ru', 'our_ru', 'already_corrected',
    *FLAGS, 'same_en_other_ru', 'same_ru_other_en', 'heuristic_score', 'suspicious', 'flags',
)
SUSPICIOUS_FIELDS = ALL_FIELDS

# Recognized English UI names, abbreviations, input symbols and measurement units.
# This is a conservative whitelist, not a translation dictionary.
SAFE_LATIN = frozenset('''
    ark asa ui ux fps dlss fsr rtx amd nvidia xbox pc pvp pve pvepvp pvpve pve
    hud xp hp mp sp dps dcdlc dlc p2p mtu cpu gpu ram ssd hdd usb hdmi kb mb gb
    tb pb bps kbps mbps gbps ms sec min hr hrs kg g mg lb lbs cm mm m km mph kph
    c f psi psi rpm hz khz mhz ghz dpi fov rgb hdr id uid url www com net org
    wasd esc tab shift ctrl control alt space enter return backspace delete del
    insert home end pageup pagedown up down left right numpad capslock
'''.split())

TAG_RE = re.compile(r'<\s*(?:(/)?([A-Za-z][\w:.-]*)\b[^<>]*?(/?)|(/))\s*>')
TAG_ATTRIBUTE_RE = re.compile(r'([A-Za-z_:][\w:.-]*)\s*=')
BRACE_RE = re.compile(r'\{\s*([A-Za-z_][\w.-]*|\d+)(?:\s*:[^{}]*)?\s*\}')
PRINTF_RE = re.compile(
    r"%(?P<position>\([^)]+\)|\d+\$)?[-+#0 'I]*(?:\d+|\*)?"
    r'(?:\.(?:\d+|\*))?(?:hh|h|ll|l|L|z|j|t)?'
    r'(?P<conversion>[diuoxXfFeEgGaAcsp])'
)
LATIN_RE = re.compile(r'[A-Za-z]{3,}')
URL_RE = re.compile(r'\b(?:https?://|www\.)[^\s<>{}]+', re.IGNORECASE)
INPUT_KEY_RE = re.compile(r'\b(?:Gamepad|Mouse|Keyboard|Controller)_[A-Za-z0-9_+-]+\b', re.IGNORECASE)
CYRILLIC_LOWER_RE = re.compile(r'^[а-яё]')


def _normalize(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFC', value).split()).casefold()


def _tags(value: str) -> Counter:
    result = Counter()
    for match in TAG_RE.finditer(value):
        closing, name, self_closing, anonymous_close = match.groups()
        if anonymous_close:
            result[('/', '')] += 1
        else:
            body = match.group(0).strip()[1:-1].lstrip().lstrip('/')
            body = re.sub(r'^[A-Za-z][\w:.-]*', '', body, count=1)
            attributes = tuple(sorted(attribute.casefold() for attribute in TAG_ATTRIBUTE_RE.findall(body)))
            result[('/' if closing else ('/' if self_closing else '+'), name.casefold(), attributes)] += 1
    return result


def _placeholders(value: str) -> Counter:
    result = Counter()
    for match in BRACE_RE.finditer(value):
        result['brace:' + match.group(1)] += 1
    escaped_percent = value.replace('%%', '')
    for match in PRINTF_RE.finditer(escaped_percent):
        # Width/precision can differ by language; argument position and value
        # conversion identify the formatting contract.
        position = match.group('position') or ''
        result[f"printf:{position}:{match.group('conversion').lower()}"] += 1
    return result


def _plain(value: str) -> str:
    return BRACE_RE.sub('', TAG_RE.sub('', value)).strip()


def _is_noise(value: str) -> bool:
    text = value.strip()
    if not text or not any(char.isalpha() for char in text):
        return True
    if re.match(r'^(?:https?://|www\.)\S+$', text, re.IGNORECASE):
        return True
    remainder = PRINTF_RE.sub('', BRACE_RE.sub('', text)).replace('%%', '').strip()
    if not remainder or not any(char.isalpha() for char in remainder):
        return True
    if re.fullmatch(r'[A-Z][A-Z0-9._+#/-]{1,11}', remainder):
        return True
    if len(remainder) <= 3 and not re.search(r'\s', remainder):
        return True
    return False


def _latin_in_ru(value: str, namespace: str = '') -> bool:
    if namespace.casefold() in {'inputkeys', 'keyboardkeys', 'controllerkeys', 'keynames'}:
        return False
    text = URL_RE.sub('', _plain(value))
    text = re.sub(r'\b(?:version|ver|build|v)\s*[:#-]?\s*v?\d[\w.+-]*', '', text, flags=re.IGNORECASE)
    text = INPUT_KEY_RE.sub('', text)
    for word in LATIN_RE.findall(text):
        lower = word.casefold()
        if lower in SAFE_LATIN or word.isupper() or word.istitle():
            continue
        if re.search(r'[a-z][A-Z]', word):  # deterministic CamelCase/proper-name shape
            continue
        if re.fullmatch(r'[A-Z]+\d+[A-Z0-9]*', word):
            continue
        if lower in {'true', 'false', 'null', 'none'}:
            continue
        return True
    return False


def _untranslated_noise(value: str) -> bool:
    text = value.strip()
    return _is_noise(text) or re.fullmatch(r'[\d\W_]+', text, re.UNICODE) is not None


def _case_suspicious(en: str, ru: str, known_ui: bool) -> bool:
    russian = _plain(ru).strip()
    english = _plain(en).strip()
    if not CYRILLIC_LOWER_RE.match(russian):
        return False
    if not english or re.search(r'[.!?…]\s*$', english):
        return False
    # The source casing is only a weak UI hint; an explicitly verified key can
    # establish a standalone label even when its English source is lowercase.
    english_label = known_ui or (english[:1].isupper() and len(english.split()) <= 8)
    return english_label and len(russian.split()) <= 12


def _mapping(raw: object, path: str) -> dict[str, str]:
    if not isinstance(raw, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in raw.items()):
        raise ValueError(f'{path} must be a JSON object with string keys and values')
    return raw


def _group_alternatives(rows: list[dict], source_field: str, target_field: str) -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        source, target = row[source_field], row[target_field]
        if not source or not target:
            continue
        grouped[_normalize(source)].setdefault(_normalize(target), target.strip())
    return {source: values for source, values in grouped.items() if len(values) > 1}


def analyze(en: dict[str, str], ru: dict[str, str], corrections: dict[str, str] | None = None,
            known_bad_terms: list[dict[str, str]] | None = None) -> list[dict]:
    """Return sorted union rows and strictly mechanical diagnostics."""
    corrections = corrections or {}
    known_bad_terms = known_bad_terms or []
    keys = sorted(set(en) | set(ru))
    rows = []
    for full_key in keys:
        namespace, separator, key = full_key.partition('\t')
        if not separator:
            raise ValueError(f'full_key must contain namespace<TAB>key: {full_key!r}')
        rows.append({
            'key': key, 'namespace': namespace, 'full_key': full_key,
            'en': en.get(full_key, ''), 'ru': ru.get(full_key, ''),
            'our_ru': corrections.get(full_key, ''), 'already_corrected': full_key in corrections,
        })

    same_en = _group_alternatives(rows, 'en', 'ru')
    same_ru = _group_alternatives(rows, 'ru', 'en')
    known_terms = {
        term['full_key']: (_normalize(term['en']), _normalize(term['ru']))
        for term in known_bad_terms
    }

    for row in rows:
        english, russian, full_key = row['en'], row['ru'], row['full_key']
        en_norm, ru_norm = _normalize(english), _normalize(russian)
        other_ru = same_en.get(en_norm, {})
        other_en = same_ru.get(ru_norm, {})
        flags = {
            'untranslated': bool(english and russian and english.strip().casefold() == russian.strip().casefold()),
            'missing_ru': full_key in en and full_key not in ru,
            'missing_en': full_key in ru and full_key not in en,
            'latin_in_ru': bool(russian and _latin_in_ru(russian, namespace)),
            'placeholder_mismatch': bool(english and russian and _placeholders(english) != _placeholders(russian)),
            'tag_mismatch': bool(english and russian and _tags(english) != _tags(russian)),
            'newline_mismatch': False,
            'suspicious_length': False,
            'same_en_multiple_ru': bool(en_norm and en_norm in same_en),
            'same_ru_multiple_en': bool(ru_norm and ru_norm in same_ru),
            'case_suspicious': False,
            'known_bad_term': False,
        }
        terms = known_terms.get(full_key)
        if terms:
            flags['known_bad_term'] = (en_norm, ru_norm) == terms
        flags['case_suspicious'] = bool(russian and english and _case_suspicious(english, russian, bool(terms)))

        en_newlines, ru_newlines = english.count('\n'), russian.count('\n')
        gap = abs(en_newlines - ru_newlines)
        flags['newline_mismatch'] = bool(gap >= 2 or (
            max(en_newlines, ru_newlines) >= 2 and
            min(en_newlines, ru_newlines) * 2 <= max(en_newlines, ru_newlines)))

        en_length, ru_length = len(_plain(english)), len(_plain(russian))
        if min(en_length, ru_length) >= 12:
            ratio = max(en_length, ru_length) / min(en_length, ru_length)
            flags['suspicious_length'] = ratio >= 3.0

        score = 0
        for flag, weight in (
            ('missing_ru', 10), ('placeholder_mismatch', 9), ('tag_mismatch', 9),
            ('known_bad_term', 9), ('missing_en', 6), ('untranslated', 7),
            ('latin_in_ru', 5), ('same_en_multiple_ru', 4),
            ('same_ru_multiple_en', 4), ('case_suspicious', 4),
            ('newline_mismatch', 2), ('suspicious_length', 1),
        ):
            if flags[flag]:
                if flag != 'untranslated' or not _untranslated_noise(russian):
                    score += weight

        row.update(flags)
        row['same_en_other_ru'] = json.dumps(
            sorted((value for normalized, value in other_ru.items() if normalized != ru_norm), key=lambda v: (_normalize(v), v)),
            ensure_ascii=False, separators=(',', ':')) if other_ru else ''
        row['same_ru_other_en'] = json.dumps(
            sorted((value for normalized, value in other_en.items() if normalized != en_norm), key=lambda v: (_normalize(v), v)),
            ensure_ascii=False, separators=(',', ':')) if other_en else ''
        row['heuristic_score'] = score
        row['suspicious'] = score > 0
        row['flags'] = ';'.join(name.upper() for name in FLAGS if flags[name])

    return rows


def write_csv(path: Path, rows: list[dict], fields: tuple[str, ...] | list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore',
                                quoting=csv.QUOTE_MINIMAL, lineterminator='\r\n')
        writer.writeheader()
        for row in rows:
            encoded = {key: ('true' if value is True else 'false' if value is False else value)
                       for key, value in row.items()}
            writer.writerow(encoded)


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'Cannot read valid JSON from {path}: {exc}') from exc


def run_audit(root: Path = ROOT) -> dict:
    root = Path(root)
    en_path, ru_path = root / 'work/en.json', root / 'work/ru.json'
    en = _mapping(_load_json(en_path), str(en_path))
    ru = _mapping(_load_json(ru_path), str(ru_path))
    corrections = _mapping(_load_json(root / 'data/corrections.json'), 'data/corrections.json')
    term_data = _load_json(root / 'data/audit_terms.json')
    terms = term_data.get('known_bad_terms') if isinstance(term_data, dict) else None
    if not isinstance(terms, list) or any(
        not isinstance(term, dict) or not all(isinstance(term.get(field), str) and term[field]
                                              for field in ('full_key', 'en', 'ru'))
        for term in terms
    ):
        raise ValueError('data/audit_terms.json must contain known_bad_terms with full_key, en and ru strings')

    rows = analyze(en, ru, corrections, terms)
    suspicious = [row for row in rows if row['heuristic_score'] > 0]
    suspicious.sort(key=lambda row: (-row['heuristic_score'], row['full_key']))
    output_dir = root / 'audit'
    write_csv(output_dir / 'all_strings.csv', rows, ALL_FIELDS)
    write_csv(output_dir / 'suspicious.csv', suspicious, SUSPICIOUS_FIELDS)

    flag_counts = Counter(flag for row in rows for flag in FLAGS if row[flag])
    flag_counts['already_corrected'] = sum(row['already_corrected'] for row in rows)
    summary = {
        'en_key_count': len(en), 'ru_key_count': len(ru), 'union_key_count': len(rows),
        'suspicious_count': len(suspicious),
        'flag_counts': {flag: flag_counts.get(flag, 0) for flag in (*FLAGS, 'already_corrected')},
        'heuristic_score_note': 'Deterministic review-priority score only; not translation quality or semantic judgment.',
        'inputs': {
            'en_sha256': hashlib.sha256(en_path.read_bytes()).hexdigest(),
            'ru_sha256': hashlib.sha256(ru_path.read_bytes()).hexdigest(),
            'corrections_sha256': hashlib.sha256((root / 'data/corrections.json').read_bytes()).hexdigest(),
            'audit_terms_sha256': hashlib.sha256((root / 'data/audit_terms.json').read_bytes()).hexdigest(),
        },
        'outputs': {
            'all_strings_csv_bytes': (output_dir / 'all_strings.csv').stat().st_size,
            'suspicious_csv_bytes': (output_dir / 'suspicious.csv').stat().st_size,
        },
    }
    (output_dir / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return summary


def main() -> int:
    summary = run_audit()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"CSV files: {ROOT / 'audit' / 'all_strings.csv'}; {ROOT / 'audit' / 'suspicious.csv'}")
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f'AUDIT ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
