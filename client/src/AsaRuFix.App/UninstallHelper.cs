using System.Diagnostics;
using AsaRuFix.Core;

namespace AsaRuFix.App;

internal static class UninstallHelper
{
    public static string Prepare()
    {
        var root = Path.Combine(Path.GetTempPath(), "ASA-RU-Fix-uninstall-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var helper = Path.Combine(root, "ASA-RU-Fix.exe");
        var source = Environment.ProcessPath!;
        AtomicFile.InstallVerified(source, helper, new FileInfo(source).Length, AtomicFile.Sha256(source));
        return helper;
    }
    public static void Start(string helper) => Process.Start(new ProcessStartInfo(helper, "--complete-uninstall " + Environment.ProcessId) { UseShellExecute = false });

    public static void RemovePrepared(string helper)
    {
        try { File.Delete(helper); Directory.Delete(Path.GetDirectoryName(helper)!); }
        catch (IOException) { /* A started helper owns its cleanup. */ }
    }

    public static async Task CompleteAsync(int oldPid)
    {
        var executable = Environment.ProcessPath!;
        string helperRoot = Path.GetDirectoryName(executable)!;
        string name = Path.GetFileName(helperRoot);
        if (Path.GetDirectoryName(helperRoot) != Path.TrimEndingDirectorySeparator(Path.GetFullPath(Path.GetTempPath())) ||
            !name.StartsWith("ASA-RU-Fix-uninstall-", StringComparison.Ordinal) ||
            !Guid.TryParseExact(name["ASA-RU-Fix-uninstall-".Length..], "N", out _) || Path.GetFileName(executable) != "ASA-RU-Fix.exe")
            throw new InvalidOperationException("Неверный путь uninstall helper.");
        if (oldPid <= 0 || oldPid == Environment.ProcessId) throw new InvalidOperationException("Неверный PID updater.");
        try
        {
            await PreviousProcess.WaitAsync(oldPid, AppRuntime.Paths.Executable, TimeSpan.FromSeconds(60));
            using var lease = UserMutex.TryAcquire(AppRuntime.MutexName, TimeSpan.FromSeconds(5))
                ?? throw new InvalidOperationException("Updater занят; удаление остановлено.");
            var store = new ConfigStore(AppRuntime.Paths);
            var config = store.Load() ?? throw new InvalidOperationException("Нет подтверждённых данных удаления.");
            var platform = new WindowsPlatform();
            if (platform.IsGameRunning(config.GamePath)) throw new InvalidOperationException("Игра запущена; updater сохранён.");
            foreach (var profile in config.Integrations)
                if (LaunchOptionsManager.Read(profile.LocalConfigPath)?.Contains("ASA-RU-Fix.exe", StringComparison.OrdinalIgnoreCase) == true)
                    throw new InvalidOperationException("Steam всё ещё ссылается на updater; файл сохранён.");
            // Fixed owned files only. Unknown user-created files are never recursively deleted.
            foreach (var file in new[] { AppRuntime.Paths.Executable, AppRuntime.Paths.Config, AppRuntime.Paths.Config + ".backup", AppRuntime.Paths.State }) File.Delete(file);
            foreach (var directory in new[] { AppRuntime.Paths.Logs, AppRuntime.Paths.Updates })
                if (Directory.Exists(directory))
                {
                    foreach (var file in Directory.EnumerateFiles(directory)) File.Delete(file);
                    if (!Directory.EnumerateFileSystemEntries(directory).Any()) Directory.Delete(directory);
                }
            if (!Directory.EnumerateFileSystemEntries(AppRuntime.Paths.Root).Any()) Directory.Delete(AppRuntime.Paths.Root);
        }
        finally { using var reaper = SelfDeletion.Start(executable); }
    }
}
