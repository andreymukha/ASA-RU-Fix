import unittest

from build import build_desired_resource
from tools.locres import Entry, FString, Resource, insert_missing, parse, serialize
from tools.server_depot import PINNED_STOCK, PINNED_MANIFEST, validate_stock_resources


def resource(keys):
    return Resource(3, [Entry(10, FString('n', False), i + 20, FString(k, False),
                             i + 30, i) for i, k in enumerate(keys)],
                    [FString(k, False) for k in keys], [1] * len(keys))


class LiveBuildTests(unittest.TestCase):
    def test_live_stock_uses_structure_instead_of_unknown_exact_hashes(self):
        raw = serialize(resource(['a']), {})
        report = validate_stock_resources({name: raw for name in PINNED_STOCK}, profile='live')
        self.assertTrue(all(row['entries'] == 1 and row['status'] == 'PASS' for row in report.values()))

    def test_live_stock_missing_required_resource_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'set mismatch'):
            validate_stock_resources({}, profile='live')

    def test_all_desired_classes_survive_reopened_locres(self):
        en, ru = resource(['a', 'b', 'c']), resource(['a', 'c'])
        baseline = {'schema': 1, 'manifest_id': PINNED_MANIFEST, 'resources': {'Engine': {}, 'ShooterGame': {
            'n\t' + entry.key.value: {field: getattr(entry, field)
                for field in ('namespace_hash', 'key_hash', 'source_hash')} for entry in en.entries}}}
        desired = {'n\ta': 'А', 'n\tb': 'Б', 'n\tc': 'c'}
        built, report = build_desired_resource(en, ru, desired, baseline, 'ShooterGame')
        self.assertEqual(parse(built).as_dict(), desired)
        self.assertEqual(report['desired_verification']['actual'], 3)
        self.assertEqual(report['classification']['already_correct'], 1)
        self.assertEqual(report['desired_preflight']['checked'], 3)

    def test_unrelated_ru_only_entry_is_preserved_during_addition(self):
        en, ru = resource(['a', 'b', 'c']), resource(['a', 'ru-only', 'c'])
        built = insert_missing(ru, en, {'n\tb': 'Б'})
        self.assertEqual([e.key.value for e in built.entries], ['a', 'ru-only', 'b', 'c'])
        self.assertEqual(built.as_dict()['n\tru-only'], 'ru-only')
