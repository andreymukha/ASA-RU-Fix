# Клиент ASA RU Fix

Клиент предназначен для Steam-версии ARK: Survival Ascended, AppID `2399830`, на Windows x64. Игрок получает один `ASA-RU-Fix.exe`. Это WinForms приложение, собранное как `win-x64`, self-contained single-file, без trimming. Отдельный .NET Runtime и инструменты разработки игроку не нужны.

Статус подтверждённых CI, Release, read-only diagnostic и установочного smoke test хранится в [TESTING.md](../TESTING.md). Описание поведения ниже не заменяет результат этих проверок.

## Установка и обычный запуск

Скачайте EXE из updater Release, запустите и нажмите «Установить и настроить». Клиент найдёт Steam, библиотеки и ARK. Если несколько Steam profiles не позволяют определить активного пользователя однозначно, выберите нужный профиль. При отсутствии найденной игры можно указать папку ARK вручную; её структура проверяется. Новый интерфейс пока доступен только в исходниках и локальном preview для будущего выпуска: публичная **updater-v1.0.0** сохраняет прежнюю кнопку «Установить».

Постоянный путь установки:

```text
%LOCALAPPDATA%\ASA-RU-Fix\ASA-RU-Fix.exe
```

В этой же папке находятся `config.json`, `config.json.backup`, `state.json`, `logs\` и `updates\`. Config хранит локальные пути, профиль и точные исходные Launch Options; state — сведения о проверенном переводе. Эти данные не отправляются в сеть. Скачанный bootstrap из Downloads автоматически не удаляется. После успешной установки его можно удалить самостоятельно.

Повторный запуск скачанного bootstrap использует ту же per-user установку. Версии сравниваются перед заменой; старая скачанная копия не должна понижать уже установленную версию или создавать вторую installation.

Установка per-user: Start Menu shortcut «ASA RU Fix», регистрация в `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall` и удаление через Windows Installed Apps. MSI и admin для самой регистрации не нужны. Запись PAK требует доступ на запись к папке игры; ошибка доступа показывается пользователю.

После установки запускайте ARK кнопкой «Играть» в Steam. При актуальном переводе updater работает без консоли и без окна. Он запускается вручную либо перед игрой, остаётся wrapper process до завершения запущенной команды и возвращает её exit code, где это возможно.

## Главное окно и необязательные проверки

В исправной установке главное окно показывает найденные Steam/ARK, выбранный профиль, работающую интеграцию и установленную версию перевода. Оно сообщает: «Автообновление перевода и программы включено. Всё готово. Просто запускайте ARK обычной кнопкой „Играть“ в Steam». Основной кнопки обновления нет.

Основное действие появляется только по состоянию: «Установить и настроить», «Указать папку ARK», «Восстановить интеграцию Steam» или «Восстановить установку». При неоднозначности профиль необходимо выбрать; один найденный профиль отображается обычной строкой без ComboBox. Полные пути доступны в подсказках к строкам Steam/ARK. Пустая полоса прогресса скрыта; она появляется только на время операции.

Меню «Дополнительно» содержит «Проверить перевод сейчас», «Проверить обновление программы сейчас», восстановление интеграции, ручной выбор папки ARK, открытие лога и отделённое разделителем «Удалить ASA RU Fix». Эти действия обычно не нужны. Проверка перевода не скачивает PAK заново, если локальный SHA совпадает с каналом. Недоступные действия отключены.

Статус перевода вычисляется по локальному state и фактическому SHA файла. При открытии окна нет сетевой проверки и обещания «последней версии». Неполная установка не считается исправной. Если Steam ссылается на отсутствующий EXE, а сохранённых исходных параметров нет, автоматическое восстановление блокируется: восстановите исходные параметры из своей резервной копии в свойствах игры Steam или обратитесь за помощью. Не удаляйте неизвестные параметры вручную.

### Безопасный локальный preview

Из корня проекта после локальной сборки:

```powershell
& '.\work\client-preview\ASA-RU-Fix.exe' --ui-preview
```

Также можно открыть `work\client-preview\Открыть предпросмотр.vbs` двойным кликом. Это реальное новое окно, а не отдельное приложение. Режим обходит переадресацию на установленный EXE и очистку self-update; выполняет только локальное чтение без сети. Установка, repair, удаление, выбор папки и ручные обновления отключены. Доступно безопасное открытие уже существующего лога. Установленная v1.0.0, Steam, PAK, registry, shortcut, config/state не изменяются. Preview не является Release artifact; запускайте именно с `--ui-preview`.

## Обнаружение Steam и профиля

Steam path читается из HKCU registry с fallback на стандартную HKLM запись Steam. Клиент читает `steamapps\libraryfolders.vdf`, поддерживает несколько библиотек и определяет фактический install directory по `appmanifest_2399830.acf`. Диск и название папки установки не фиксируются в коде.

Для Steam user учитываются registry `ActiveUser`, `config\loginusers.vdf` и существующие `userdata` directories. При неоднозначности выбор не делается молча. Launch Options записываются в файл выбранного профиля:

```text
Steam\userdata\<user>\config\localconfig.vdf
```

Нужный entry: `UserLocalConfigStore → Software → Valve → Steam → apps → 2399830 → LaunchOptions`.

## Steam Launch Options

Managed wrapper имеет вид:

```text
"<LOCALAPPDATA>\ASA-RU-Fix\ASA-RU-Fix.exe" --steam-launch -- %command%
```

`<LOCALAPPDATA>` здесь обозначает фактический абсолютный путь текущего пользователя. В Steam хранится ровно один managed wrapper. Предыдущее значение сохраняется точно в `original_launch_options` перед изменением VDF, включая отсутствие entry, пустую строку, quoting и пользовательский wrapper.

Простые исходные flags, например `-high -foo`, добавляются к настоящей команде игры. Если исходные options содержат один допустимый `%command%`, он заменяется Windows command line, полученной от Steam после `--`. Поддерживаются пути с пробелами, пустые аргументы, quotes и Unicode. Неоднозначный template, shell operators или неподдерживаемая структура останавливают автоматическую интеграцию с понятным сообщением.

VDF tokenizer сохраняет позиции токенов. Меняется только нужный entry; неизвестные keys, другие игры, кодировка и BOM сохраняются. Новый файл записывается рядом, повторно разбирается и проверяется, затем атомарно заменяет старый. Перед заменой проверяются отсутствие Steam и неизменность исходных байтов.

При install/repair/uninstall Steam должен быть закрыт. После согласия пользователя применяется `steam.exe -shutdown`, затем ожидается реальное завершение. Если Steam остаётся активен, VDF не записывается. При запущенной ARK PAK не заменяется; программа просит закрыть игру. Принудительное завершение Steam или ARK не используется.

## Загрузка перевода и fail-open

Источник перевода — [stable.json](https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/stable.json), schema `1`. Клиент скачивает только готовый `ASA_RU_Fix_P.pak` из versioned GitHub Release. Server depot, game PAK extraction, LOCRES rebuild, repak и ooz на стороне игрока не используются.

Целевой файл:

```text
<ARK>\ShooterGame\Content\Paks\ASA_RU_Fix_P.pak
```

До загрузки проверяются schema, версия, имя, ограничение размера, SHA-256 и URL именно репозитория `andreymukha/ASA-RU-Fix`. Скачивание идёт во временный файл; фактические размер и SHA проверяются до замены. Для установки используется staging рядом с целевым PAK на том же volume. Существующий PAK сохраняется при download, hash, permission, disk или atomic replace error. Проверка запущенной игры повторяется перед заменой.

Получение manifest ограничено пятью секундами; отдельная загрузка имеет timeout и cancellation. При обновлении PAK Steam-launch показывает прогресс и позволяет пропустить обновление. При timeout, DNS/HTTP ошибке, неверном JSON/schema/hash, отмене или занятости updater игра запускается с текущим PAK. Если PAK ещё нет, запускается обычная игра. Плохой файл никогда не устанавливается ради успешного запуска.

Если config повреждён, сначала читается backup. Ошибка updater не должна блокировать исходную команду Steam. `steam://rungameid` в wrapper mode не используется, чтобы не создать рекурсию.

## Обновление самого клиента

Отдельный источник — [client.json](https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/client.json), schema `1`. Updater version `1.0.0` и translation version `1.0.0` — разные потоки. Client releases используют tags `updater-v1.0.0`, `updater-v1.0.1` и далее; translation tags имеют вид `v1.0.0`.

Client manifest содержит `version`, `release.tag`, `release.commit`, `release.published_at` и `artifact.filename`, `artifact.size`, `artifact.sha256`, `artifact.download_url`. Источник истины — manifest, не GitHub Latest Release.

Если опубликованная версия новее, новый EXE скачивается в `updates\new.pending.exe` и проверяется по size/SHA/URL. Игра запускается без ожидания этой загрузки; self-update выполняется пока wrapper ждёт игру. После завершения игры pending EXE запускается в режиме `--complete-self-update`, ожидает старый updater PID, атомарно заменяет установленный EXE, проверяет результат и обновляет локальную регистрацию версии. Путь установки и Steam Launch Options сохраняются. При ошибке остаётся рабочая прежняя копия; downgrade не выполняется.

Операции install, update, self-update и uninstall координируются per-user named mutex. Если другой экземпляр занят во время Steam launch, новая проверка пропускается и исходная игра запускается.

## Удаление и восстановление

Нажмите «Дополнительно → Удалить ASA RU Fix» (в публичной v1.0.0 — «Удалить»), воспользуйтесь Windows Installed Apps либо запустите установленный EXE с `--uninstall`. Закройте ARK; согласуйте закрытие Steam, если оно требуется.

Uninstall сначала восстанавливает исходные Launch Options для сохранённых integrations. Если wrapper ещё идентичен managed значению, восстанавливается точный original entry. Если пользователь убрал wrapper самостоятельно, текущие options сохраняются. Если к managed wrapper добавлены безопасные простые flags, они сохраняются вместе с прежними options. Неоднозначная правка блокирует удаление EXE, пока остаётся ссылка Steam на updater: чужие options не перезаписываются.

После успешного удаления интеграции удаляются только `ASA_RU_Fix_P.pak`, регистрация HKCU, shortcut и собственные config/state/logs/updates. Running EXE удаляется helper после выхода. Steam profiles, другие PAK и скачанный пользователем bootstrap сохраняются.

Если интеграция повреждена, используйте «Восстановить интеграцию Steam» на главном экране или в «Дополнительно». Не удаляйте установленный EXE вручную, пока Steam ссылается на него. При повреждении обоих config файлов автоматическое восстановление точных original options невозможно; удаление останавливается с объяснением. Логи находятся локально в `logs\updater.log`; предусмотрена ротация. Человекочитаемые записи используют локальное время Windows в ISO 8601 с offset. Машинные timestamps config/state, каналов, manifests, Actions и серверной автоматизации остаются UTC.

## Приватность и доверие

Сеть используется только для необходимых HTTP GET manifest и файлов GitHub; разрешённые HTTPS download redirects проверяются отдельно. Клиент не получает токены и не отправляет Steam ID, пути, hardware info, список игр или logs. Telemetry, service, scheduled task, Windows Startup и постоянный background daemon отсутствуют.

EXE неподписан. SmartScreen warning возможен при первом запуске. Клиент не добавляет self-signed certificates, не ослабляет Windows security, не меняет game EXE и anti-cheat. SHA-256 проверяет соответствие скачанного файла manifest; доверие к самим обновлениям опирается на HTTPS, репозиторий и его доступы.

## Архитектура

`client/src/AsaRuFix.Core` содержит VDF parser, Steam discovery, command reconstruction, manifest/URL validation, атомарные файлы, PAK/self-update и install/uninstall. `client/src/AsaRuFix.App` — WinForms UI, process/registry/shortcut integration и headless CLI dispatch. Production код использует стандартные .NET/Windows API; тестовые MSTest зависимости находятся только в `client/tests`.

Клиент отделён от серверной сборки и её `build_fingerprint`. Серверная автоматизация продолжает выпускать перевод по расписанию `17,47 * * * *`; client code не требует изменений datasets или source identities.

## Сборка и публикация

Закреплены .NET 10 LTS SDK `10.0.401` в `client/global.json` и runtime `10.0.12`. Локально из `client/`, с этим SDK в PATH:

```powershell
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
dotnet build tests/ChildProbe/ChildProbe.csproj --configuration Release
$env:ASA_RU_FIX_CHILD_PROBE = Join-Path (Get-Location) 'tests/ChildProbe/bin/Release/net10.0/ChildProbe.exe'
dotnet test tests/AsaRuFix.Tests/AsaRuFix.Tests.csproj --configuration Release --logger 'trx;LogFileName=client-tests.trx' --results-directory ../work/client-test-results
dotnet publish src/AsaRuFix.App/AsaRuFix.App.csproj --configuration Release --runtime win-x64 --self-contained true --output ../work/client-publish -p:PublishSingleFile=true -p:PublishTrimmed=false -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=embedded -p:RuntimeFrameworkVersion=10.0.12
```

[client-build.yml](../.github/workflows/client-build.yml) запускается только вручную, имеет `contents: read`, выполняет C# и Python tests, publish и проверку ровно одного EXE в пользовательской папке. Artifact `asa-ru-fix-client-win-x64` содержит только `ASA-RU-Fix.exe`; `asa-ru-fix-client-build-report` содержит JSON, SHA256SUMS и TRX.

[client-release.yml](../.github/workflows/client-release.yml) запускается вручную из master с input `version`, точно совпадающим с `client/Directory.Build.props`. Он повторяет tests/publish, создаёт immutable tag исходного commit и draft Release с `make_latest=false`. Assets: `ASA-RU-Fix.exe`, `SHA256SUMS.txt`, `client-manifest.json`. Metadata содержат source commit и параметры сборки без случайного run ID или времени, поэтому повторная проверка идентичного выпуска воспроизводима.

EXE скачивается через GitHub API и проверяется до публикации draft и после неё. Только после успешной проверки обновляется `channel/client.json`. Existing public Release принимается без изменений только при совпадении commit и всех assets; несовпадение останавливает выпуск. Upload не использует `--clobber`, tag/ref не обновляются force.

Client writer использует исходный `base_tree`, BOT author/committer и fast-forward commit, меняя только `client.json`. Серверный writer аналогично сохраняет client и неизвестные файлы. Оба writer workflow используют одну concurrency группу `asa-ru-fix-live-update`, `cancel-in-progress: false`. Повторное identical обновление client manifest не создаёт commit. Token — только встроенный `GITHUB_TOKEN` с `contents: write`.

## Проверки

C# fixtures используют TEMP, подставной HTTP handler/platform и `ChildProbe.exe`, который записывает полученные аргументы и возвращает заданный exit code. Они проверяют VDF, discovery, quoting/templates, размер/SHA/schema/URL, transaction failures, install/repair/uninstall и self-update. Они не запускают ARK, не меняют реальный Steam и не заменяют реальный PAK.

Из корня репозитория Python fixtures запускаются командой:

```powershell
python -m unittest discover -s tests
```

После реального Release отдельно скачивается публичный EXE без токена и сверяется с `client.json` по size/SHA. Именно скачанный Release EXE запускается с `--diagnose-json`: режим читает обнаруженные Steam/ARK, integration и PAK status, без установки и изменения Steam. Это отдельная read-only проверка.

Реальный установочный smoke test выполняется только после согласия пользователя: сохранить hash/backup Steam localconfig, установить, проверить wrapper и original options, выполнить обычный Steam launch и uninstall, проверить восстановление. Для публикации не требуется предварительно менять реальную систему разработчика. Все выполненные результаты и ограничения заносятся в [TESTING.md](../TESTING.md).
