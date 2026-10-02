import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")
CSCRIPT = shutil.which("cscript.exe")


@unittest.skipUnless(os.name == "nt" and POWERSHELL and CSCRIPT,
                     "Windows PowerShell and Windows Script Host are required")
class UpdateLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ASA RU update ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "project with spaces"
        self.project.mkdir()
        self.cwd = self.base / "different working directory"
        self.cwd.mkdir()

        self.ps_script = ROOT / "update.ps1"
        self.vbs_script = ROOT / "Обновить перевод.vbs"
        if self.ps_script.is_file():
            shutil.copy2(self.ps_script, self.project / self.ps_script.name)
        if self.vbs_script.is_file():
            shutil.copy2(self.vbs_script, self.project / self.vbs_script.name)

        (self.project / "build.py").write_text(
            "import os, sys\n"
            "print('BUILD_STDOUT')\n"
            "print('BUILD_STDERR', file=sys.stderr)\n"
            "raise SystemExit(int(os.environ['ASA_TEST_BUILD_EXIT']))\n",
            encoding="utf-8",
        )
        self.install_script = self.project / "install.ps1"
        self.fake_patch_target = self.project / "fake-game" / "ASA_RU_Fix_P.pak"
        self.fake_patch_target.parent.mkdir()
        self.fake_patch_target.write_text("original installed PAK", encoding="utf-8")
        self.install_script.write_text(
            "[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'install-ran.marker'), 'ran')\n"
            "[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'fake-game/ASA_RU_Fix_P.pak'), 'new installed PAK')\n"
            "Write-Output 'INSTALL_STDOUT'\n",
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        self.env["ASA_TEST_BUILD_EXIT"] = "0"

    def run_launcher(self, build_exit, install_text=None):
        self.env["ASA_TEST_BUILD_EXIT"] = str(build_exit)
        if install_text is not None:
            self.install_script.write_text(install_text, encoding="utf-8")
        return subprocess.run(
            [CSCRIPT, "//nologo", str(self.project / "Обновить перевод.vbs"), "/NoMessageBox"],
            cwd=self.cwd,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_success_builds_then_installs_and_logs_all_output(self):
        log = self.project / "work" / "update.log"
        log.parent.mkdir()
        log.write_text("STALE_LOG_CONTENT", encoding="utf-8")

        result = self.run_launcher(0)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.project / "install-ran.marker").is_file())
        self.assertEqual(self.fake_patch_target.read_text(encoding="utf-8"), "new installed PAK")
        output = log.read_text(encoding="utf-8-sig")
        self.assertNotIn("STALE_LOG_CONTENT", output)
        self.assertIn("BUILD_STDOUT", output)
        self.assertIn("BUILD_STDERR", output)
        self.assertIn("INSTALL_STDOUT", output)

    def test_build_failure_is_logged_returned_and_skips_install(self):
        result = self.run_launcher(17)

        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertFalse((self.project / "install-ran.marker").exists())
        self.assertEqual(self.fake_patch_target.read_text(encoding="utf-8"), "original installed PAK")
        output = (self.project / "work" / "update.log").read_text(encoding="utf-8-sig")
        self.assertIn("BUILD_STDOUT", output)
        self.assertIn("BUILD_STDERR", output)
        self.assertIn("17", output)

    def test_install_failure_is_logged_and_returns_nonzero(self):
        result = self.run_launcher(
            0,
            "Write-Output 'INSTALL_STARTED'\nthrow 'INSTALL_FAILURE_SENTINEL'\n",
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        output = (self.project / "work" / "update.log").read_text(encoding="utf-8-sig")
        self.assertIn("BUILD_STDOUT", output)
        self.assertIn("INSTALL_STARTED", output)
        self.assertIn("INSTALL_FAILURE_SENTINEL", output)

    def test_vbs_hides_and_waits_for_powershell_then_propagates_exit_code(self):
        source = self.vbs_script.read_text(encoding="utf-8")
        powershell_source = self.ps_script.read_text(encoding="utf-8-sig")

        self.assertIn("-WindowStyle Hidden", source)
        self.assertIn("shell.Run(command, 0, True)", source)
        self.assertIn("WScript.Quit exitCode", source)
        self.assertIn("ASA-RU-Fix — ошибка", powershell_source)
        self.assertIn("Не удалось пересобрать или установить перевод.", powershell_source)
        self.assertIn("Подробности:`r`n$LogPath", powershell_source)
        self.assertIn("Перевод успешно пересобран и установлен.", powershell_source)
        self.assertIn("Можно запускать ARK.", powershell_source)


if __name__ == "__main__":
    unittest.main()
