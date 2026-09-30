import json
import tempfile
import unittest
from pathlib import Path

from tools.corrections import CorrectionError, merge_candidates, placeholders, validate_corrections, verify_applied
from tools.locres import LocresError, load_edits


class CorrectionTests(unittest.TestCase):
    def test_merge_keeps_existing_and_accepts_identical_duplicate(self):
        en = {'Content\tback': 'back', 'Content\tsave': 'Save'}
        ru = {'Content\tback': 'спина', 'Content\tsave': 'Сохранить'}
        merged, report = merge_candidates({'Content\tsave': 'Сохранить игру', 'Content\tback': 'Назад'},
                                           {'Content\tback': 'Назад'}, en, ru)
        self.assertEqual(merged, {'Content\tback': 'Назад', 'Content\tsave': 'Сохранить игру'})
        self.assertEqual(report['new_count'], 1)
        self.assertEqual(report['identical_duplicates'], 1)

    def test_conflict_fails_and_does_not_mutate_existing(self):
        existing = {'n\t1': 'Назад'}
        with self.assertRaisesRegex(CorrectionError, 'conflict'):
            merge_candidates({'n\t1': 'Другой текст'}, existing, {'n\t1': 'Back'}, {'n\t1': 'спина'})
        self.assertEqual(existing, {'n\t1': 'Назад'})

    def test_missing_key_and_malformed_identity_fail(self):
        for key in ('n\tmissing', 'no separator', 'n\t1\t2', '\t1'):
            with self.subTest(key=key), self.assertRaises(CorrectionError):
                validate_corrections({key: 'Текст'}, {'n\t1': 'Text'}, {'n\t1': 'Текст'})
        with self.assertRaises(CorrectionError):
            validate_corrections({'n\t1': 'Текст'}, {}, {'n\t1': 'Текст'})

    def test_empty_or_nonstring_replacement_fails(self):
        for value in ('', '  ', None, 1):
            with self.subTest(value=value), self.assertRaises(CorrectionError):
                validate_corrections({'n\t1': value}, {'n\t1': 'Text'}, {'n\t1': 'Текст'})

    def test_named_space_and_positional_placeholders_preserved_with_counts(self):
        en = '{0} {1} {Name} {Some Value} {Name} %s %d %i %.1f %%'
        ru = '{Name} {0} {Some Value} {Name} {1} %s %d %i %.1f %%'
        validate_corrections({'n\t1': ru}, {'n\t1': en}, {'n\t1': ''})
        self.assertEqual(placeholders(en), placeholders(ru))
        for replacement in ('{Враг}', '{Enemy} {Enemy}', '{enemy}'):
            with self.subTest(replacement=replacement), self.assertRaises(CorrectionError):
                validate_corrections({'n\t1': replacement}, {'n\t1': '{Enemy}'}, {'n\t1': ''})

    def test_printf_cyrillic_conversion_and_precision_loss_fail(self):
        for source, target in (('%s', '%с'), ('%.1f', '%f'), ('%d', '%i'), ('%1$s', '%s')):
            with self.subTest(source=source), self.assertRaises(CorrectionError):
                validate_corrections({'n\t1': target}, {'n\t1': source}, {'n\t1': ''})

    def test_literal_percent_and_decorative_angles_are_not_tokens(self):
        self.assertFalse(placeholders('10% food 5% faster 50% health 100%%'))
        validate_corrections({'n\t1': '<<НАЗВАНИЕ>>'}, {'n\t1': '<<TITLE>>'}, {'n\t1': ''})

    def test_printf_token_can_touch_following_text(self):
        self.assertEqual(placeholders('%sName')['printf:%s'], 1)
        self.assertFalse(placeholders('{{Name}}'))

    def test_richtext_nested_anonymous_closes_and_void_tags(self):
        source = '<RichColor Color="red"><b>Text</b></><br><img src="image"/>'
        target = '<RichColor Color="red"><b>Текст</b></><br><img src="image"/>'
        validate_corrections({'n\t1': target}, {'n\t1': source}, {'n\t1': ''})

    def test_missing_close_wrong_close_or_attribute_loss_fails(self):
        source = '<RichColor Color="red">Text</>'
        for target in ('<RichColor Color="red">Текст', '<RichColor Color="red">Текст</b>', '<RichColor>Текст</>'):
            with self.subTest(target=target), self.assertRaises(CorrectionError):
                validate_corrections({'n\t1': target}, {'n\t1': source}, {'n\t1': ''})

    def test_source_richtext_fragment_preserves_its_boundary_contract(self):
        report = validate_corrections({'n\t1': '{color} ( {0} из {1} )</>'},
                                      {'n\t1': '{color} ( {0} of {1} )</>'}, {'n\t1': ''})
        self.assertEqual(report['source_markup_fragments'], 1)
        with self.assertRaises(CorrectionError):
            validate_corrections({'n\t1': '{color} ( {0} из {1} )'},
                                 {'n\t1': '{color} ( {0} of {1} )</>'}, {'n\t1': ''})

    def test_all_corrections_verified_and_missing_value_fails(self):
        corrections = {'n\t1': 'Один', 'n\t2': 'Два'}
        self.assertEqual(verify_applied(corrections, {**corrections, 'n\t3': 'Три'}),
                         {'expected': 2, 'actual': 2, 'mismatches': 0})
        with self.assertRaisesRegex(CorrectionError, 'n\\\\t2'):
            verify_applied(corrections, {'n\t1': 'Один', 'n\t2': 'Ошибка'})

    def test_duplicate_json_keys_fail_instead_of_silent_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'edits.json'
            path.write_text('{"n\\t1": "first", "n\\t1": "second"}', encoding='utf-8')
            with self.assertRaises(LocresError):
                load_edits(path)


if __name__ == '__main__':
    unittest.main()
