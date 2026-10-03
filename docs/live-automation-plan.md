# План серверной автоматизации

Цель: готовый stable channel и небольшой Release PAK для будущего updater.
Работа выполняется в `master` по предоставленному ТЗ; клиентская доставка в этот этап не входит.

Архитектура: единый desired dataset и явный baseline EN identity; общий проверенный
build path с профилями `pinned` и `live`; отдельный оркестратор probe/state/build/publish.
Ветка `channel` содержит только generated state и обновляется обычными commits.

- [ ] Объединить 1200 corrections и 43 additions без изменения текстов; создать 1264 identities.
- [ ] Сохранить pinned oracle и проверить его byte-for-byte после миграции.
- [ ] Добавить live stock validation, динамическую классификацию и source guard.
- [ ] Проверить manifest-only DepotDownloader 3.4.0 на hosted runner.
- [ ] Добавить fingerprint, skip/retry/block state, idempotent publisher и fixtures.
- [ ] Создать доказанный baseline Release v1.0.0 и orphan channel.
- [ ] Выполнить реальный forced live run, затем unchanged fast-path run.
- [ ] Включить schedule только после PASS всех обязательных проверок.
- [ ] Проверить публичные stable/automation JSON и Release asset; обновить документацию.

Команды проверки: `python -m unittest discover -s tests -v`,
`python build.py --profile pinned --source server-pak --server-pak PATH`,
`gh workflow run cloud-build-pinned.yml --ref master`,
`gh workflow run auto-update.yml --ref master -f force_rebuild=true`, затем `false`.

LIVE проверяет все 1243 ShooterGame и 21 Engine desired values после unpack;
неизвестная EN identity или структурная ошибка блокирует публикацию.
Schedule добавляется отдельным commit после реальных manual/fast-path PASS.
