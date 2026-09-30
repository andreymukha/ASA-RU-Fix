"""Run the actual production build while denying DevKit access and other executables.

The guard covers Python filesystem probes, audited file/DLL opens, directory
enumeration, optional reference imports, and process creation. Only the cached
repak executable is allowed to run. This is validation, never a build backend.
"""
import builtins
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPAK = os.path.normcase(str(ROOT / 'work/tools/repak.exe'))
DENIED = ('arkdevkit', 'unrealpak', 'epicgameslauncher', 'devkit_reference', 'compare_devkit')
violations = []
processes = []


def check(value):
    if isinstance(value, (str, bytes, os.PathLike)):
        text = os.fsdecode(value).lower().replace('\\', '/')
        if any(token in text for token in DENIED):
            violations.append(text)
            raise RuntimeError(f'Standalone guard denied: {text}')


def audit(event, args):
    if event in ('open', 'os.listdir', 'os.scandir', 'ctypes.dlopen'):
        check(args[0])
    if event == 'subprocess.Popen':
        check(args[0])
        executable = args[0]
        if executable is None:
            # Windows subprocess audits executable=None and a quoted command
            # line when invoked with an argument list. Allow only our exact
            # cached tool as its first token, without invoking a shell parser.
            prefix = f'"{ROOT / "work/tools/repak.exe"}" '
            if not isinstance(args[1], str) or not args[1].startswith(prefix):
                raise RuntimeError(f'Standalone guard rejected command line: {args[1]}')
            check(args[1])
            executable = str(ROOT / 'work/tools/repak.exe')
        if os.path.normcase(os.path.abspath(executable)) != REPAK:
            raise RuntimeError(f'Standalone guard rejected executable: {executable}')
        processes.append(str(executable))


def guarded(function):
    def call(path, *args, **kwargs):
        check(path)
        return function(path, *args, **kwargs)
    return call


def main():
    # Static proof includes every project module in the production build and
    # bootstrap. The optional test scripts are deliberately outside this list.
    production = ['build.py', 'tools/steam.py', 'tools/locres.py', 'tools/pakv12.py',
                  'tools/oodle.py', 'tools/bootstrap.py', 'tools/ooz_bridge.cpp', 'tools/corrections.py']
    for name in production:
        content = (ROOT / name).read_text(encoding='utf-8').lower()
        if any(word in content for word in ('devkit', 'unrealpak', 'epicgameslauncher')):
            raise RuntimeError(f'Production source still references a forbidden backend: {name}')
    print(f'Production source search: no DevKit/UnrealPak/Epic lookup in {len(production)} files', flush=True)
    sys.addaudithook(audit)
    for name in ('stat', 'lstat', 'access', 'listdir', 'scandir', 'readlink'):
        setattr(os, name, guarded(getattr(os, name)))
    original_import = builtins.__import__
    def import_checked(name, *args, **kwargs):
        check(name)
        return original_import(name, *args, **kwargs)
    builtins.__import__ = import_checked
    # Confirm the guard detects both a filesystem probe and a tool launch.
    for probe in (lambda: os.stat(r'D:\ARKDevkit'),
                  lambda: audit('subprocess.Popen', (r'D:\ARKDevkit\UnrealPak.exe',))):
        try:
            probe()
        except RuntimeError:
            pass
        else:
            raise RuntimeError('Standalone guard self-test failed')
    violations.clear()
    os.environ['ASA_UNREALPAK'] = r'D:\ARKDevkit\guard-must-reject\UnrealPak.exe'
    sys.argv = [str(ROOT / 'build.py'), *sys.argv[1:]]
    try:
        runpy.run_path(str(ROOT / 'build.py'), run_name='__main__')
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise
    if violations or len(processes) != 4:
        raise RuntimeError(f'Unexpected guarded build activity: violations={violations}, processes={processes}')
    print('Standalone build PASS: 0 forbidden accesses; 4 subprocesses, all cached repak; guard self-test PASS')


if __name__ == '__main__':
    main()
