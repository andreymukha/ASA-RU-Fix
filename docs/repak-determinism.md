# Детерминированная упаковка repak 0.2.3

`repak pack` сортирует пути, но готовит записи параллельно и записывает их
в порядке поступления из канала. Поэтому одинаковые LOCRES могут дать разный
физический порядок и SHA-256 PAK.
[Закреплённый исходный код](https://github.com/trumank/repak/blob/v0.2.3/repak_cli/src/main.rs#L477).

После `repak pack`, перед существующими проверками:

```python
from tools.pak_order import canonicalize_pak

canonicalize_pak(dist, [INTERNAL, ENGINE_INTERNAL])
```

Порядок эталона: ShooterGame, затем Engine. Функция принимает только два
точных относительных LOCRES-пути, V11, mount `../../../`, seed 0,
незашифрованные данные без сжатия и 32-битные компактные записи.
Она проверяет SHA-1 всех индексов и данных, локальные заголовки,
точные lookup-индексы, непрерывность блоков и границы файла.

Переставляются целые блоки заголовок+данные. Меняются компактные смещения
и SHA-1 главного индекса в footer. Порядок компактных записей остаётся
лексикографическим, поэтому PHI/FDI не меняются. Результат повторно проверяется
перед атомарной заменой; ошибочный вход сохраняется.
[Компактные записи](https://github.com/trumank/repak/blob/v0.2.3/repak/src/entry.rs#L256),
[индексы и хеши](https://github.com/trumank/repak/blob/v0.2.3/repak/src/pak.rs#L493),
[footer](https://github.com/trumank/repak/blob/v0.2.3/repak/src/footer.rs#L82).

Проверка на временных копиях реальных PAK восстановила полное совпадение
с облачным эталоном: 10 795 036 байт,
SHA-256 `914589668aa41516915a68ef233873f4aeeedf570db70a7232e36ff9e8c04f2b`.
`repak info`, `list`, `unpack` успешно выполнены; оба извлечённых LOCRES
побайтно совпали. Эталонная раскладка также идемпотентна.

```powershell
python -m unittest discover -s tests -p test_pak_order.py -v
```
