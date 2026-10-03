import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from tools.locres import Entry, FString, Resource, serialize
from tools.cloud_report import make_report
from tools.server_depot import (
    EXPECTED_PAK_SHA256,
    PINNED_MANIFEST,
    PINNED_STOCK,
    download_server_pak,
    validate_stock_resources,
)


def locres(namespace: str, key: str = "key", *, version: int = 3) -> bytes:
    resource = Resource(
        version,
        [Entry(1, FString(namespace, False), 2, FString(key, False), 3, 0)],
        [FString("value", False)],
        [1],
    )
    return serialize(resource, {})


class StockValidationTests(unittest.TestCase):
    def test_each_input_is_checked_for_size_hash_version_and_entry_count(self):
        names = tuple(PINNED_STOCK)
        contents = {
            names[0]: locres("ShooterGame"),
            names[1]: locres("ShooterGame", "ru"),
            names[2]: locres("Engine"),
            names[3]: locres("Engine", "ru"),
        }
        specs = {
            name: {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "version": 3,
                "entries": 1,
            }
            for name, data in contents.items()
        }
        report = validate_stock_resources(contents, specs=specs)
        self.assertEqual(set(report), set(names))
        self.assertTrue(all(row["status"] == "PASS" for row in report.values()))

    def test_hash_mismatch_fails_before_build(self):
        name = next(iter(PINNED_STOCK))
        raw = locres("ShooterGame")
        specs = {name: {"size": len(raw), "sha256": "0" * 64, "version": 3, "entries": 1}}
        with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
            validate_stock_resources({name: raw}, specs=specs, require_all=False)

    def test_unexpected_locres_version_or_count_fails(self):
        name = next(iter(PINNED_STOCK))
        raw = locres("ShooterGame", version=2)
        spec = {name: {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                       "version": 3, "entries": 1}}
        with self.assertRaisesRegex(RuntimeError, "version"):
            validate_stock_resources({name: raw}, specs=spec, require_all=False)


class DepotDownloadTests(unittest.TestCase):
    def test_download_is_limited_to_the_pinned_manifest_and_one_pak(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe = root / "DepotDownloader.exe"
            exe.touch()
            download_bytes = 123456

            def run(command, **kwargs):
                args = command[1:]
                self.assertIn("-app", args)
                self.assertEqual(args[args.index("-app") + 1], "2430930")
                self.assertEqual(args[args.index("-depot") + 1], "2430931")
                self.assertEqual(args[args.index("-manifest") + 1], PINNED_MANIFEST)
                filelist = Path(args[args.index("-filelist") + 1])
                self.assertEqual(filelist.read_text(encoding="utf-8").strip(),
                                 "ShooterGame/Content/Paks/pakchunk0-WindowsServer.pak")
                self.assertNotIn("-username", args)
                output_dir = Path(args[args.index("-dir") + 1])
                target = output_dir / "ShooterGame/Content/Paks/pakchunk0-WindowsServer.pak"
                target.parent.mkdir(parents=True)
                target.write_bytes(b"pak")
                return SimpleNamespace(returncode=0, stdout=f"Total downloaded: {download_bytes} bytes\n", stderr="")

            result = download_server_pak(exe, root / "download", run=run)
            self.assertTrue(result["path"].is_file())
            self.assertEqual(result["downloaded_bytes"], download_bytes)
            self.assertEqual(result["manifest"], PINNED_MANIFEST)

    def test_download_failure_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe = root / "DepotDownloader.exe"
            exe.touch()
            run = Mock(return_value=SimpleNamespace(returncode=17, stdout="", stderr="Steam failure"))
            with self.assertRaisesRegex(RuntimeError, "Steam failure"):
                download_server_pak(exe, root / "download", run=run)


class DeterministicOutputTests(unittest.TestCase):
    def test_expected_production_hash_is_pinned(self):
        self.assertEqual(EXPECTED_PAK_SHA256,
                         "914589668aa41516915a68ef233873f4aeeedf570db70a7232e36ff9e8c04f2b")

    def test_cloud_report_requires_exact_successful_pinned_build(self):
        build = {
            "source": {"kind": "steam-dedicated-server", "app_id": "2430930",
                       "depot_id": "2430931", "manifest": PINNED_MANIFEST,
                       "downloaded_bytes": 12},
            "stock_input_validation": {name: {"status": "PASS"} for name in PINNED_STOCK},
            "counts": {"corrections": 1200, "additions": 43, "engine_edits": 21},
            "translation_validation": {"status": "PASS", "issues": 0},
            "package": {"list_info_unpack": "PASS"},
            "pak_size": 10_795_036,
            "pak_sha256": EXPECTED_PAK_SHA256,
            "deterministic_match": True,
        }
        tests = {"result": "PASS", "count": 75, "failures": 0, "errors": 0}
        report = make_report(build, tests, commit="c" * 40, timestamp="2026-10-03T00:00:00Z")
        self.assertEqual(report["git_commit"], "c" * 40)
        self.assertEqual(report["steam"]["downloaded_bytes"], 12)
        self.assertEqual(report["tests"]["count"], 75)
        build["pak_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "byte-identical"):
            make_report(build, tests, commit="c" * 40)


if __name__ == "__main__":
    unittest.main()
