# Проверка текущего Steam-манифеста

```powershell
python -m tools.manifest_probe --output work/manifest-probe-result.json
```

Нужен уже установленный `work/tools/depotdownloader/DepotDownloader.exe` версии
3.4.0. Probe самостоятельно проверяет версию. Он не запускает bootstrap.

Команда DepotDownloader:

```text
DepotDownloader.exe -app 2430930 -depot 2430931 -branch public -manifest-only -dir <fresh-directory>/content
```

Параметр `-manifest` отсутствует: запрашивается текущий public-манифест.
Каждый запуск использует новый временный каталог внутри `work/manifest-probe`,
включая рабочий каталог процесса. Старые файлы не используются; временные
метаданные удаляются после проверки, включая ошибочный запуск.

Авторитетный источник ID — единственный свежий текстовый манифест
`manifest_2430931_<id>.txt`. Проверяются совпадение ID в имени и заголовке,
depot, структура метаданных и таблицы, а также единственный итог загрузки
с нулём сжатых/несжатых байтов и одним depot. `.pak` в каталоге probe
недопустимы, включая существовавшие до запуска. Ошибки процесса, несовместимая
версия, неподдерживаемые аргументы, отсутствие и неоднозначность манифеста
завершаются ошибкой.

JSON содержит `app_id`, `depot_id`, `manifest_id`, `checked_at` в UTC,
`downloaded_bytes: 0`, `metadata_bytes_on_disk`, `depotdownloader_version`
и `branch`. `downloaded_bytes` означает содержимое файлов depot.
Steam metadata передаются по сети: их трафик не измеряется;
`metadata_bytes_on_disk` — размер временных метаданных на диске.
`server_build_id` не выводится, поскольку текстовый манифест его не содержит.

Официальные источники, закреплённые на теге `DepotDownloader_3.4.0`:

- [README: параметры manifest и manifest-only](https://github.com/SteamRE/DepotDownloader/blob/DepotDownloader_3.4.0/README.md#parameters).
- [Program.cs: обработка manifest-only, текущая ветка, версия](https://github.com/SteamRE/DepotDownloader/blob/DepotDownloader_3.4.0/DepotDownloader/Program.cs#L80).
- [ContentDownloader.cs: возврат до обработки файлов](https://github.com/SteamRE/DepotDownloader/blob/DepotDownloader_3.4.0/DepotDownloader/ContentDownloader.cs#L782).
- [ContentDownloader.cs: точный формат текстового манифеста](https://github.com/SteamRE/DepotDownloader/blob/DepotDownloader_3.4.0/DepotDownloader/ContentDownloader.cs#L1220).

Проверка без сети и без загрузки файлов:

```powershell
python -m unittest discover -s tests -p test_manifest_probe.py -v
```
