# План клиентского updater

ТЗ пользователя задаёт дизайн и разрешает реализацию в master. Реальные записи Steam/PAK выполняются только после отдельного подтверждения; тесты используют TEMP и child probe.

1. Закрепить .NET 10 LTS SDK 10.0.401/runtime 10.0.12; Core, WinForms App, MSTest и подставной child process. Production без сторонних пакетов.
2. VDF tokenizer со spans, точечный LaunchOptions patch и атомарный reparse/write; discovery библиотек/активного пользователя; Windows quoting и сохранение исходных options.
3. Schema/URL/size/hash validation stable/client, короткий manifest timeout, cancelable PAK download, замена на том же volume; staging self-update без downgrade.
4. Installer/repair/uninstaller, config/state/log rotation, per-user mutex, registry/shortcut, graceful Steam shutdown по согласию, проверка процессов игры.
5. WinForms installer/status/progress; headless Steam wrapper обновляет fail-open, запускает исходную команду, ждёт process, возвращает exit code; self-update после child exit.
6. Fixtures install/repair/uninstall/HTTP/errors/child argv/exit; Python regression сохранения client.json в server channel update.
7. Manual client-build и client-release workflows с pinned SDK, single-EXE oracle, immutable updater tag и проверкой uploaded assets перед channel/client.json. Общая concurrency с server channel writer.
8. Реальные CI build/release, публичная загрузка EXE и read-only diagnose-json именно из Release. Проверка untouched Steam config/PAK/legacy; документация для игроков. Затем один запрос подтверждения реального smoke test.

Контракты: Core namespace `AsaRuFix.Core`; UI зависит от Core. SDK для локальной разработки находится в ignored work/tools/dotnet-10.0.401. CI получает тот же SDK. Steam discovery читает только Valve config; не выводит Steam identity в публичный отчёт. Version updater и translation независимы.
