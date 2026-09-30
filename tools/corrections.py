"""Strict mechanical validation and optional import of externally reviewed corrections."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from tools.locres import LocresError, load_edits

ROOT = Path(__file__).resolve().parents[1]
BRACES = re.compile(r'(?<!\{)\{([^{}\r\n]+)\}(?!\})')
PRINTF = re.compile(
    r"%(?:\([^)]+\)|\d+\$)?[-+#0 'I]*(?:\d+|\*)?"
    r'(?:\.(?:\d+|\*))?(?:hh|h|ll|l|L|z|j|t)?[diuoxXfFeEgGaAcsp]'
)
TAGS = re.compile(r'(?<!<)<\s*(?:(/)?([A-Za-z][\w:.-]*)\b([^<>]*?)|(/))\s*>(?!>)')
ATTRIBUTES = re.compile(r'([A-Za-z_:][\w:.-]*)\s*=')
VOID_TAGS = frozenset({'br', 'img', 'hr', 'wbr', 'input'})


class CorrectionError(LocresError):
    def __init__(self, issues: list[dict]):
        self.issues = issues
        super().__init__('Correction validation failed:\n' + '\n'.join(
            f"{item['kind']}: {item['full_key']!r}: {item['detail']}" for item in issues
        ))


def placeholders(value: str) -> Counter:
    """Keep exact argument identities, repetition, printf positions and precision."""
    tokens = Counter('brace:' + match.group(1).strip() for match in BRACES.finditer(value))
    percent_text = value.replace('%%', '')
    for match in PRINTF.finditer(percent_text):
        # Percent followed by a normal word ("10% food") is not a printf
        # conversion. Compact tokens can be adjacent to the following text.
        token = match.group(0)
        if token.startswith('% ') and match.end() < len(percent_text) and percent_text[match.end()].isalpha():
            continue
        tokens['printf:' + token] += 1
    return tokens


def richtext(value: str) -> tuple[Counter, list[str]]:
    signature, errors, stack = Counter(), [], []
    for match in TAGS.finditer(value):
        closing, name, body, anonymous = match.groups()
        if anonymous:
            signature[('close', '')] += 1
            if not stack:
                errors.append('anonymous closing tag has no opening tag')
            else:
                stack.pop()
            continue
        name = name.casefold()
        attributes = tuple(sorted(attribute.casefold() for attribute in ATTRIBUTES.findall(body)))
        self_closing = body.rstrip().endswith('/') or name in VOID_TAGS
        kind = 'close' if closing else 'void' if self_closing else 'open'
        signature[(kind, name, attributes)] += 1
        if closing:
            if not stack or stack[-1] != name:
                errors.append(f'closing {name!r} does not match the opening tag')
            else:
                stack.pop()
        elif not self_closing:
            stack.append(name)
    if stack:
        errors.append(f'unclosed tags: {stack!r}')
    return signature, errors


def validate_corrections(corrections: dict[str, str], en: dict[str, str], ru: dict[str, str]) -> dict:
    issues = []
    placeholder_count = markup_count = fragment_count = 0
    for key, value in corrections.items():
        def issue(kind, detail):
            issues.append({'full_key': key, 'kind': kind, 'detail': detail})
        if not isinstance(key, str) or key.count('\t') != 1 or not all(key.split('\t')):
            issue('invalid_key', 'expected nonempty namespace<TAB>key')
            continue
        if key not in ru:
            issue('missing_ru_key', 'key is absent from current official RU LOCRES')
        if key not in en:
            issue('missing_en_key', 'key is absent from current official EN LOCRES')
        if not isinstance(value, str) or not value.strip():
            issue('invalid_value', 'replacement must be a nonempty string')
            continue
        if key not in en:
            continue
        source_tokens, proposed_tokens = placeholders(en[key]), placeholders(value)
        placeholder_count += bool(source_tokens or proposed_tokens)
        if source_tokens != proposed_tokens:
            issue('placeholder_mismatch', f'EN={dict(source_tokens)!r}; proposed={dict(proposed_tokens)!r}')
        source_tags, source_errors = richtext(en[key])
        proposed_tags, markup_errors = richtext(value)
        markup_count += bool(source_tags or proposed_tags)
        if source_tags != proposed_tags:
            issue('markup_mismatch', f'EN={dict(source_tags)!r}; proposed={dict(proposed_tags)!r}')
        # A stock template can receive an opening tag from an argument, e.g.
        # {color} ... </>. Preserve that source boundary exactly, rather than
        # assuming each localization entry is a complete standalone widget.
        source_fragment = bool(source_errors and BRACES.match(en[key].lstrip()) and
                               set(source_tags) == {('close', '')} and
                               source_tags == proposed_tags and source_errors == markup_errors and
                               source_tokens == proposed_tokens)
        fragment_count += source_fragment
        if markup_errors and not source_fragment:
            issue('invalid_markup', '; '.join(markup_errors))
    if issues:
        raise CorrectionError(issues)
    return {'checked': len(corrections), 'placeholder_strings': placeholder_count,
            'richtext_strings': markup_count, 'source_markup_fragments': fragment_count, 'issues': 0}


def merge_candidates(candidates: dict[str, str], existing: dict[str, str],
                     en: dict[str, str], ru: dict[str, str]) -> tuple[dict[str, str], dict]:
    conflicts = [{'full_key': key, 'kind': 'conflict',
                  'detail': f'existing={existing[key]!r}; candidate={value!r}'}
                 for key, value in candidates.items() if key in existing and existing[key] != value]
    if conflicts:
        raise CorrectionError(conflicts)
    duplicates = sum(key in existing for key in candidates)
    validation = validate_corrections(candidates, en, ru)
    merged = dict(sorted({**existing, **candidates}.items()))
    validate_corrections(merged, en, ru)
    return merged, {'candidate_count': len(candidates), 'existing_count': len(existing),
                    'new_count': len(candidates) - duplicates, 'identical_duplicates': duplicates,
                    'total_count': len(merged), 'conflicts': 0, 'invalid_or_missing_keys': 0,
                    'validation': validation}


def verify_applied(corrections: dict[str, str], actual: dict[str, str]) -> dict:
    issues = [{'full_key': key, 'kind': 'correction_not_applied',
               'detail': f'expected={value!r}; actual={actual.get(key)!r}'}
              for key, value in corrections.items() if key not in actual or actual[key] != value]
    if issues:
        raise CorrectionError(issues)
    return {'expected': len(corrections), 'actual': len(corrections), 'mismatches': 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Write corrections only after successful preflight')
    parser.add_argument('--expected-new', type=int)
    parser.add_argument('--expected-total', type=int)
    args = parser.parse_args()
    # Run the production build first to refresh these STOCK dumps.
    en_path, ru_path = ROOT / 'work/en.json', ROOT / 'work/ru.json'
    corrections_path = ROOT / 'data/corrections.json'
    merged, report = merge_candidates(load_edits(args.candidate), load_edits(corrections_path),
                                      load_edits(en_path), load_edits(ru_path))
    for expected, field in ((args.expected_new, 'new_count'), (args.expected_total, 'total_count')):
        if expected is not None and report[field] != expected:
            raise CorrectionError([{'full_key': '', 'kind': 'unexpected_count',
                                    'detail': f'{field}: expected {expected}, found {report[field]}'}])
    report['inputs_sha256'] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for name, path in (('candidate', args.candidate), ('en', en_path), ('ru', ru_path))}
    if args.apply:
        corrections_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    report['applied'] = args.apply
    (ROOT / 'work/import_validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, LocresError) as exc:
        print(str(exc))
        raise SystemExit(2)
