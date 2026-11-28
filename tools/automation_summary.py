"""Expose the live update report in GitHub Actions without changing its result."""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path


def summarize(report: dict | None) -> str:
    report = report or {}
    status = report.get('status', 'failed')
    labels = {'success', 'skipped', 'blocked', 'backoff', 'failed', 'publication_failed', 'probe_failed'}
    label = status.upper() if status in labels else 'FAILED'
    full = report.get('heavy_build') is True
    validation = ('PASS' if status == 'success' else 'НЕ ЗАВЕРШЕНА УСПЕШНО') if full else 'НЕ ВЫПОЛНЯЛАСЬ'

    def safe(value):
        return html.escape(str(value)).replace('|', '&#124;').replace('\r', '').replace('\n', '<br>')

    lines = [f'## ASA-RU-Fix: {label}', '']
    if status in ('blocked', 'backoff'):
        lines += ['**Предупреждение:** проверка отложена. Полная сборка и проверка перевода не выполнены.', '']
    if not report:
        lines += ['**Предупреждение:** отчёт отсутствует или повреждён. Смотрите ошибку предыдущего шага.', '']
    rows = [('Статус', label), ('Полная сборка и валидация', validation)]
    for title, value in (
        ('Steam manifest', report.get('steam', {}).get('manifest_id')),
        ('Build fingerprint', report.get('build_fingerprint')),
        ('Причина', report.get('decision', {}).get('reason')),
        ('Предупреждение', report.get('warning')),
        ('Повторная проверка (UTC)', report.get('next_retry_at') or report.get('decision', {}).get('next_retry_at')),
        ('Этап ошибки', report.get('failure_stage')),
        ('Ошибка', report.get('error')),
        ('Ошибка записи состояния', report.get('state_error')),
        ('Версия комплекта', report.get('bundle_version')),
        ('Создан Release', report.get('release_created')),
    ):
        if value is not None:
            rows.append((title, value))
    lines += ['| Проверка | Результат |', '| --- | --- |']
    lines += [f'| {title} | {safe(value)} |' for title, value in rows]
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path('work/live-build-report.json'))
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding='utf-8'))
        if not isinstance(report, dict):
            report = None
    except (OSError, ValueError):
        report = None
    summary = summarize(report)
    if destination := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(destination).open('a', encoding='utf-8') as file:
            file.write(summary)
    print(summary)
    # This always-run diagnostic step does not override the actual build exit code.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
