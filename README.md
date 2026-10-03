# ASA RU Fix

Исправления русской локализации ARK: Survival Ascended для Steam на Windows x64. Клиент `ASA-RU-Fix.exe` устанавливает готовый перевод и проверяет обновления перед обычным запуском игры через Steam.

## Для игроков

1. Скачать [ASA-RU-Fix.exe](https://github.com/andreymukha/ASA-RU-Fix/releases/download/updater-v1.0.0/ASA-RU-Fix.exe).
2. Запустить.
3. Нажать «Установить».
4. Дальше запускать ARK через Steam как обычно.

Поддерживается Steam-версия ARK: Survival Ascended на Windows x64. Python, Git, отдельный .NET Runtime и GitHub account не нужны. Updater устанавливается для текущего пользователя в `%LOCALAPPDATA%\ASA-RU-Fix\ASA-RU-Fix.exe`; скачанный файл после установки можно удалить самостоятельно. Когда потребуется настроить Steam, программа предложит его перезапуск. При запущенной ARK сначала закройте игру.

Исходные Steam Launch Options сохраняются. Updater проверяет готовый PAK из GitHub и обновляет собственный EXE; ошибка сети или обновления позволяет запустить игру с имеющимся переводом. Telemetry, Windows service, scheduled task и автозапуск Windows отсутствуют. Для удаления используйте «Удалить» в программе или Windows Installed Apps.

EXE **не подписан**: при первом запуске Windows может показать SmartScreen warning. Программа не устанавливает доверенные сертификаты и не меняет настройки защиты Windows. Подробности установки, восстановления и удаления — в [документации клиента](docs/client-updater.md). Результаты реальных Actions, публичного скачивания и диагностики Release EXE приведены в [отчёте проверки клиента](docs/client-updater-verification.md).

## Для разработчиков

Серверная сборка получает официальные EN/RU LOCRES из Steam Dedicated Server, применяет проверенные переводы к полным RU-ресурсам и создаёт `dist/ASA_RU_Fix_P.pak`. Клиент загружает уже готовый PAK: server depot, repak, ooz и DevKit на компьютере игрока не используются. Официальные тексты, загруженные инструменты и созданные бинарные файлы не хранятся в Git.

Исходники клиента находятся в `client/`; сборка использует закреплённый .NET 10 LTS SDK `10.0.401` и runtime `10.0.12`. Команды сборки, fixture tests и manual workflow описаны в [docs/client-updater.md](docs/client-updater.md#сборка-и-публикация). Python/PowerShell/VBS инструменты проекта предназначены для разработки и серверной сборки. Исторический снимок `E:\Projects\ARK Survival\ASA-RU-Fix-legacy-v1` сохранён отдельно.

## Сборка

Нужны Windows x64, 64-битный Python 3.12 и доступ в интернет. Для первой компиляции ooz требуются Visual Studio 2022 Build Tools, компонент Desktop development with C++, MSVC x64 и Windows SDK. Проверенный кэш DLL позволяет выполнять последующие сборки без компилятора.

```powershell
python tools/bootstrap.py
python build.py --profile pinned
# То же самое: pinned — профиль по умолчанию.
python build.py
```

`pinned` использует manifest `3251368963427721326` приложения `2430930`, depot `2430931`. Сборка загружает только `ShooterGame/Content/Paks/pakchunk0-WindowsServer.pak`, проверяет размер, SHA-256, версию и количество ключей четырёх stock LOCRES, затем сверяет итоговый PAK с закреплённым эталоном.

Для текущей публичной версии сначала получите точный manifest:

```powershell
python tools/bootstrap.py --probe-only
python -m tools.manifest_probe --output work/manifest-probe.json
python tools/bootstrap.py
# Подставьте manifest_id из полученного JSON.
python build.py --profile live --manifest ID
```

`--probe-only` готовит только DepotDownloader. Probe получает метаданные manifest без файлов depot и без PAK. Полный bootstrap нужен при переходе к сборке. Профиль `live` проверяет структуру текущих ресурсов, формат переводов и сохранность принятых EN-identity; размер и общий SHA-256 ресурсов могут отличаться от pinned. Его результат не обязан совпадать с pinned PAK.

Для повторной локальной проверки доступны `--source server-pak --server-pak PATH` и явный `--output PATH`. `--source installed-game --game-path PATH` оставлен для разработки. Команды, параметры облачных workflow и ограничения расписания приведены в [docs/cloud-build.md](docs/cloud-build.md). Фактические результаты проверок записываются в [TESTING.md](TESTING.md) и [V1_CANDIDATE.md](V1_CANDIDATE.md); описание процесса не заменяет подтверждённый запуск.

## Данные перевода и защита исходных строк

`data/shootergame_ru.json` — единственный набор желаемых ShooterGame-переводов: JSON `namespace\tkey` → русский текст. Он содержит точное объединение прежних 1200 corrections и 43 additions, всего **1243 уникальных ключа**, с сохранением текстов. `data/engine_ru.json` сохраняет **21** подтверждённый перевод `InputKeys`. Отдельные файлы corrections/additions удалены.

Классификация выполняется для текущего stock RU: отсутствующий ключ становится добавлением; существующий с другим текстом — исправлением; совпадающий с желаемым текстом — `already_correct`. На pinned manifest получаются:

| Ресурс | Исправления | Добавления | Уже правильные | Всего желаемых |
| --- | ---: | ---: | ---: | ---: |
| ShooterGame | 1199 | 43 | 1 | 1243 |
| Engine | 16 | 1 | 4 | 21 |

Эти значения отличаются от исторического количества записанных правок: одна ShooterGame-строка и четыре Engine-строки уже совпадают со stock RU. Это не потеря переводов. В `live` доли категорий могут меняться, а все желаемые строки проверяются после сборки и извлечения из PAK.

`data/source_identity.json` имеет schema `1`, исходный `manifest_id` и карты ресурсов `ShooterGame`/`Engine`. Для каждого желаемого ключа сохранены три числовых поля: `namespace_hash`, `key_hash`, `source_hash`. Официальные EN-тексты в baseline не записываются. Исчезновение нужного EN-ключа, отсутствие принятой identity или изменение любого из трёх хэшей останавливает сборку. Изменения посторонних EN-ключей разрешены.

Перед переводом проверяются непустые ключи и значения, точные плейсхолдеры, printf и RichText. При добавлении ключа используются его EN-хэши и положение в исходном EN-ресурсе. Для уже существующих RU-ключей сохраняется stock RU `source_hash`: автоматической синхронизации с EN нет.

Изменение EN-identity принимается только для явно названных желаемых ключей. Сначала просмотрите вывод без `--apply`, затем повторите команду с `--apply`, если новая исходная строка проверена:

```powershell
python -m tools.translation_data accept-source --resource ShooterGame --stock-en work/source/ShooterGame/Content/Localization/ShooterGame/en/ShooterGame.locres --key "Content`t3027221575"
# Добавьте --apply после проверки old/new хэшей.
```

В PowerShell `` `t `` обозначает настоящий TAB внутри ключа. `--key` повторяется для каждого проверенного ключа; массового принятия всех identity нет. Для Engine используйте `--resource Engine` и соответствующий stock EN LOCRES. Команда показывает old/new хэши и меняет только названные записи baseline.

Проверенные кандидаты импортируются существующим CLI:

```powershell
python -m tools.corrections --candidate PATH_TO_REVIEWED.json
# --expected-new N и --expected-total N позволяют проверить размер импорта.
# --apply записывает объединённый data/shootergame_ru.json.
```

Кандидат может содержать EN-only ключ. Новый желаемый ключ требует отдельного `accept-source`: импорт не принимает identity автоматически, а выводит `pending_source_acceptance`. До принятия таких ключей сборка остановится. Конфликты существующих текстов, дубли JSON-ключей, отсутствие EN, пустые значения и нарушения форматирования отклоняются. Правила русских UI-текстов описаны в [TRANSLATION_STYLE.md](TRANSLATION_STYLE.md); сравнение EN-дампов доступно через `python delta.py OLD_EN.json NEW_EN.json`.

## Облачное обновление

[cloud-build-pinned.yml](.github/workflows/cloud-build-pinned.yml) выполняет ручную проверку закреплённого эталона и сохраняет артефакты. [auto-update.yml](.github/workflows/auto-update.yml) предназначен для проверки текущего публичного manifest и публикации через `gh`: версионный GitHub Release содержит PAK, а ветка `channel` хранит `stable.json` и `automation.json`.

Решение о сборке зависит от пары `(manifest_id, build_fingerprint)`. Уже успешно обработанная пара пропускается. После двух ошибок одной пары дальнейшие автоматические сборки блокируются до изменения входов либо ручного `force_rebuild`. Patch-компонент версии повышается только при изменении байтов PAK; новый manifest с прежним PAK обновляет сведения об успешной обработке без новой версии.

Расписание **`17,47 * * * *` включено** после успешных hosted pinned/live и fast-path проверок. `GITHUB_TOKEN` workflow требует только `contents: write`; группа concurrency `asa-ru-fix-live-update` использует `cancel-in-progress: false`. Подробности публикации, состояния и восстановления приведены в [документации облачного процесса](docs/cloud-build.md#автоматическое-обновление-и-публикация), фактические результаты — в [отчёте проверки](docs/server-automation-verification.md).

Публичный канал перевода: [stable.json](https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/stable.json). Готовый PAK опубликован в [Release v1.0.0](https://github.com/andreymukha/ASA-RU-Fix/releases/tag/v1.0.0). Клиент использует этот manifest для загрузки и проверки PAK; канал самого updater — [client.json](https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/client.json). Версии перевода и updater независимы.

Первый PAK занимает `10795036` bytes. Перед игрой клиент получает небольшие manifest и скачивает PAK только при необходимости. Источник истины — каналы schema `1`, а не GitHub Latest Release.

## Аудит и проверки

После обновления stock-дампов сборкой:

```powershell
python -m tools.audit
python -m unittest discover -s tests -v
python tests/standalone_build.py
```

Аудит читает официальные `work/en.json` и `work/ru.json`. Желаемые тексты из `data/shootergame_ru.json` показываются отдельно в `our_ru`/`already_corrected` и не скрывают ошибки stock RU. `work/ru_rebuilt.json` не используется. CSV имеют UTF-8 BOM и корректное экранирование; отчёты `audit/` игнорируются Git. Механические фильтры не оценивают смысл и качество перевода и не редактируют данные.

Standalone-проверка использует уже загруженный server PAK и ограничивает файловые, DLL- и process-зависимости; допускается только кэшированный repak. Для другого расположения кэша задайте `ASA_TEST_SERVER_PAK`. Историческая `tests/compare_devkit.py --unrealpak PATH` — дополнительная проверка разработчика, не зависимость production.

## Формат ресурсов, кэш и ограничения

Читатель поддерживает незашифрованный PAK V12, compact entries и None/Oodle. Он проверяет footer/index SHA-1, точные пути, локальные заголовки, диапазоны и блоки сжатия. Метаданные и каждый извлекаемый ресурс ограничены 64 MiB. Неизвестные версии, шифрование, неизвестное сжатие и повреждённые данные отклоняются. ooz загружается один раз через ctypes; проприетарная Oodle DLL не нужна. Upstream ooz не рассчитан на враждебные входные потоки; используйте доверенный официальный контент.

repak v0.2.3 создаёт V11 с mount `../../../`. Пакет содержит только два русских LOCRES; проверяются `info`, `list`, `unpack`, байты повторно извлечённых файлов и каждый желаемый перевод. Отчёт сборки находится в игнорируемом `work/build_validation.json`.

Инструменты, исходники и лицензии хранятся в `work/tools/`. Архивы repak/DepotDownloader и исходники ooz закреплены SHA-256. Bootstrap повторно использует проверенный кэш, восстанавливает файлы из архивов и принимает DLL только при совпадении recipe и записанного хэша. Для пересборки ooz удалите его `work/tools/ooz/build.json`.

Английские UI-случаи `WEIGHT` и `Crafting Requirements` остаются известными ограничениями: исследование не подтвердило отдельную orphan identity, которую можно безопасно добавить. Производственная сборка не создаёт предполагаемые ключи. Переводы модов исключены из текущей области; исследовательские инструменты и игровые assets остаются в игнорируемом `work/`.

## Ручная установка и удаление для разработчика

Для отдельной проверки PAK сначала выполните `./install.ps1 -WhatIf`, затем `./install.ps1`. Скрипт копирует только `ASA_RU_Fix_P.pak`. Для удаления используйте `./uninstall.ps1 -WhatIf`, затем `./uninstall.ps1`; удаляется только этот PAK. Эти скрипты не устанавливают клиент и его Steam wrapper. Обычная инструкция игрока приведена в начале README. Совместимость с сервером и anti-cheat не устанавливается одной проверкой кнопки «Назад».

## Сторонние компоненты

- [repak](https://github.com/trumank/repak), v0.2.3, **MIT OR Apache-2.0**: проверенный Windows x64 архив, запись и проверка патча.
- [DepotDownloader](https://github.com/SteamRE/DepotDownloader), v3.4.0, **GPL-2.0**: анонимный доступ к manifest и выбранному server PAK; архив и лицензия остаются в кэше.
- [powzix/ooz](https://github.com/powzix/ooz/tree/05038060aa68f9187ae9923b2388ca8db40e58d1), commit `05038060aa68f9187ae9923b2388ca8db40e58d1`, **GPL-3.0-or-later**: локально компилируемый декодер и GPL C ABI bridge. При отдельном распространении производного ooz сохраняйте соответствующие исходники, уведомления и лицензию.
- [TradFR](https://github.com/valentin-gosselin/ark-ascended-fr) изучался как технический пример формата. На исследованном commit явная лицензия проекта не найдена; исходники не копировались дословно.

Происхождение, лицензии и детали компиляции описаны в [THIRD_PARTY.md](THIRD_PARTY.md).
