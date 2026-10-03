import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.locres import Entry, FString, Resource, load_edits, serialize
from tools.translation_data import (
    TranslationDataError, accept_source_identities, classify_desired, identity_of,
)


def resource(values):
    return Resource(3, [Entry(17, FString('Content', False), 100 + index,
                             FString(key, False), 200 + index, index)
                        for index, key in enumerate(values)],
                    [FString(value, False) for value in values.values()], [1] * len(values))


def baseline(en):
    return {'schema': 1, 'manifest_id': '3251368963427721326', 'resources': {
        'ShooterGame': {f'{entry.namespace.value}\t{entry.key.value}': identity_of(entry)
                        for entry in en.entries}, 'Engine': {}}}


class TranslationDataTests(unittest.TestCase):
    def setUp(self):
        self.en = resource({'a': 'Alpha', 'b': 'Beta'})
        self.desired = {'Content\ta': 'Альфа', 'Content\tb': 'Бета'}
        self.baseline = baseline(self.en)

    def classify(self, ru):
        return classify_desired(self.desired, self.en, ru, self.baseline)

    def test_ru_absent_then_appears_then_disappears(self):
        absent = self.classify(resource({}))
        self.assertEqual(absent['additions'], self.desired)
        appeared = self.classify(resource({'a': 'Старая строка'}))
        self.assertEqual(appeared['corrections'], {'Content\ta': 'Альфа'})
        self.assertEqual(appeared['additions'], {'Content\tb': 'Бета'})
        self.assertEqual(self.classify(resource({}))['additions'], self.desired)

    def test_already_correct_and_dynamic_counts_preserve_desired_total(self):
        result = self.classify(resource({'a': 'Альфа', 'b': 'Старая строка'}))
        self.assertEqual(result['already_correct'], {'Content\ta': 'Альфа'})
        self.assertEqual(result['counts'], {'corrections': 1, 'additions': 0,
                                          'already_correct': 1, 'missing': 0,
                                          'source_changed': 0, 'desired': 2})
        for ru in (resource({}), resource({'a': 'Старая строка'}),
                   resource({'a': 'Альфа', 'b': 'Бета'})):
            counts = self.classify(ru)['counts']
            self.assertEqual(sum(counts[name] for name in ('corrections', 'additions', 'already_correct')), 2)

    def test_missing_english_fails_with_issues(self):
        with self.assertRaises(TranslationDataError) as caught:
            classify_desired(self.desired, resource({'a': 'Alpha'}), resource({}), self.baseline)
        self.assertTrue(any(issue['kind'] == 'missing_en_key' for issue in caught.exception.issues))
        self.assertTrue(all(issue['resource'] == 'ShooterGame' for issue in caught.exception.issues))

    def test_each_identity_hash_change_fails(self):
        for field in ('namespace_hash', 'key_hash', 'source_hash'):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.en)
                setattr(changed.entries[0], field, getattr(changed.entries[0], field) + 1)
                with self.assertRaises(TranslationDataError) as caught:
                    classify_desired(self.desired, changed, resource({}), self.baseline)
                self.assertTrue(any(issue['kind'] == 'source_changed' for issue in caught.exception.issues))
                issue = next(issue for issue in caught.exception.issues if issue['kind'] == 'source_changed')
                self.assertEqual(issue['resource'], 'ShooterGame')
                self.assertEqual(issue['old_identity'], identity_of(self.en.entries[0]))
                self.assertEqual(issue['current_identity'], identity_of(changed.entries[0]))
                self.assertEqual(issue['old_source_hash'], self.en.entries[0].source_hash)
                self.assertEqual(issue['current_source_hash'], changed.entries[0].source_hash)

    def test_unrelated_key_change_is_allowed(self):
        desired = {'Content\ta': 'Альфа'}
        self.en.entries[1].source_hash += 1
        result = classify_desired(desired, self.en, resource({}), self.baseline)
        self.assertEqual(result['additions'], desired)

    def test_missing_or_invalid_baseline_fails(self):
        for change in ('missing', 'invalid', 'schema', 'manifest'):
            with self.subTest(change=change):
                data = copy.deepcopy(self.baseline)
                if change == 'missing':
                    del data['resources']['ShooterGame']['Content\ta']
                elif change == 'invalid':
                    data['resources']['ShooterGame']['Content\ta']['source_hash'] = '200'
                elif change == 'schema':
                    data['schema'] = 2
                else:
                    data['manifest_id'] = 'unreviewed'
                with self.assertRaises(TranslationDataError):
                    classify_desired(self.desired, self.en, resource({}), data)

    def test_invalid_key_value_and_placeholder_fail(self):
        for desired in ({'bad': 'Текст'}, {'Content\ta': ''}, {'Content\ta': 1},
                        {'Content\ta': 'Текст {Name}'}, {'Content\ta': 'Текст %s'},
                        {'Content\ta': '<b>Текст</b>'}):
            with self.subTest(desired=desired), self.assertRaises(TranslationDataError):
                classify_desired(desired, self.en, resource({}), self.baseline)

    def test_ru_identity_is_never_synchronized(self):
        ru = resource({'a': 'Старая строка'})
        ru.entries[0].source_hash = 999
        self.classify(ru)
        self.assertEqual(ru.entries[0].source_hash, 999)

    def test_explicit_accept_updates_only_requested_key_without_mutation(self):
        before = copy.deepcopy(self.baseline)
        self.en.entries[0].source_hash = 1000
        self.en.entries[1].source_hash = 1001
        updated, changes = accept_source_identities(self.desired, self.en, self.baseline, ['Content\ta'])
        self.assertEqual(self.baseline, before)
        self.assertEqual(updated['resources']['ShooterGame']['Content\tb'], before['resources']['ShooterGame']['Content\tb'])
        self.assertEqual(updated['resources']['ShooterGame']['Content\ta']['source_hash'], 1000)
        self.assertEqual(changes, [{'full_key': 'Content\ta', 'old': before['resources']['ShooterGame']['Content\ta'],
                                    'new': identity_of(self.en.entries[0])}])

    def test_explicit_accept_can_add_identity_for_new_desired_key(self):
        del self.baseline['resources']['ShooterGame']['Content\ta']
        updated, changes = accept_source_identities(self.desired, self.en, self.baseline, ['Content\ta'])
        self.assertIsNone(changes[0]['old'])
        self.assertEqual(updated['resources']['ShooterGame']['Content\ta'], identity_of(self.en.entries[0]))

    def test_explicit_accept_rejects_empty_unknown_or_missing_english_keys(self):
        for keys, en in (([], self.en), (['Content\tunknown'], self.en),
                         (['Content\tb'], resource({'a': 'Alpha'}))):
            with self.subTest(keys=keys), self.assertRaises(TranslationDataError):
                accept_source_identities(self.desired, en, self.baseline, keys)

    def test_accept_cli_dry_run_then_apply_changes_only_named_identity(self):
        from tools.translation_data import main
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            desired_path = root / 'data/shootergame_ru.json'
            desired_path.write_text(json.dumps(self.desired), encoding='utf-8')
            baseline_path = root / 'data/source_identity.json'
            baseline_path.write_text(json.dumps(self.baseline), encoding='utf-8')
            self.en.entries[0].source_hash += 1
            self.en.entries[1].source_hash += 1
            stock_path = root / 'stock.locres'
            stock_path.write_bytes(serialize(self.en, {}))
            arguments = ['translation_data', 'accept-source', '--resource', 'ShooterGame',
                         '--stock-en', str(stock_path), '--key', 'Content\ta']
            before = baseline_path.read_bytes()
            with patch('tools.translation_data.ROOT', root), patch('sys.argv', arguments):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(), 0)
                self.assertEqual(baseline_path.read_bytes(), before)
                report = json.loads(output.getvalue())
                self.assertEqual([item['full_key'] for item in report['identities']], ['Content\ta'])
                self.assertNotIn('Alpha', output.getvalue())
                self.assertNotIn('Альфа', output.getvalue())
            with patch('tools.translation_data.ROOT', root), patch('sys.argv', arguments + ['--apply']):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(), 0)
            updated = json.loads(baseline_path.read_text(encoding='utf-8'))
            self.assertEqual(updated['resources']['ShooterGame']['Content\tb'],
                             self.baseline['resources']['ShooterGame']['Content\tb'])
            self.assertEqual(updated['resources']['ShooterGame']['Content\ta'], identity_of(self.en.entries[0]))
            self.assertEqual(load_edits(desired_path), self.desired)
            self.assertEqual(baseline_path.read_text(encoding='utf-8'),
                             json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + '\n')

    def test_candidate_cli_accepts_en_only_but_does_not_accept_source_identity(self):
        from tools.corrections import main
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            stock_root = root / 'work/source/ShooterGame/Content/Localization/ShooterGame'
            for language, res in (('en', self.en), ('ru', resource({'a': 'Старая строка'}))):
                (stock_root / language).mkdir(parents=True)
                (stock_root / language / 'ShooterGame.locres').write_bytes(serialize(res, {}))
            desired_path = root / 'data/shootergame_ru.json'
            desired_path.write_text(json.dumps({'Content\ta': 'Альфа'}), encoding='utf-8')
            baseline_path = root / 'data/source_identity.json'
            del self.baseline['resources']['ShooterGame']['Content\tb']
            baseline_path.write_text(json.dumps(self.baseline), encoding='utf-8')
            candidate_path = root / 'candidate.json'
            candidate_path.write_text(json.dumps({'Content\tb': 'Бета'}), encoding='utf-8')
            before = baseline_path.read_bytes()
            with patch('tools.corrections.ROOT', root), patch('sys.argv',
                    ['corrections', '--candidate', str(candidate_path), '--apply']):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report['new_count'], 1)
            self.assertEqual(report['pending_source_acceptance'], ['Content\tb'])
            self.assertEqual(load_edits(desired_path), self.desired)
            self.assertEqual(baseline_path.read_bytes(), before)
            with self.assertRaises(TranslationDataError):
                classify_desired(load_edits(desired_path), self.en, resource({}), self.baseline)


if __name__ == '__main__':
    unittest.main()
