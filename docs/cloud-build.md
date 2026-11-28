# Сборка из Steam и облачное обновление

Сборка использует анонимный режим DepotDownloader 3.4.0 для приложения `2430930`, depot `2430931`. При сборке загружается только `ShooterGame/Content/Paks/pakchunk0-WindowsServer.pak`. Клиент ARK, установленная игра и DevKit не требуются. PAK, метаданные Steam и официальные LOCRES сохраняются в игнорируемом `work/`.

## Профили pinned и live

```powershell
python tools/bootstrap.py
python build.py --profile pinned
# pinned используется по умолчанию:
python build.py
```

Профиль `pinned` закреплён за manifest `3251368963427721326`. До перевода он проверяет четыре официальных ресурса по размеру, SHA-256, версии LOCRES 3 и числу ключей:

| Ресурс | Размер, байт | SHA-256 | Ключей |
| --- | ---: | --- | ---: |
| ShooterGame EN | 3 669 617 | `efb6606905da0c3b5883c2472b253db5e22f5cd2e948cb0d1601b565ce41a216` | 39 444 |
| ShooterGame RU | 4 996 378 | `be8b5d46901bc3780be0454dbc9545908cdb35b6cc59cd5dd48315d9887a1d44` | 35 598 |
| Engine EN | 3 909 182 | `c0ae7e3dc9fb0f38ab39064f4556737c7ebf3a7ed8bd3971dd6dd0912ddf2d30` | 48 284 |
| Engine RU | 5 805 962 | `4e9e6bc08b577c947ec67bc1168633916f464d45ce973c8a5f6de54159a9d475` | 45 771 |

Кроме входных ресурсов, pinned проверяет итоговый PAK по закреплённому размеру и SHA-256 и фиксирует ожидаемую классификацию желаемых переводов.

Для нового публичного manifest используется профиль `live` с обязательным точным ID:

```powershell
python tools/bootstrap.py --probe-only
python -m tools.manifest_probe --output work/manifest-probe.json
python tools/bootstrap.py
python build.py --profile live --manifest ID
```

Подставьте `manifest_id` из probe. `live` проверяет четыре точных пути и корректный LOCRES, но не требует прежнего общего SHA-256, размера или количества ключей. Проверки identity желаемых ключей, плейсхолдеров, printf, RichText, порядка и содержимого итогового пакета сохраняются. Изменение официального RU допускается и влияет на динамическую классификацию. Изменение EN-identity нужного перевода требует ручной проверки.

Повторная проверка уже загруженного pinned server PAK не требует Steam-запроса:

```powershell
python build.py --profile pinned --source server-pak --server-pak PATH_TO_SERVER_PAK --output work/cloud-validation/ASA_RU_Fix_P.pak
```

Для локального PAK нового manifest укажите `--profile live --manifest ID`. `--source installed-game --game-path PATH` служит дополнительным источником при разработке. Облачный production использует Steam Dedicated Server.

## Probe без загрузки PAK

`python tools/bootstrap.py --probe-only` готовит только проверенный DepotDownloader. repak, компилятор и ooz в этом пути не запускаются. `tools.manifest_probe` использует `-branch public -manifest-only` и свежий изолированный каталог, проверяет точные заголовки manifest и соответствие ID имени файла.

Поле `downloaded_bytes: 0` означает нулевую загрузку файловых chunks depot. Обмен метаданными по сети остаётся необходимым; его локальный размер записывается в `metadata_bytes_on_disk`. Probe отклоняет PAK в своём рабочем каталоге. Полная подготовка инструментов и загрузка выбранного server PAK нужны лишь при решении выполнять сборку.

## Желаемые тексты и EN-identity

Единственный ShooterGame-набор — `data/shootergame_ru.json`, **1243** уникальных ключа из точного объединения прежних 1200 corrections и 43 additions. Engine-набор `data/engine_ru.json` содержит прежние **21** перевода `InputKeys`. Раздельные corrections/additions больше не являются источниками данных.

Для каждой текущей пары EN/RU выполняется классификация:

| Условие для желаемого ключа | Категория |
| --- | --- |
| EN отсутствует | Ошибка, сборка остановлена |
| EN-identity не принята или изменилась | Ошибка, сборка остановлена |
| RU отсутствует | `additions` |
| RU совпадает с желаемым текстом | `already_correct` |
| RU содержит другой текст | `corrections` |

На закреплённых входах ShooterGame имеет **1199 corrections / 43 additions / 1 already_correct**, Engine — **16 / 1 / 4**. Поэтому исторические «1200 исправлений» и «20 Engine corrections» не описывают текущее количество заменяемых строк. Суммы желаемых ключей остаются 1243 и 21. Единственный уже правильный ShooterGame-ключ — `Content\t3027221575`; для Engine совпадают `LeftMouseButton`, `MiddleMouseButton`, `RightMouseButton` и `SpaceBar` в namespace `InputKeys`.

Baseline `data/source_identity.json` имеет следующую структуру:

```json
{
  "schema": 1,
  "manifest_id": "3251368963427721326",
  "resources": {
    "ShooterGame": {
      "Namespace\tKey": {
        "namespace_hash": 0,
        "key_hash": 0,
        "source_hash": 0
      }
    },
    "Engine": {}
  }
}
```

Это иллюстрация формата; фактические хэши получены из проверенного stock EN. Baseline хранит только identity желаемых ключей, без официальных EN-текстов. Отсутствующая запись и изменение любого из трёх хэшей запрещают сборку. Посторонние EN-ключи могут меняться. При расхождении отчёт содержит ресурс, full_key, `old_identity`, `current_identity`, `old_source_hash` и `current_source_hash`, чтобы явно показать принятую и текущую identity без EN-текста.

Для явно проверенных ключей предусмотрен отдельный CLI:

```powershell
python -m tools.translation_data accept-source --resource ShooterGame --stock-en work/source/ShooterGame/Content/Localization/ShooterGame/en/ShooterGame.locres --key "Content`t3027221575"
# После просмотра old/new полей повторите команду с --apply.
```

PowerShell `` `t `` создаёт настоящий TAB. `--key` можно повторить; автоматического принятия всех ключей нет. Ключ должен входить в желаемый набор и существовать в указанном EN LOCRES. Без `--apply` baseline не меняется. При записи обновляются только названные identity, JSON сортируется детерминированно. `--resource Engine` выбирает отдельную карту и `data/engine_ru.json`.

`python -m tools.corrections --candidate PATH` проверяет импорт в единый желаемый набор, включая EN-only кандидаты. `--apply` записывает тексты, но новые ключи остаются в `pending_source_acceptance` до явного `accept-source`. Изменившаяся identity существующего желаемого ключа не принимается импортом. Кандидат проходит те же проверки точных плейсхолдеров, printf и RichText.

Для существующих stock RU-ключей исходный `source_hash` сохраняется. Добавления копируют namespace/key/source identity из EN и вставляются в его естественном порядке. Автоматической синхронизации RU-хэшей нет. После repak `info`/`list`/`unpack` сравниваются оба LOCRES побайтно и проверяются все желаемые тексты, включая `already_correct`.

Аудит получает официальные `work/en.json`/`work/ru.json`. Желаемый текст показан отдельно в `our_ru`; `ru_rebuilt.json` не участвует в оценке stock RU. Это сохраняет видимость исходных ошибок локализации.

## Ручной pinned workflow

[cloud-build-pinned.yml](../.github/workflows/cloud-build-pinned.yml) запускается через `workflow_dispatch` на Windows x64 с Python 3.12. Он выполняет bootstrap, pinned-сборку, тесты и формирование облачного отчёта. Для проверки сохраняются `ASA_RU_Fix_P.pak`, `cloud-build-report.json` и компактный validation log; срок хранения workflow-артефакта — три дня. Pinned-проверка не публикует канал обновлений.

## Автоматическое обновление и публикация

[auto-update.yml](../.github/workflows/auto-update.yml) обслуживает текущий публичный manifest. Порядок действий:

1. Подготовить DepotDownloader и выполнить metadata-only probe.
2. Прочитать состояние ветки `channel` и вычислить `build_fingerprint` из явного набора production-файлов и переводов.
3. По паре `(manifest_id, build_fingerprint)` выбрать пропуск, блокировку либо live-сборку.
4. При сборке подготовить полный кэш инструментов, получить выбранный server PAK, выполнить проверки и сравнить SHA-256 полученного патча с опубликованным.
5. При изменении PAK опубликовать версионный GitHub Release через `gh`, проверить размер и SHA-256 asset, затем обновить канал.
6. Записать итог обработки пары в `automation.json`. При ошибке сохранить диагностику и оставить последний успешный `stable.json`.

Документация, тестовые файлы и само расписание не меняют fingerprint. Желаемые переводы, baseline EN-identity и производственный код входят в него. Поэтому новый перевод пересобирает тот же manifest, а простая правка README не требует нового PAK.

Состояние хранится в отдельных JSON-файлах ветки `channel`:

- `stable.json` указывает на последний успешный релиз: версия, URL PAK, размер и SHA-256, сведения о сборке.
- `automation.json` хранит последнюю успешную пару, последнюю попытку, число ошибок и последний релиз.

Успешно обработанная пара пропускается (`SKIPPED`). После **двух deterministic errors одной пары** она блокируется (`BLOCKED`); новый manifest или fingerprint разрешает новую попытку. Временные сетевые ошибки probe/bootstrap/source download не расходуют этот счётчик: `transient_failure` сохраняется в `channel/automation.json` между runners, повтор откладывается на 30 минут → 1 → 2 → 4 → 6 часов (`BACKOFF`). Успех сбрасывает transient-состояние. Неизвестные ошибки не считаются сетевыми. Ручной `workflow_dispatch` с `force_rebuild` разрешает диагностический повтор той же пары. Этот параметр не отключает проверки EN-identity, форматирования и пакета.

`BLOCKED` и `BACKOFF` возвращают 0 только при безопасном пропуске тяжёлой сборки, с предупреждением и явным JSON-статусом. Сводка GitHub Actions отдельно показывает, выполнялась ли полная сборка/валидация. Ошибки сборки и публикации завершают job ненулевым кодом; `PUBLICATION_FAILED` указывает этап. `pending_release` имеет приоритет над пропуском/блокировкой/backoff: восстановление не скрывается под успешным probe и не перезаписывает опубликованные immutable assets.

Patch-компонент версии `x.y.z` повышается только для другого PAK. Если новый manifest или fingerprint даёт прежние байты, новая версия не создаётся: состояние успешной обработки обновляется, последний рабочий asset сохраняется. Публикация сначала проверяет Release и его asset, затем передвигает канал; конфликт обновления ref прекращает запись. Publisher использует `gh`, не меняет аутентификацию и не печатает токены.

Перед публикацией нового PAK `automation.json` сохраняет `pending_release`: версию, commit и исходный проверенный отчёт. Если upload или запись канала прерваны, повтор той же пары использует исходные байты manifest/report/checksums и дополняет draft без перезаписи assets. Незавершённая транзакция с другими входными данными требует явного ручного решения; она не удаляется молча. Публичный Release и `stable.json` не заменяются результатом неуспешной проверки.

Workflow использует `GITHUB_TOKEN` с `permissions: contents: write` для Release, тегов и ветки `channel`. Дополнительный персональный токен не требуется. Группа concurrency — `asa-ru-fix-live-update`, `cancel-in-progress: false`: следующая обработка ожидает завершения текущей.

Основной внешний источник `workflow_dispatch` установлен 28.11.2026: VPS `host4biz`, systemd `asa-ru-fix-trigger.timer` → `asa-ru-fix-trigger.service` → `/usr/local/sbin/asa-ru-fix-trigger`. Таймер содержит `OnCalendar=*-*-* *:07,22,37,52:00`, `Persistent=true`, `AccuracySec=30s`. Журнал VPS прямо связывает запуск 09:52 UTC с GitHub run [46132465865](https://github.com/andreymukha/ASA-RU-Fix/actions/runs/46132465865); actor/triggering_actor — `andreymukha`. Это отдельный источник, а не повтор GitHub schedule.

Чтобы не дублировать частые VPS-проверки, GitHub schedule изменён с `17,47 * * * *` на ежедневный резерв **`47 3 * * *`** (UTC); ручной запуск остаётся доступным. VPS-таймер и его скрипт не изменены: доступный SSH-пользователь не имеет passwordless sudo, units принадлежат root. Для снижения VPS-частоты до двух проверок в час администратору нужно выполнить `sudo systemctl edit asa-ru-fix-trigger.timer` и записать drop-in:

```ini
[Timer]
OnCalendar=
OnCalendar=*-*-* *:07,37:00
```

Затем `sudo systemctl daemon-reload`, `sudo systemctl restart asa-ru-fix-trigger.timer` и `systemctl list-timers asa-ru-fix-trigger.timer`. Сервис, токен и назначение триггера сохраняются; root-доступ для этого изменения в текущей сессии отсутствует. Частые неизменившиеся probes не скачивают server PAK и не создают Release. Группа concurrency исключает параллельные публикации.

GitHub автоматически отключает scheduled workflow публичного репозитория после **60 дней без активности репозитория**. Это ограничение платформы; восстановить расписание можно через Actions, API или GitHub CLI. См. [официальную документацию GitHub](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows). Также возможны задержки запуска schedule, а выполнение привязано к default branch: [GitHub: события workflow](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Статус клиента и ограничения

Updater 1.0.3 читает `stable.json` схемы 1 и проверяет три файла `bundle`; legacy-поля однофайлового выпуска сохраняются для совместимости. Исправление серверного чтения PAK не меняет формат поставки и не требует нового EXE.

Полный текст GPLv3 для ooz хранится побайтно в `tools/licenses/GPL-3.0.txt` и копируется bootstrap с проверкой закреплённого SHA-256. Доступность gnu.org больше не влияет на чистую сборку; исходники ooz по-прежнему загружаются из закреплённого commit с проверкой каждого SHA-256.

Сборка поддерживает незашифрованный PAK V12 с None/Oodle; неизвестный формат, шифрование и повреждённые диапазоны завершаются ошибкой. ASA-файлы directory index могут содержать UTF-8 имя с точной длиной без NUL. Оно допускается только при восьмибайтовом расширении footer, проверенных SHA-1 индексов и совпадении seeded path hash с location каждой такой записи. Числовые поля footer меняются между сборками ARK и не служат allowlist; обычные FString остаются строгими. Метаданные и отдельные ресурсы ограничены 64 MiB. Декодер ooz предназначен для доверенного официального контента; upstream не рассчитан на враждебные сжатые потоки. repak пишет двухресурсный RU-патч V11, к которому добавляются проверенные IoStore companions UTOC/UCAS. Лицензии и происхождение инструментов сохранены в [THIRD_PARTY.md](../THIRD_PARTY.md).

Известные английские UI-случаи `WEIGHT` и `Crafting Requirements` сохраняются как ограничения. Неподтверждённые orphan identity не добавляются, моды исключены из текущего production-перевода. Проверка серверного PAK не равна новому подтверждённому in-game тесту каждого виджета.
