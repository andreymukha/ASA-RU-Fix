# Проверка первого публичного клиента — 2026-10-03

## Сборка и выпуск

Опубликован настоящий unsigned клиент Windows x64, updater **1.0.0**, tag **updater-v1.0.0**. Исходный commit обоих workflow: `c4e30fa0e8b77d5d48e6d2d06d6d972668c44351`. Использованы .NET 10 LTS, SDK **10.0.401**, runtime **10.0.12**; параметры self-contained, single-file, без trimming, native self-extract и embedded debug. PE: x64 (`0x8664`), Windows GUI subsystem (`2`). Игроку не требуются Python, Git, gh, отдельный .NET Runtime или GitHub token.

| Проверка | Результат |
|---|---|
| Локальные .NET fixture tests | 106/106 PASS, 0 пропусков |
| Python server/client regression tests | 185/185 PASS |
| Локальная WinForms публикация | PASS, 0 предупреждений |
| Реальный client-build | [37100803273](https://github.com/andreymukha/ASA-RU-Fix/actions/runs/37100803273), SUCCESS; job 77 секунд |
| Реальный client-release | [37100953608](https://github.com/andreymukha/ASA-RU-Fix/actions/runs/37100953608), SUCCESS; job 99 секунд |
| CI .NET TRX | 106/106 PASS |
| Публичное скачивание без токена | PASS |
| Сравнение Release EXE с Actions EXE | Побайтно одинаковы |
| Read-only diagnostic из Release EXE | PASS, exit code 0 |

В user artifact `asa-ru-fix-client-win-x64` находится только `ASA-RU-Fix.exe`. TRX и manifest вынесены в `asa-ru-fix-client-build-report`; отчёт выпуска — `asa-ru-fix-client-release-report`.

## Публичный бинарный файл и канал

- [Release updater-v1.0.0](https://github.com/andreymukha/ASA-RU-Fix/releases/tag/updater-v1.0.0).
- [Скачать ASA-RU-Fix.exe](https://github.com/andreymukha/ASA-RU-Fix/releases/download/updater-v1.0.0/ASA-RU-Fix.exe).
- [client.json](https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/client.json).
- Размер EXE: **116 246 264 байта**.
- SHA-256: `a043c978a6e1f2f0673b35011361a29f37c458d6d1e2f5ecaf98062feaa0f74e`.

Проверенные поля `client.json`: schema `1`, version `1.0.0`, release.tag `updater-v1.0.0`, release.commit `c4e30fa0e8b77d5d48e6d2d06d6d972668c44351`, release.published_at `2026-10-03T05:48:55Z`, artifact.filename `ASA-RU-Fix.exe`, size/SHA/download URL как выше. Manifest SHA совпал с фактически скачанным EXE. Release также содержит `SHA256SUMS.txt` и `client-manifest.json`; иных файлов игроку скачивать не нужно.

EXE не подписан. Trusted self-signed сертификаты не устанавливались, Windows SmartScreen и проверка TLS не отключались. В диагностике переменная `DOTNET_ROOT` указывала на несуществующий каталог: опубликованный EXE выполнился автономно.

## Локальная диагностика без установки

Реальный Release EXE запущен только с `--diagnose-json`. Диагностика:

- Steam найден; ARK найдена.
- Активный Steam user определён; доступны два локальных профиля. Private identity в отчёт не включается.
- Новая Launch Options интеграция отсутствует; установленного клиентского EXE пока нет.
- PAK существует, соответствует stable translation `1.0.0`.
- SHA PAK: `914589668aa41516915a68ef233873f4aeeedf570db70a7232e36ff9e8c04f2b`.
- Публичный stable manifest доступен; ошибок сети нет.

Две реальные `localconfig.vdf` проверены по контрольным суммам до и после: **2/2 не изменились**. Read-only diagnostic не является доказательством успешной установки на реальной машине.

Установка, repair, uninstall, отказ от записи при запущенной Steam/игре, восстановление исходных Launch Options, проверка SHA, отмена загрузки, сохранение старого файла при ошибке, self-update staging/replacement, mutex, обработка PID и выход тестового дочернего процесса проверены на временных fixture данных. Реальная GUI установка и перезапуск Steam пока не выполнялись: перед этим этапом требуется одно отдельное подтверждение пользователя согласно ТЗ. ARK запускать запрещено.

## Сохранность серверного pipeline и legacy

- `stable.json` после client release побайтно равен сохранённому до публикации.
- `automation.json` также побайтно равен исходному; добавлен только `client.json`.
- Latest GitHub Release остался translation `v1.0.0`, клиент опубликован с `make_latest=false`.
- Серверный workflow имеет состояние `active`; cron остался `17,47 * * * *`.
- Серверный fingerprint остался `72853b3027d0fbcb50ae0a997dc78c90c766cbb94c96b347971bce3823c242be`.
- Regression tests доказывают сохранение `client.json` при серверной записи Git tree и сохранение stock каналов при клиентской записи.
- Legacy snapshot: **68/68 файлов** сохранили пути и SHA-256.

ARK и DevKit не запускались. Игровой PAK не перезаписывался и не удалялся. Steam не закрывался и не перезапускался. Telemetry, service, scheduled task, credentials, VPS и fake/test Releases отсутствуют. Серверная автоматизация не заменена клиентом: клиент скачивает только готовый PAK.

## Использование и восстановление

Описание клиентских служб и всех пользовательских действий: [client-updater.md](client-updater.md). Основной сценарий: скачать один EXE, установить, затем запускать ARK кнопкой «Играть» в Steam.

Постоянная установка: `%LOCALAPPDATA%\ASA-RU-Fix\ASA-RU-Fix.exe`; рядом находятся `config.json`, `config.json.backup`, `state.json`, `logs\updater.log` и `updates\`. Точный managed wrapper:

```text
"<LOCALAPPDATA>\ASA-RU-Fix\ASA-RU-Fix.exe" --steam-launch -- %command%
```

VDF меняется точечно при закрытой Steam. Оригинальные параметры сохраняются, `%command%` раскрывается исходной командой, остальные простые flags сохраняются. Сложный shell wrapper отклоняется до изменения интеграции. Сетевая ошибка, неправильный manifest/SHA, отказ записи или недоступный mutex позволяют запустить исходную игровую команду. PAK заменяется через проверенный временный файл в том же каталоге и atomic replacement.

Self-update использует отдельный `client.json`, сохраняет проверенный `new.pending.exe`, ждёт завершения игры и старого updater PID, затем меняет фиксированный установленный EXE. Понижение версии запрещено. Uninstall восстанавливает Launch Options ранее интегрированных профилей; безопасные добавленные flags сохраняются. При неоднозначно изменённом wrapper удаление останавливается и EXE сохраняется. После снятия интеграции удаляются собственный PAK, регистрация, ярлык и установленные данные; запущенный EXE удаляет отдельный helper после выхода процесса. Скачанный bootstrap не удаляется.
