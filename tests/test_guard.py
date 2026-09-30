import unittest
from standalone_build import ROOT, audit, check, processes


class GuardTests(unittest.TestCase):
    def test_windows_subprocess_audit(self):
        before = len(processes)
        audit('subprocess.Popen', (None, f'"{ROOT / "work/tools/repak.exe"}" info test.pak', None, None))
        self.assertEqual(len(processes), before + 1)

    def test_forbidden_access_and_executable(self):
        for path in (r'D:\ARKDevkit', r'D:\ARKDevkit\UnrealPak.exe', 'tests.compare_devkit'):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                check(path)
        with self.assertRaises(RuntimeError):
            audit('subprocess.Popen', (None, 'cmd.exe /c echo forbidden', None, None))
