# Проверка серверной автоматизации — 2026-10-03

Серверная часть готова: probe → пара manifest/fingerprint → проверенная сборка → сравнение PAK → Release при изменении → канал. **Пользовательская доставка и Steam-launch updater ещё не реализованы.**

## Данные и источник

Прежние 1200 corrections и 43 additions объединены без изменения русских текстов в `data/shootergame_ru.json`: 1243 уникальных ключа. Старые два файла удалены. `data/engine_ru.json` сохраняет 21 желаемую строку. `data/source_identity.json` содержит 1264 принятые EN identity: namespace/key/source hash; официальные EN-тексты не публикуются.

Текущий public Steam: app `2430930`, depot `2430931`, manifest `3251368963427721326`. Probe DepotDownloader 3.4.0 на hosted runner скачал только metadata, PAK bytes = 0; metadata на диске = 563323 bytes. Текущий Build ID probe достоверно не предоставляет. Исторический pinned Build ID `25683903` остаётся диагностикой, не compatibility gate.

| Ресурс | Исправления | Добавления | Уже правильные | Missing | Source changed | Всего |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ShooterGame | 1199 | 43 | 1 | 0 | 0 | 1243 |
| Engine | 16 | 1 | 4 | 0 | 0 | 21 |

Одна строка ShooterGame уже совпадает со stock: `Content<TAB>3027221575 = Кожаная шапка`. Она остаётся desired и проверяется в PAK. Итоговые числа классов могут меняться после обновлений; обязательны 1243/1243 и 21/21 желаемых значений.

| Stock LOCRES | Размер, bytes | Entries | Версия | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| ShooterGame EN | 3669617 | 39444 | 3 | `efb6606905da0c3b5883c2472b253db5e22f5cd2e948cb0d1601b565ce41a216` |
| ShooterGame RU | 4996378 | 35598 | 3 | `be8b5d46901bc3780be0454dbc9545908cdb35b6cc59cd5dd48315d9887a1d44` |
| Engine EN | 3909182 | 48284 | 3 | `c0ae7e3dc9fb0f38ab39064f4556737c7ebf3a7ed8bd3971dd6dd0912ddf2d30` |
| Engine RU | 5805962 | 45771 | 3 | `4e9e6bc08b577c947ec67bc1168633916f464d45ce973c8a5f6de54159a9d475` |

В live exact hashes/count не являются ограничением. Требуются parse, структура, четыре пути и принятие identity только наших ключей. Новый EN source hash или пропавший desired EN key останавливает публикацию; явный `accept-source` применяется после ручного review выбранных ключей.

## Реальные hosted проверки

Production-код проверен на commit `a49e7dd5fec1bac7f0835852193dbb263a0cbad1`.

| Проверка | Run | Длительность от создания до завершения | Результат |
| --- | --- | --- | --- |
| Pinned regression | [37096446767](https://github.com/andreymukha/ASA-RU-Fix/actions/runs/37096446767) | 94 s | PASS, 168 tests, PAK byte-identical legacy |
| Live, force=true | [37096442392](https://github.com/andreymukha/ASA-RU-Fix/actions/runs/37096442392) | 96 s | PASS, 168 tests, все 1264 desired MATCH |
| Повтор, force=false | [37096569230](https://github.com/andreymukha/ASA-RU-Fix/actions/runs/37096569230) | 33 s | PASS, fast path, server PAK не скачивался |

Live download: **1146602176 bytes** по отчёту DepotDownloader; распакованный server PAK: **1487841986 bytes**, SHA-256 `81f869e826568d16b49f11b1b42ac8cd3116f9534cc68616824e4a35f0ee490f`. Download выполнен с точным manifest из probe, не с неопределённым latest.

Pinned и live: repak `info/list/unpack`, повторный LOCRES parse, побайтное сравнение ресурсов и 1243/1243 + 21/21 desired values — PASS. Placeholders/printf/RichText: 1264 entries, **0 issues**. Локальный полный suite — **168 PASS**; standalone guard — PASS, четыре cached repak процесса, ноль запрещённых доступов. Порядок физических блоков repak канонизирован; payload и lookup проверяются перед заменой, pinned oracle сохранён. См. [детерминизм repak](repak-determinism.md).

Fast path: `downloaded_bytes=0`, `full_bootstrap=false`, `heavy_build=false`, `release_created=false`. Не скачивались repak и server PAK, не компилировался ooz, не запускались сборка и полный suite. Commit канала сохранился `db32838a078c7fa2e66a657cf4b9f31b32224dab`: heartbeat commit отсутствует.

Первый проход также был успешен: pinned `37096166122`, live `37096179668`, skip `37096302229`. При дополнительной проверке `37096369421` произошёл сетевой WinError 10060 в bootstrap; state записал ошибку и сохранил последнюю успешную stable-версию. Финальный проход прошёл без обхода проверок. Fixtures отдельно подтверждают retry/block после двух ошибок одной пары, force retry и восстановление частично опубликованного Release.

## Release и канал

[v1.0.0](https://github.com/andreymukha/ASA-RU-Fix/releases/tag/v1.0.0) создан из повторно скачанного доказанного артефакта run `37092180003`; его report сохранён побайтно. Release tag указывает на `d675366eed03434cdc762b4e2baf3a180e909515`, published at `2026-10-03T04:18:34Z`.

Assets: `ASA_RU_Fix_P.pak`, `release-manifest.json`, `SHA256SUMS.txt`, `cloud-build-report.json`. Официальные stock LOCRES и server PAK не публиковались.

PAK **10795036 bytes**, SHA-256 **`914589668aa41516915a68ef233873f4aeeedf570db70a7232e36ff9e8c04f2b`**. Pinned artifact и публичный Release asset скачаны и побайтно сравнены с legacy. Публичное скачивание без токена — PASS. Live SHA совпадает с baseline: новая версия `v1.0.1` и новый Release **не создавались**.

Публичные JSON: [stable.json](https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/stable.json), [automation.json](https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/automation.json). Ветка `channel` — минимальная orphan history, обычные fast-forward commits от `github-actions[bot]`, без force.

Ключевые stable поля: schema 1, channel stable, version 1.0.0, manifest `3251368963427721326`, desired totals 1243/21, конкретный [versioned PAK URL](https://github.com/andreymukha/ASA-RU-Fix/releases/download/v1.0.0/ASA_RU_Fix_P.pak), размер и SHA выше. Fingerprint: `72853b3027d0fbcb50ae0a997dc78c90c766cbb94c96b347971bce3823c242be`; локальный LF checkout и hosted checkout совпали. Текущее состояние automation: success, attempt_count 1 для финальной пары, failure_count 0, last_successful run `37096442392`, latest release v1.0.0. Skip его не переписывает.

Расписание включено **после** этих проверок: `17,47 * * * *`. Concurrency `asa-ru-fix-live-update`, `cancel-in-progress: false`. Только `GITHUB_TOKEN`, permissions `contents: write`; pinned workflow имеет `contents: read` и остаётся manual. Ограничение GitHub: public schedule может отключаться после 60 дней без repository activity; возможны задержки запуска.

## Ограничения этапа

Legacy snapshot сохранён. ARK не запускался, DevKit не использовался, локальная установка не выполнялась, VPS и fake/test Releases не создавались. Новый in-game тест не проводился; прежнее подтверждение кнопки «Назад» остаётся пользовательским свидетельством. `WEIGHT` / `Crafting Requirements` могут оставаться английскими в отдельных UI; CS/Cybers Structures исключены из базового перевода. Массовый перевод и новый asset scan не выполнялись.

Будущий Steam-launch updater сможет читать `stable.json` и при необходимости скачивать готовый ~11 MB Release asset. Этот клиент ещё не реализован.
