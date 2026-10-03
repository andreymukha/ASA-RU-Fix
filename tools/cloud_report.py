"""Run the unit suite and emit the compact cloud-build report."""

from __future__ import annotations

import argparse
import io
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.bootstrap import DEPOTDOWNLOADER_VERSION
from tools.server_depot import APP_ID, DEPOT_ID, EXPECTED_PAK_SHA256, EXPECTED_PAK_SIZE, PINNED_MANIFEST, PINNED_STOCK

SERVER_BUILD_ID = "25683903"
ROOT = Path(__file__).resolve().parents[1]


def run_tests(log_path: Path) -> dict[str, object]:
    """Run the complete unittest suite and preserve its compact text log."""
    import unittest

    buffer = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(buffer.getvalue(), encoding="utf-8")
    sys.stdout.write(buffer.getvalue())
    return {
        "result": "PASS" if result.wasSuccessful() else "FAIL",
        "count": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
    }


def make_report(build: dict, tests: dict, *, commit: str, timestamp: str | None = None) -> dict:
    source = build["source"]
    if source.get("kind") != "steam-dedicated-server":
        raise RuntimeError("cloud report requires a Steam Dedicated Server build")
    if source.get("app_id") != APP_ID or source.get("depot_id") != DEPOT_ID or source.get("manifest") != PINNED_MANIFEST:
        raise RuntimeError("cloud build used an unexpected Steam app, depot, or manifest")
    if (build.get("pak_size") != EXPECTED_PAK_SIZE
            or build.get("pak_sha256") != EXPECTED_PAK_SHA256
            or not build.get("deterministic_match")):
        raise RuntimeError("cloud build did not produce the pinned byte-identical PAK")
    if tests.get("result") != "PASS":
        raise RuntimeError("unit test suite failed")
    if tests.get("count", 0) < 67:
        raise RuntimeError(f"unit test suite count is unexpectedly low: {tests.get('count')}")
    if build.get("counts") != {"shooter_desired": 1243, "engine_desired": 21}:
        raise RuntimeError("cloud build translation counts do not match the production baseline")
    if build.get("translation_validation", {}).get("status") != "PASS" or build["translation_validation"].get("issues") != 0:
        raise RuntimeError("placeholder/printf/RichText validation did not pass")
    stock_inputs = build.get("stock_input_validation", {})
    if set(stock_inputs) != set(PINNED_STOCK) or any(item.get("status") != "PASS" for item in stock_inputs.values()):
        raise RuntimeError("cloud build did not validate exactly the four pinned stock LOCRES files")
    if build.get("package", {}).get("list_info_unpack") != "PASS":
        raise RuntimeError("repak info/list/unpack did not pass")
    return {
        "timestamp_utc": timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": commit,
        "runner_os": platform.platform(),
        "python_version": platform.python_version(),
        "steam": {
            "app_id": APP_ID,
            "depot_id": DEPOT_ID,
            "manifest_id": PINNED_MANIFEST,
            "server_build_id": SERVER_BUILD_ID,
            "depotdownloader_version": DEPOTDOWNLOADER_VERSION,
            "downloaded_bytes": source.get("downloaded_bytes"),
        },
        "stock_locres": build["stock_input_validation"],
        "translation_counts": build["counts"],
        "dynamic_classification": {name: item['classification']
                                   for name, item in build.get('resources', {}).items()},
        "placeholder_printf_richtext_validation": build["translation_validation"],
        "tests": tests,
        "repak_validation": build["package"]["list_info_unpack"],
        "final_pak": {
            "path": "ASA_RU_Fix_P.pak",
            "size": build["pak_size"],
            "sha256": build["pak_sha256"],
            "expected_sha256": EXPECTED_PAK_SHA256,
            "deterministic_match": build["deterministic_match"],
        },
    }


def make_live_report(build: dict, tests: dict, probe: dict, *, fingerprint: str,
                     commit: str, run_id: str, previous_sha: str | None) -> dict:
    if build.get('profile') != 'live' or build.get('counts') != {'shooter_desired': 1243, 'engine_desired': 21}:
        raise RuntimeError('live build profile or desired counts mismatch')
    source = build['source']
    if (source.get('kind') != 'steam-dedicated-server' or source.get('manifest') != probe['manifest_id']
            or source.get('app_id') != APP_ID or source.get('depot_id') != DEPOT_ID):
        raise RuntimeError('live build source differs from resolved Steam probe')
    if tests.get('result') != 'PASS' or tests.get('count', 0) == 0:
        raise RuntimeError('full test suite did not pass')
    if build['translation_validation']['status'] != 'PASS' or build['translation_validation']['issues']:
        raise RuntimeError('translation formatting validation failed')
    if build['package']['list_info_unpack'] != 'PASS':
        raise RuntimeError('repak validation failed')
    if (set(build['stock_input_validation']) != set(PINNED_STOCK)
            or any(item.get('status') != 'PASS' for item in build['stock_input_validation'].values())):
        raise RuntimeError('live stock resource set mismatch')
    for name, total in (('ShooterGame', 1243), ('Engine', 21)):
        item = build['resources'][name]
        counts = item['classification']
        if (sum(counts[k] for k in ('corrections', 'additions', 'already_correct')) != total
                or counts['missing'] or counts['source_changed']
                or item['desired_verification'] != {'expected': total, 'actual': total, 'mismatches': 0}):
            raise RuntimeError(f'live desired verification failed: {name}')
    return {
        'schema': 1, 'timestamp_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'run_id': run_id, 'git_commit': commit, 'build_fingerprint': fingerprint,
        'steam': probe, 'source': source, 'downloaded_bytes': source['downloaded_bytes'],
        'stock_locres': build['stock_input_validation'], 'translation_counts': build['counts'],
        'dynamic_classification': {name: item['classification'] for name, item in build['resources'].items()},
        'placeholder_printf_richtext_validation': build['translation_validation'], 'tests': tests,
        'repak_validation': build['package']['list_info_unpack'],
        'final_pak': {'path': 'ASA_RU_Fix_P.pak', 'size': build['pak_size'], 'sha256': build['pak_sha256']},
        'previous_stable_pak_sha256': previous_sha, 'pak_changed': build['pak_sha256'] != previous_sha,
        'release_created': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-report", type=Path, default=ROOT / "work/build_validation.json")
    parser.add_argument("--output", type=Path, default=ROOT / "work/cloud-build-report.json")
    parser.add_argument("--log", type=Path, default=ROOT / "work/cloud-validation.log")
    args = parser.parse_args()

    build = json.loads(args.build_report.read_text(encoding="utf-8"))
    tests = run_tests(args.log)
    report = make_report(build, tests, commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Unit tests: {tests['result']} ({tests['count']})")
    print(f"Cloud report: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"CLOUD REPORT ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
