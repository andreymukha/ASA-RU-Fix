import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.locres import Entry, FString, Resource, LocresError, insert_missing, parse, serialize, load_edits
from build import build_resource, verify_package, INTERNAL, ENGINE_INTERNAL


def resource(keys, namespace='Content'):
    return Resource(3, [Entry(17, FString(namespace, False), i + 100,
                             FString(key, False), i + 200, i)
                        for i, key in enumerate(keys)],
                    [FString(key, False) for key in keys], [1] * len(keys))


class LocalizationBuildTests(unittest.TestCase):
    def test_native_order_hashes_and_only_requested_keys(self):
        en, ru = resource(['a', 'b', 'c', 'd']), resource(['a', 'd'])
        built = insert_missing(ru, en, {'Content\tb': 'Б'})
        self.assertEqual([e.key.value for e in built.entries], ['a', 'b', 'd'])
        entry = built.entries[1]
        self.assertEqual((entry.namespace_hash, entry.namespace, entry.key_hash,
                          entry.key, entry.source_hash),
                         (en.entries[1].namespace_hash, en.entries[1].namespace,
                          en.entries[1].key_hash, en.entries[1].key, en.entries[1].source_hash))
        self.assertEqual(ru.as_dict(), {'Content\ta': 'a', 'Content\td': 'd'})
        self.assertEqual(parse(serialize(built, {})).as_dict(),
                         {'Content\ta': 'a', 'Content\tb': 'Б', 'Content\td': 'd'})

    def test_existing_or_unknown_addition_rejected(self):
        for key in ('Content\ta', 'Content\tunknown'):
            with self.subTest(key=key), self.assertRaises(LocresError):
                insert_missing(resource(['a']), resource(['a', 'b']), {key: 'Б'})

    def test_incompatible_stock_order_rejected(self):
        with self.assertRaises(LocresError):
            insert_missing(resource(['c', 'a']), resource(['a', 'b', 'c']), {'Content\tb': 'Б'})

    def test_new_namespace_uses_en_position(self):
        en, ru = resource(['a'], 'First'), resource(['a'], 'Last')
        en.entries += ru.entries
        en.entries[1] = Entry(17, FString('Last', False), 100, FString('a', False), 200, 0)
        built = insert_missing(ru, en, {'First\ta': 'А'})
        self.assertEqual([e.namespace.value for e in built.entries], ['First', 'Last'])

    def test_corrections_coexist_with_additions(self):
        data, report = build_resource(resource(['a', 'b', 'c']), resource(['a', 'c']),
                                      {'Content\ta': 'А'}, {'Content\tb': 'Б'})
        self.assertEqual(parse(data).as_dict(), {'Content\ta': 'А', 'Content\tb': 'Б', 'Content\tc': 'c'})
        self.assertEqual(report['additions_verification']['actual'], 1)

    def test_engine_existing_and_missing_key_build(self):
        data, report = build_resource(resource(['SpaceBar', 'Insert'], 'InputKeys'),
                                      resource(['SpaceBar'], 'InputKeys'),
                                      {'InputKeys\tSpaceBar': 'Пробел'}, {'InputKeys\tInsert': 'Insert'})
        self.assertEqual(parse(data).as_dict(), {'InputKeys\tSpaceBar': 'Пробел', 'InputKeys\tInsert': 'Insert'})

    def test_correction_does_not_automatically_sync_stock_source_hash(self):
        en, ru = resource(['WEIGHT']), resource(['WEIGHT'])
        en.entries[0].source_hash = 0xDCF5EF20
        ru.entries[0].source_hash = 123
        data, _ = build_resource(en, ru, {'Content\tWEIGHT': 'ВЕС'}, {})
        actual = parse(data)
        self.assertEqual(actual.entries[0].source_hash, 123)
        self.assertEqual(actual.as_dict()['Content\tWEIGHT'], 'ВЕС')

    def test_all_edits_checked_after_package_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            expected = {INTERNAL: serialize(resource(['a']), {'Content\ta': 'А'}),
                        ENGINE_INTERNAL: serialize(resource(['SpaceBar'], 'InputKeys'), {'InputKeys\tSpaceBar': 'Пробел'})}
            edits = {INTERNAL: {'Content\ta': 'А'}, ENGINE_INTERNAL: {'InputKeys\tSpaceBar': 'Пробел'}}
            def repak(exe, command, *args):
                if command == 'list':
                    return '\n'.join(reversed(list(expected)))
                if command == 'info':
                    return 'mount point: ../../../\nversion: V11'
                for name, data in expected.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                return ''
            with patch('build.run_repak', side_effect=repak):
                result = verify_package(Path('repak'), Path('patch.pak'), root, expected, edits)
            self.assertEqual(len(result['files']), 2)
            self.assertEqual(result['edits'][INTERNAL]['mismatches'], 0)

    def test_unexpected_package_file_fails(self):
        with patch('build.run_repak', return_value='Unexpected/file'):
            with self.assertRaises(RuntimeError):
                verify_package(Path('repak'), Path('patch.pak'), Path('unused'), {INTERNAL: b''}, {INTERNAL: {}})

    def test_post_package_wrong_expected_edit_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = serialize(resource(['a']), {})
            def repak(exe, command, *args):
                if command == 'list':
                    return INTERNAL
                if command == 'info':
                    return 'mount point: ../../../\nversion: V11'
                path = root / INTERNAL
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return ''
            with patch('build.run_repak', side_effect=repak), self.assertRaises(LocresError):
                verify_package(Path('repak'), Path('patch.pak'), root,
                               {INTERNAL: data}, {INTERNAL: {'Content\ta': 'Wrong'}})

    def test_reviewed_screenshot_regressions(self):
        edits = load_edits(Path(__file__).resolve().parents[1] / 'data/corrections.json')
        expected = {'Content\t1408111756': 'Назад',
                    'GraphLiteral\t1014074791': 'Цвет прицела на союзнике',
                    'GraphLiteral\t3145492015': 'Цвет прицела на враге',
                    'Content\t2831581971': 'Седло для Кархародонтозавра',
                    'Content\t2631035315': 'Тек-грядка',
                    'Content\t3789992885': 'Седло для И Линга',
                    'Content\t2281052626': 'Заряженный',
                    'GraphLiteral\t2281052626': 'Заряженный',
                    'Content\t3027221575': 'Кожаная шапка',
                    'Globals\t3027221575': 'Кожаная шапка',
                    'Content\t3927745900': 'Тек-рама для ворот'}
        expected['GraphLiteral\t3707105056'] = 'ВЕС'
        expected.update({'Content\t2879543335': 'Седло для Кархародонтозавра',
                         'Content\t2232173803': 'Седло для Берроубака',
                         'Content\t2318685006': 'Парниковая крыша: треугольник и угол',
                         'Content\t2672943785': 'Стол для доработки',
                         'Content\t4053904995': 'Усилитель скорости компаньона',
                         'GraphLiteral\t397870435': 'Показать эффекты'})
        self.assertEqual(len(edits), 1167)
        self.assertEqual({key: edits[key] for key in expected}, expected)
        self.assertNotIn('GraphLiteral\t63761803', edits)
        self.assertFalse(any('RU FIX TEST' in value for value in edits.values()))
        additions = load_edits(Path(__file__).resolve().parents[1] / 'data/additions.json')
        self.assertEqual(len(additions), 43)
        self.assertEqual(additions['GraphLiteral\t1863176983'], ', ВЕТЕР:')
        self.assertEqual(additions['GraphLiteral\t3285020872'], 'КАРТЫ ИЗ МОДОВ')


if __name__ == '__main__':
    unittest.main()
