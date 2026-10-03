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
    if build.get("counts") != {"corrections": 1200, "additions": 43, "engine_edits": 21}:
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
