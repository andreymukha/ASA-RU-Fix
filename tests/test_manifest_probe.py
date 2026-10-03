import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.manifest_probe import main, probe_manifest


MANIFEST = "3251368963427721326"
TEXT = (
    "Content Manifest for Depot 2430931 \n\n"
    f"Manifest ID / date     : {MANIFEST} / 10/03/2026 00:00:00 \n"
    "Total number of files  : 1 \n"
    "Total number of chunks : 1 \n"
    "Total bytes on disk    : 123456 \n"
    "Total bytes compressed : 65432 \n\n\n"
    "          Size Chunks File SHA                                 Flags Name\n"
    "        123456      1 " + "a" * 40 + "     0 ShooterGame/example.pak\n"
)
OUTPUT = "Using app branch: 'public'.\nTotal downloaded: 0 bytes (0 bytes uncompressed) from 1 depots\n"


class ManifestProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / "DepotDownloader.exe"
        self.exe.touch()
        self.work = self.root / "probe"

    def runner(self, *, text=TEXT, output=OUTPUT, returncode=0, extra=None,
               version="3.4.0+abc", manifest_id=MANIFEST):
        def run(command, **kwargs):
            self.assertEqual(command[0], str(self.exe.resolve()))
            self.assertTrue(kwargs["capture_output"])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertGreater(kwargs["timeout"], 0)
            cwd = Path(kwargs["cwd"])
            self.assertEqual(cwd.parent, self.work.resolve())
            if command[1:] == ["--version"]:
                self.assertEqual(list(cwd.iterdir()), [])
                return SimpleNamespace(returncode=0, stdout=f"DepotDownloader v{version}\n", stderr="")
            self.assertIn("-manifest-only", command)
            self.assertNotIn("-manifest", command)
            for forbidden in ("-filelist", "-username", "-password", "-validate"):
                self.assertNotIn(forbidden, command)
            for flag, value in (("-app", "2430930"), ("-depot", "2430931"), ("-branch", "public")):
                self.assertEqual(command[command.index(flag) + 1], value)
            content = Path(command[command.index("-dir") + 1])
            self.assertEqual(content.parent, cwd)
            self.assertFalse(content.exists())
            content.mkdir()
            if text is not None:
                (content / f"manifest_2430931_{manifest_id}.txt").write_bytes(text.encode("utf-8"))
            if extra:
                extra(content)
            return SimpleNamespace(returncode=returncode, stdout=output, stderr="")
        return Mock(side_effect=run)

    def test_current_public_manifest_only_command_and_exact_metadata(self):
        run = self.runner()
        report = probe_manifest(self.exe, self.work, run=run)
        self.assertEqual(report["app_id"], "2430930")
        self.assertEqual(report["depot_id"], "2430931")
        self.assertEqual(report["manifest_id"], MANIFEST)
        self.assertEqual(report["downloaded_bytes"], 0)
        self.assertGreater(report["metadata_bytes_on_disk"], 0)
        self.assertNotIn("server_build_id", report)
        self.assertEqual(datetime.fromisoformat(report["checked_at"].replace("Z", "+00:00")).tzinfo, timezone.utc)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_stale_manifest_is_never_used(self):
        self.work.mkdir()
        stale = self.work / f"manifest_2430931_{MANIFEST}.txt"
        stale.write_text(TEXT)
        with self.assertRaisesRegex(RuntimeError, "manifest text"):
            probe_manifest(self.exe, self.work, run=self.runner(text=None))
        self.assertTrue(stale.is_file())

    def test_missing_executable_fails_without_running(self):
        run = Mock()
        with self.assertRaisesRegex(RuntimeError, "missing"):
            probe_manifest(self.root / "missing.exe", self.work, run=run)
        run.assert_not_called()

    def test_unsupported_version_fails_before_manifest_request(self):
        for version in ("3.3.0", "3.4.1", "4.0.0", "unknown"):
            with self.subTest(version=version):
                run = self.runner(version=version)
                with self.assertRaisesRegex(RuntimeError, "3.4.0"):
                    probe_manifest(self.exe, self.work, run=run)
                self.assertEqual(run.call_count, 1)

    def test_missing_or_ambiguous_version_output_fails_before_manifest_request(self):
        for output in ("Runtime: .NET 9", "DepotDownloader v3.4.0\nDepotDownloader v3.4.0\n"):
            with self.subTest(output=output):
                run = Mock(return_value=SimpleNamespace(returncode=0, stdout=output, stderr=""))
                with self.assertRaisesRegex(RuntimeError, "3.4.0"):
                    probe_manifest(self.exe, self.work, run=run)
                self.assertEqual(run.call_count, 1)

    def test_nonzero_exit_and_process_failure_are_errors(self):
        with self.assertRaisesRegex(RuntimeError, "Steam unavailable"):
            probe_manifest(self.exe, self.work, run=self.runner(returncode=1, output="Steam unavailable"))
        for error in (OSError("cannot launch"), subprocess.TimeoutExpired("DepotDownloader", 1)):
            with self.subTest(error=error):
                with self.assertRaises(RuntimeError):
                    probe_manifest(self.exe, self.work, run=Mock(side_effect=error))

    def test_stdout_cannot_replace_manifest_text(self):
        with self.assertRaisesRegex(RuntimeError, "manifest text"):
            probe_manifest(self.exe, self.work, run=self.runner(text=None, output=f"Manifest {MANIFEST}\n" + OUTPUT))

    def test_wrong_depot_mismatch_malformed_duplicate_and_zero_ids_fail(self):
        invalid = [
            TEXT.replace("Depot 2430931", "Depot 111"),
            TEXT.replace(MANIFEST, "123"),
            TEXT.replace("Manifest ID / date     :", "Manifest:"),
            TEXT + f"Manifest ID / date     : {MANIFEST} / now\n",
            TEXT.replace(MANIFEST, "0"),
            TEXT.replace(MANIFEST, str(1 << 64)),
            TEXT.replace("Total bytes compressed", "Unknown metadata field"),
        ]
        for text in invalid:
            with self.subTest(text=text):
                with self.assertRaises(RuntimeError):
                    probe_manifest(self.exe, self.work, run=self.runner(text=text))

    def test_utf8_bom_and_windows_newlines_are_supported(self):
        report = probe_manifest(self.exe, self.work, run=self.runner(text="\ufeff" + TEXT.replace("\n", "\r\n")))
        self.assertEqual(report["manifest_id"], MANIFEST)

    def test_matching_filename_and_header_still_require_valid_uint64_id(self):
        for manifest_id in ("0", str((1 << 64) - 1), str(1 << 64), "1" * 21):
            with self.subTest(length=len(manifest_id)):
                with self.assertRaisesRegex(RuntimeError, "invalid"):
                    probe_manifest(self.exe, self.work, run=self.runner(
                        text=TEXT.replace(MANIFEST, manifest_id), manifest_id=manifest_id,
                    ))

    def test_multiple_fresh_manifest_files_are_ambiguous(self):
        def extra(content):
            (content / "manifest_2430931_123.txt").write_text(TEXT.replace(MANIFEST, "123"))
        with self.assertRaisesRegex(RuntimeError, "manifest text"):
            probe_manifest(self.exe, self.work, run=self.runner(extra=extra))

    def test_missing_nonzero_or_duplicate_download_summaries_fail(self):
        for output in ("", OUTPUT.replace("0 bytes (", "1 bytes ("),
                       OUTPUT.replace("0 bytes uncompressed", "1 bytes uncompressed"),
                       OUTPUT.replace("1 depots", "2 depots"), OUTPUT + OUTPUT):
            with self.subTest(output=output):
                with self.assertRaisesRegex(RuntimeError, "download summary"):
                    probe_manifest(self.exe, self.work, run=self.runner(output=output))

    def test_unconsumed_manifest_only_argument_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "not used"):
            probe_manifest(self.exe, self.work, run=self.runner(output=OUTPUT + "Argument #8 -manifest-only was not used.\n"))

    def test_existing_pak_anywhere_in_work_root_fails_before_run(self):
        pak = self.work / "nested" / "old.PAK"
        pak.parent.mkdir(parents=True)
        pak.touch()
        run = Mock()
        with self.assertRaisesRegex(RuntimeError, "PAK"):
            probe_manifest(self.exe, self.work, run=run)
        run.assert_not_called()
        self.assertTrue(pak.exists())

    def test_unexpected_downloaded_pak_is_rejected_and_fresh_directory_cleaned(self):
        with self.assertRaisesRegex(RuntimeError, "PAK"):
            probe_manifest(self.exe, self.work, run=self.runner(extra=lambda content: (content / "bad.PAK").touch()))
        self.assertEqual(list(self.work.iterdir()), [])

    def test_cli_writes_requested_json(self):
        report = {"app_id": "2430930", "depot_id": "2430931", "manifest_id": MANIFEST,
                  "downloaded_bytes": 0, "checked_at": "2026-10-03T00:00:00Z"}
        output = self.root / "nested" / "result.json"
        with patch("tools.manifest_probe.probe_manifest", return_value=report) as probe:
            self.assertEqual(main(["--output", str(output)]), 0)
        self.assertEqual(json.loads(output.read_text()), report)
        executable, work_root = probe.call_args.args
        self.assertEqual(executable.parts[-3:], ("tools", "depotdownloader", "DepotDownloader.exe"))
        self.assertEqual(work_root.parts[-2:], ("work", "manifest-probe"))

    def test_cli_failure_preserves_existing_result_and_exits_nonzero(self):
        output = self.root / "result.json"
        output.write_text("old result")
        errors = io.StringIO()
        with patch("tools.manifest_probe.probe_manifest", side_effect=RuntimeError("Steam unavailable")):
            with contextlib.redirect_stderr(errors):
                self.assertEqual(main(["--output", str(output)]), 1)
        self.assertIn("Steam unavailable", errors.getvalue())
        self.assertEqual(output.read_text(), "old result")


if __name__ == "__main__":
    unittest.main()
