using AsaRuFix.Core;
using Microsoft.Win32;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace AsaRuFix.App;

public sealed class WindowsPlatform : IClientPlatform
{
    public const string OwnerMarker = "ASA-RU-Fix.Client";
    private const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\ASA-RU-Fix";
    private static readonly string[] SteamProcesses = ["steam", "steamwebhelper"];
    private static readonly string[] GameProcesses = ["ArkAscended", "ArkAscended_BE", "ShooterGame"];

    public bool IsSteamRunning(string steamRoot) => IsRunning(steamRoot, false);
    public bool IsGameRunning(string gameRoot) => IsRunning(gameRoot, true);

    public void Register(string installedExe, string version)
    {
        installedExe = Path.GetFullPath(installedExe);
        if (!PathsEqual(installedExe, AppPaths.Default.Executable) || !File.Exists(installedExe))
            throw new InvalidOperationException("Регистрация разрешена только для установленного ASA-RU-Fix.exe.");
        if (!Version.TryParse(version, out _)) throw new ArgumentException("Некорректная версия updater.", nameof(version));
        using (var existing = Registry.CurrentUser.OpenSubKey(UninstallKey, false))
        {
            if (existing is not null && !OwnedRegistration(existing.GetValue("AsaRuFixOwner") as string, existing.GetValue("InstallLocation") as string, installedExe))
                throw new InvalidOperationException("Запись Installed Apps занята другой установкой.");
        }
        WriteShortcut(installedExe);
        using var key = Registry.CurrentUser.CreateSubKey(UninstallKey, true) ?? throw new IOException("Не удалось зарегистрировать updater.");
        key.SetValue("AsaRuFixOwner", OwnerMarker, RegistryValueKind.String);
        key.SetValue("DisplayName", "ASA RU Fix", RegistryValueKind.String);
        key.SetValue("Publisher", "Andrey / ASA RU Fix", RegistryValueKind.String);
        key.SetValue("DisplayVersion", version, RegistryValueKind.String);
        key.SetValue("InstallLocation", Path.GetDirectoryName(installedExe)!, RegistryValueKind.String);
        key.SetValue("DisplayIcon", installedExe + ",0", RegistryValueKind.String);
        key.SetValue("UninstallString", GameCommandBuilder.Quote(installedExe) + " --uninstall", RegistryValueKind.String);
        key.SetValue("NoModify", 1, RegistryValueKind.DWord);
        key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        key.Flush();
    }

    public void Unregister()
    {
        string exe = AppPaths.Default.Executable;
        bool registered;
        using (var existing = Registry.CurrentUser.OpenSubKey(UninstallKey, false))
        {
            registered = existing is not null;
            if (registered && !OwnedRegistration(existing!.GetValue("AsaRuFixOwner") as string, existing.GetValue("InstallLocation") as string, exe))
                throw new InvalidOperationException("Запись Installed Apps не принадлежит этой установке и сохранена.");
        }
        RemoveShortcut(exe);
        if (registered) Registry.CurrentUser.DeleteSubKeyTree(UninstallKey, false);
    }

    /// <summary>Pure ownership check; an unreadable known process blocks writes conservatively.</summary>
    public static bool ProcessMatches(string processName, string? executablePath, string root, bool game)
    {
        var names = game ? GameProcesses : SteamProcesses;
        bool knownName = names.Contains(processName, StringComparer.OrdinalIgnoreCase);
        if (!game && !knownName) return false;
        if (string.IsNullOrWhiteSpace(executablePath)) return knownName;
        if (string.IsNullOrWhiteSpace(root)) return false;
        try
        {
            string prefix = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root)) + Path.DirectorySeparatorChar;
            return Path.GetFullPath(executablePath).StartsWith(prefix, StringComparison.OrdinalIgnoreCase);
        }
        catch (Exception error) when (error is ArgumentException or NotSupportedException or PathTooLongException)
        { return knownName; }
    }

    public static bool OwnedRegistration(string? owner, string? installLocation, string expectedExe) =>
        owner == OwnerMarker && installLocation is not null && PathsEqual(installLocation, Path.GetDirectoryName(expectedExe)!);

    /// <summary>The caller obtains user consent before requesting this graceful shutdown.</summary>
    public static async Task<bool> ShutdownSteamAsync(string steamRoot, CancellationToken cancellation = default)
    {
        cancellation.ThrowIfCancellationRequested();
        var platform = new WindowsPlatform();
        if (!platform.IsSteamRunning(steamRoot)) return true;
        string executable = SteamExecutable(steamRoot);
        using var request = Process.Start(new ProcessStartInfo(executable)
        {
            Arguments = "-shutdown", WorkingDirectory = Path.GetDirectoryName(executable)!,
            UseShellExecute = false, CreateNoWindow = true
        }) ?? throw new IOException("Не удалось запросить завершение Steam.");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(TimeSpan.FromSeconds(30));
        try
        {
            while (platform.IsSteamRunning(steamRoot)) await Task.Delay(200, deadline.Token);
            return true;
        }
        catch (OperationCanceledException) when (!cancellation.IsCancellationRequested) { return false; }
    }

    public static void RestartSteam(string steamRoot)
    {
        if (new WindowsPlatform().IsSteamRunning(steamRoot)) return;
        string executable = SteamExecutable(steamRoot);
        using var process = Process.Start(new ProcessStartInfo(executable)
        {
            WorkingDirectory = Path.GetDirectoryName(executable)!, UseShellExecute = false
        }) ?? throw new IOException("Не удалось запустить Steam.");
    }

    private static bool IsRunning(string root, bool game)
    {
        foreach (string? selectedName in game ? new string?[] { null } : SteamProcesses)
        {
            Process[] processes;
            try { processes = selectedName is null ? Process.GetProcesses() : Process.GetProcessesByName(selectedName); }
            catch (Exception error) when (error is Win32Exception or InvalidOperationException) { return true; }
            try
            {
                foreach (var process in processes)
                {
                    string name = selectedName ?? "";
                    string? path;
                    try
                    {
                        if (selectedName is null) name = process.ProcessName;
                        if (process.HasExited) continue;
                        path = process.MainModule?.FileName;
                    }
                    catch (InvalidOperationException) { continue; }
                    catch (Win32Exception) { path = null; }
                    if (ProcessMatches(name, path, root, game)) return true;
                }
            }
            finally { foreach (var process in processes) process.Dispose(); }
        }
        return false;
    }

    private static string SteamExecutable(string root)
    {
        if (string.IsNullOrWhiteSpace(root)) throw new ArgumentException("Не найден каталог Steam.", nameof(root));
        string executable = Path.GetFullPath(Path.Combine(root, "steam.exe"));
        if (!File.Exists(executable)) throw new FileNotFoundException("Не найден steam.exe.", executable);
        return executable;
    }

    private static string ShortcutPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "ASA RU Fix.lnk");

    private static void WriteShortcut(string exe)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(ShortcutPath)!);
        WithShortcut(shortcut =>
        {
            if (File.Exists(ShortcutPath) && !OwnedShortcut(shortcut, exe)) throw new InvalidOperationException("Ярлык ASA RU Fix принадлежит другой команде и сохранён.");
            shortcut.TargetPath = exe;
            shortcut.Arguments = "";
            shortcut.WorkingDirectory = Path.GetDirectoryName(exe)!;
            shortcut.Description = "Русский перевод ARK: Survival Ascended";
            shortcut.IconLocation = exe + ",0";
            shortcut.Save();
        });
    }

    private static void RemoveShortcut(string exe)
    {
        if (!File.Exists(ShortcutPath)) return;
        bool owned = false;
        WithShortcut(shortcut => owned = OwnedShortcut(shortcut, exe));
        if (owned) File.Delete(ShortcutPath);
    }

    private static bool OwnedShortcut(dynamic shortcut, string exe) => PathsEqual((string)shortcut.TargetPath, exe) && string.IsNullOrEmpty((string)shortcut.Arguments);

    private static void WithShortcut(Action<dynamic> action)
    {
        object? shell = null;
        object? shortcut = null;
        try
        {
            Type type = Type.GetTypeFromProgID("WScript.Shell", true)!;
            shell = Activator.CreateInstance(type) ?? throw new IOException("Не удалось открыть Windows Shell.");
            shortcut = ((dynamic)shell).CreateShortcut(ShortcutPath);
            action(shortcut);
        }
        finally
        {
            if (shortcut is not null && Marshal.IsComObject(shortcut)) Marshal.FinalReleaseComObject(shortcut);
            if (shell is not null && Marshal.IsComObject(shell)) Marshal.FinalReleaseComObject(shell);
        }
    }

    private static bool PathsEqual(string left, string right)
    {
        try { return string.Equals(Path.TrimEndingDirectorySeparator(Path.GetFullPath(left)), Path.TrimEndingDirectorySeparator(Path.GetFullPath(right)), StringComparison.OrdinalIgnoreCase); }
        catch (Exception error) when (error is ArgumentException or NotSupportedException or PathTooLongException) { return false; }
    }
}
