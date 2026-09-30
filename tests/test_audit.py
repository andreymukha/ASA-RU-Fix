import csv
import io
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tools.audit import FLAGS, analyze, consistency_reports, run_audit


class AuditLogicTests(unittest.TestCase):
    def rows(self, en, ru, corrections=None, terms=None):
        return analyze(en, ru, corrections or {}, terms or [])

    def test_exact_key_union_missing_directions(self):
        rows = self.rows({'n\tEnglish only': 'A'}, {'n\tРусский only': 'Б'})
        self.assertEqual(len(rows), 2)
        by_key = {row['key']: row for row in rows}
        self.assertEqual(by_key['English only']['flags'], 'MISSING_RU')
        self.assertEqual(by_key['Русский only']['flags'], 'MISSING_EN')

    def test_unicode_csv_quotes_commas_semicolons_and_multiline(self):
        text = 'строка, «кавычки»; <RichText>\nвторая строка'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rows.csv'
            from tools.audit import write_csv
            write_csv(path, [{'key': 'ключ', 'ru': text}], ['key', 'ru'])
            content = path.read_bytes()
            self.assertTrue(content.startswith(b'\xef\xbb\xbf'))
            result = next(csv.DictReader(io.StringIO(content.decode('utf-8-sig'), newline='')))
            self.assertEqual(result, {'key': 'ключ', 'ru': text})

    def test_placeholder_counts_and_escaped_percent(self):
        rows = self.rows({'n\ta': 'Deal %s with {Name} {0} %.2f 100%%'},
                         {'n\ta': 'Нанести %s урон {Name} {0} %%'})
        self.assertTrue(rows[0]['placeholder_mismatch'])
        same = self.rows({'n\ta': 'Deal %1$s and {Name:format}'},
                         {'n\ta': 'Урон %1$s и {Name}'})
        self.assertFalse(same[0]['placeholder_mismatch'])

    def test_printf_conversion_and_brace_placeholder_forms(self):
        en = 'Deal %d %f %1$s %(player)s {0} {1} {Something} {Something:format} 100%%'
        ru = 'Урон %d %f %1$s %(player)s {0} {1} {Something} {Something} %%'
        self.assertFalse(self.rows({'n\ta': en}, {'n\ta': ru})[0]['placeholder_mismatch'])
        self.assertTrue(self.rows({'n\ta': 'Deal %d'}, {'n\ta': 'Урон %s'})[0]['placeholder_mismatch'])

    def test_tag_mismatch(self):
        rows = self.rows({'n\ta': '<RichColor Color="red">Hello</>'},
                         {'n\ta': 'Привет'})
        self.assertTrue(rows[0]['tag_mismatch'])
        attr = self.rows({'n\ta': '<RichColor Color="red">Hello</>'},
                         {'n\ta': '<RichColor>Привет</>'})
        self.assertTrue(attr[0]['tag_mismatch'])

    def test_double_angle_tokens_are_not_markup(self):
        row = self.rows({'n\ta': '<<TITLE>>'}, {'n\ta': '<<TITLE>>'})[0]
        self.assertFalse(row['tag_mismatch'])

    def test_unreal_rich_text_tags_are_markup(self):
        rows = self.rows({'n\ta': '<RichColor Color="red">Hello</>'},
                         {'n\ta': '<RichColor Color="red">Привет</>'})
        self.assertFalse(rows[0]['tag_mismatch'])
        self.assertTrue(self.rows({'n\ta': '<RichColor Color="red">Hello</>'},
                                  {'n\ta': 'Привет'})[0]['tag_mismatch'])

    def test_same_english_multiple_russian(self):
        rows = self.rows({'a\t1': 'Back', 'b\t2': 'Back'},
                         {'a\t1': 'Назад', 'b\t2': 'Спина'})
        self.assertTrue(all(row['same_en_multiple_ru'] for row in rows))
        en_groups, _ = consistency_reports(rows)
        self.assertEqual(en_groups[0]['distinct_ru_count'], 2)
        self.assertNotIn('same_en_other_ru', rows[0])

    def test_same_russian_multiple_english(self):
        rows = self.rows({'a\t1': 'Back', 'b\t2': 'spine'},
                         {'a\t1': 'спина', 'b\t2': 'спина'})
        self.assertTrue(all(row['same_ru_multiple_en'] for row in rows))
        _, ru_groups = consistency_reports(rows)
        self.assertEqual(ru_groups[0]['distinct_en_count'], 2)
        self.assertNotIn('same_ru_other_en', rows[0])

    def test_missing_russian_values_do_not_group_as_shared_translation(self):
        rows = self.rows({'a\t1': 'Save', 'b\t2': 'Load', 'c\t3': 'Back'},
                         {'a\t1': '', 'b\t2': '  ', 'c\t3': 'Назад'})
        missing = [row for row in rows if row['missing_ru']]
        self.assertEqual(len(missing), 2)
        self.assertTrue(all(not row['same_ru_multiple_en'] for row in missing))
        self.assertTrue(all('same_ru_other_en' not in row for row in missing))

    def test_empty_english_does_not_form_same_english_group(self):
        rows = self.rows({'a\t1': '', 'b\t2': ''},
                         {'a\t1': 'Строка А', 'b\t2': 'Строка Б'})
        self.assertTrue(all(not row['same_en_multiple_ru'] for row in rows))
        self.assertTrue(all('same_en_other_ru' not in row for row in rows))
        self.assertTrue(all(row['missing_en'] for row in rows))

    def test_consistency_reports_group_once_and_skip_empty_values(self):
        rows = self.rows({'a\t1': 'Back', 'b\t2': 'Back', 'c\t3': 'Save',
                          'd\t4': '', 'e\t5': ''},
                         {'a\t1': 'Назад', 'b\t2': 'Спина', 'c\t3': '',
                          'd\t4': 'Один', 'e\t5': 'Два'})
        en_groups, ru_groups = consistency_reports(rows)
        self.assertEqual(len(en_groups), 1)
        self.assertEqual(en_groups[0]['en'], 'Back')
        self.assertEqual(en_groups[0]['occurrences'], 2)
        self.assertEqual(en_groups[0]['distinct_ru_count'], 2)
        self.assertEqual(len(ru_groups), 0)

    def test_consistency_variant_preview_is_capped_but_count_is_complete(self):
        en = {f'n\t{i}': 'Same' for i in range(25)}
        ru = {f'n\t{i}': f'Вариант {i}' for i in range(25)}
        en_groups, _ = consistency_reports(self.rows(en, ru))
        self.assertEqual(en_groups[0]['distinct_ru_count'], 25)
        self.assertEqual(len(json.loads(en_groups[0]['ru_variants'])), 20)

    def test_consistency_only_flag_does_not_make_suspicious(self):
        rows = self.rows({'a\t1': 'Back', 'b\t2': 'Back'},
                         {'a\t1': 'Назад', 'b\t2': 'Спина'})
        self.assertTrue(all(row['same_en_multiple_ru'] for row in rows))
        self.assertTrue(all(not row['suspicious'] for row in rows))

    def test_technical_identifiers_are_marked_and_filtered_from_suspicious(self):
        rows = self.rows(
            {'n\tpath': '/Game/Genesis2/Sounds/Audio_Cue',
             'n\tidentifier': 'CorruptedMaze_AddPlayers_Title',
             'n\tdebug': '(Hunt_Dino_Lunar_06) ServerSidePoint=123'},
            {'n\tpath': '/Game/Genesis2/Sounds/Audio_Cue',
             'n\tidentifier': 'CorruptedMaze_AddPlayers_Title',
             'n\tdebug': '(Hunt_Dino_Lunar_06) ServerSidePoint=123'})
        self.assertTrue(all(row['technical_likely'] for row in rows))
        self.assertTrue(all(row['untranslated'] for row in rows))
        self.assertTrue(all(not row['suspicious'] for row in rows))

    def test_natural_russian_ui_is_not_technical(self):
        row = self.rows({'n\tback': 'Back'}, {'n\tback': 'Назад'})[0]
        self.assertFalse(row['technical_likely'])

    def test_missing_keys_are_not_suspicious(self):
        rows = self.rows({'n\tmissing': 'Save'}, {})
        self.assertTrue(rows[0]['missing_ru'])
        self.assertFalse(rows[0]['suspicious'])

    def test_known_back_correction_remains_suspicious(self):
        key = 'Content\t1408111756'
        row = self.rows({key: 'back'}, {key: 'спина'}, {key: 'Назад'},
                        [{'full_key': key, 'en': 'back', 'ru': 'спина'}])[0]
        self.assertTrue(row['case_suspicious'])
        self.assertTrue(row['known_bad_term'])
        self.assertTrue(row['suspicious'])

    def test_corrected_key_audits_official_ru_and_exposes_our_ru(self):
        key = 'Content\t1408111756'
        rows = self.rows({key: 'back'}, {key: 'спина'}, {key: 'Назад'},
                         [{'full_key': key, 'en': 'back', 'ru': 'спина'}])
        row = rows[0]
        self.assertEqual(row['ru'], 'спина')
        self.assertTrue(row['already_corrected'])
        self.assertEqual(row['our_ru'], 'Назад')
        self.assertTrue(row['known_bad_term'])
        self.assertTrue(row['case_suspicious'])
        self.assertEqual(row['flags'], 'CASE_SUSPICIOUS;KNOWN_BAD_TERM')

    def test_identical_acronym_and_url_are_low_noise(self):
        rows = self.rows({'n\ta': 'ARK', 'n\tb': 'https://example.com', 'n\tc': '42'},
                         {'n\ta': 'ARK', 'n\tb': 'https://example.com', 'n\tc': '42'})
        self.assertTrue(all(row['untranslated'] for row in rows))
        self.assertFalse(any(row['suspicious'] for row in rows))

    def test_latin_exclusions_for_measurements_versions_names_and_keys(self):
        en = {
            'n\tversion': 'Build v2.7.1', 'n\tunit': 'Weight 5 kg',
            'n\tname': 'DragonTopia', 'InputKeys\tkey': 'ArrowUp',
            'n\tgamepad': 'Gamepad_LeftShoulder',
        }
        ru = {
            'n\tversion': 'Версия build 2.7.1', 'n\tunit': 'Вес 5 kg',
            'n\tname': 'DragonTopia', 'InputKeys\tkey': 'ArrowUp',
            'n\tgamepad': 'Gamepad_leftshoulder',
        }
        self.assertFalse(any(row['latin_in_ru'] for row in self.rows(en, ru)))

    def test_case_rule_sentence_case(self):
        rows = self.rows({'n\ta': 'Create or Resume Game', 'n\tb': 'Settings'},
                         {'n\ta': 'создать или возобновить игру', 'n\tb': 'Настройки'})
        self.assertTrue(rows[0]['case_suspicious'])
        self.assertFalse(rows[1]['case_suspicious'])

    def test_newlines_latin_and_length_diagnostics(self):
        rows = self.rows({'n\ta': 'Short\n\nline', 'n\tb': 'A very long source description ' * 12},
                         {'n\ta': 'Очень длинная english строка и текст\nздесь',
                          'n\tb': 'Очень длинная строка интерфейса'})
        self.assertTrue(rows[0]['newline_mismatch'])
        self.assertTrue(rows[0]['latin_in_ru'])
        self.assertTrue(rows[1]['suspicious_length'])

    def test_known_bad_term_requires_exact_official_values(self):
        key = 'n\tkey'
        terms = [{'full_key': key, 'en': 'back', 'ru': 'спина'}]
        self.assertTrue(self.rows({key: 'back'}, {key: 'спина'}, terms=terms)[0]['known_bad_term'])
        self.assertFalse(self.rows({key: 'back'}, {key: 'поясница'}, terms=terms)[0]['known_bad_term'])

    def test_all_fields_bool_and_flags_are_deterministic(self):
        rows = self.rows({'n\tb': 'Save', 'n\ta': 'Back'},
                         {'n\tb': 'Сохранить', 'n\ta': 'спина'})
        self.assertEqual([r['full_key'] for r in rows], ['n\ta', 'n\tb'])
        self.assertEqual(set(FLAGS).issubset(rows[0]), True)
        self.assertIs(type(rows[0]['missing_ru']), bool)

    def test_run_audit_writes_summary_and_union_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            (root / 'work').mkdir()
            (root / 'data/corrections.json').write_text(json.dumps({'n\ta': 'Назад'}), encoding='utf-8')
            (root / 'data/audit_terms.json').write_text('{"known_bad_terms": []}', encoding='utf-8')
            (root / 'work/en.json').write_text(json.dumps({'n\ta': 'Back', 'n\tb': 'Save'}), encoding='utf-8')
            (root / 'work/ru.json').write_text(json.dumps({'n\ta': 'Спина', 'n\tc': 'Звук'}), encoding='utf-8')
            summary = run_audit(root)
            self.assertEqual((summary['en_key_count'], summary['ru_key_count'], summary['union_key_count']), (2, 2, 3))
            with (root / 'audit/all_strings.csv').open(encoding='utf-8-sig', newline='') as source:
                self.assertEqual(len(list(csv.DictReader(source))), 3)
            with (root / 'audit/missing_ru.csv').open(encoding='utf-8-sig', newline='') as source:
                self.assertEqual(len(list(csv.DictReader(source))), 1)
            with (root / 'audit/missing_en.csv').open(encoding='utf-8-sig', newline='') as source:
                self.assertEqual(len(list(csv.DictReader(source))), 1)
            with (root / 'audit/consistency_en.csv').open(encoding='utf-8-sig', newline='') as source:
                self.assertEqual(list(csv.DictReader(source)), [])
            with (root / 'audit/consistency_ru.csv').open(encoding='utf-8-sig', newline='') as source:
                self.assertEqual(list(csv.DictReader(source)), [])
            with (root / 'audit/suspicious.csv').open(encoding='utf-8-sig', newline='') as source:
                suspicious = list(csv.DictReader(source))
            self.assertTrue(all('same_en_other_ru' not in row for row in suspicious))
            self.assertTrue(all('same_ru_other_en' not in row for row in suspicious))
            self.assertEqual(json.loads((root / 'audit/summary.json').read_text(encoding='utf-8'))['union_key_count'], 3)


if __name__ == '__main__':
    unittest.main()
