using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using AsaRuFix.Core;

namespace AsaRuFix.App;

internal static class SelfUpdateHelper
{
    private static string PendingPath => Path.Combine(AppRuntime.Paths.Updates, "new.pending.exe");
    private static string MetadataPath => Path.Combine(AppRuntime.Paths.Updates, "pending.json");

    internal static async Task<PendingSelfUpdate?> StageAndSaveAsync(ChannelClient client, string currentVersion, CancellationToken cancellationToken)
    {
        var pending = await new SelfUpdater(client).StageAsync(currentVersion, AppRuntime.Paths.Updates, cancellationToken).ConfigureAwait(false);
        if (pending is not null)
        {
            ValidatePending(pending);
            ConfigStore.SaveJson(MetadataPath, pending);
        }
        return pending;
    }

    internal static void StartCompletion(PendingSelfUpdate pending, bool restart)
    {
        ValidatePending(pending);
        if (SemVersion.Parse(pending.Version).CompareTo(SemVersion.Parse(AppRuntime.Version)) <= 0)
            throw new InvalidDataException("Отложенная версия updater не новее текущей.");
        var start = new ProcessStartInfo(PendingPath) { UseShellExecute = false, WorkingDirectory = AppRuntime.Paths.Root };
        start.ArgumentList.Add("--complete-self-update");
        start.ArgumentList.Add(Environment.ProcessId.ToString(CultureInfo.InvariantCulture));
        if (restart) start.ArgumentList.Add("--restart");
        using var helper = Process.Start(start) ?? throw new IOException("Не удалось запустить helper обновления updater.");
    }

    internal static async Task CompleteAsync(int oldPid, bool restart)
    {
        if (oldPid <= 0 || oldPid == Environment.ProcessId) throw new InvalidDataException("Некорректный PID предыдущего updater.");
        if (!SamePath(Environment.ProcessPath, PendingPath))
            throw new InvalidDataException("Self-update helper должен выполняться из фиксированного pending EXE.");
        var pending = ReadPending();
        ValidatePending(pending);
        if (pending.Version != AppRuntime.Version || ReadFileVersion(PendingPath) != pending.Version)
            throw new InvalidDataException("Версия выполняемого helper не соответствует отложенному обновлению.");
        await WaitForPreviousUpdaterAsync(oldPid).ConfigureAwait(false);

        using var lease = UserMutex.TryAcquire(AppRuntime.MutexName, TimeSpan.FromSeconds(60))
            ?? throw new TimeoutException("Updater уже выполняет другую операцию.");
        // Re-read and verify after the wait: another updater may have changed staged files.
        var latest = ReadPending();
        if (latest != pending) throw new InvalidDataException("Отложенное обновление изменилось во время ожидания.");
        ValidatePending(latest);
        var store = new ConfigStore(AppRuntime.Paths);
        var config = store.Load() ?? throw new InvalidDataException("Не найдена рабочая конфигурация установленного updater.");
        if (SemVersion.Parse(config.UpdaterVersion).CompareTo(SemVersion.Parse(pending.Version)) > 0 ||
            SemVersion.Parse(ReadFileVersion(AppRuntime.Paths.Executable)).CompareTo(SemVersion.Parse(pending.Version)) > 0)
            throw new InvalidDataException("Self-update не может понижать установленную версию.");
        IClientPlatform platform = new WindowsPlatform();
        EnsureGameClosed();
        SelfUpdater.Complete(pending, AppRuntime.Paths.Executable, EnsureGameClosed);
        config.UpdaterVersion = pending.Version;
        store.Save(config);
        platform.Register(AppRuntime.Paths.Executable, pending.Version);
        lease.Dispose();
        if (restart)
        {
            using var started = Process.Start(new ProcessStartInfo(AppRuntime.Paths.Executable)
            { UseShellExecute = false, WorkingDirectory = AppRuntime.Paths.Root })
                ?? throw new IOException("Не удалось перезапустить обновлённый updater.");
        }

        void EnsureGameClosed()
        {
            if (platform.IsGameRunning(config.GamePath)) throw new InvalidOperationException("Закройте ARK и повторите обновление updater.");
        }
    }

    internal static void CleanupCompleted()
    {
        if (!SamePath(Environment.ProcessPath, AppRuntime.Paths.Executable) || !File.Exists(MetadataPath)) return;
        using var lease = UserMutex.TryAcquire(AppRuntime.MutexName, TimeSpan.Zero);
        if (lease is null) return;
        var pending = ReadPending();
        if (SemVersion.Parse(pending.Version).CompareTo(SemVersion.Parse(AppRuntime.Version)) > 0) return;
        if (!SamePath(pending.FilePath, PendingPath)) throw new InvalidDataException("Неверный путь отложенного обновления.");
        // The installed updater cleans this only after the helper has finished executing.
        try { if (File.Exists(PendingPath)) File.Delete(PendingPath); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { return; }
        File.Delete(MetadataPath);
    }

    private static PendingSelfUpdate ReadPending()
    {
        if (new FileInfo(MetadataPath).Length > 128 * 1024) throw new InvalidDataException("Отложенное обновление имеет слишком большой metadata файл.");
        return JsonSerializer.Deserialize<PendingSelfUpdate>(File.ReadAllText(MetadataPath), ConfigStore.JsonOptions)
            ?? throw new InvalidDataException("Некорректные metadata отложенного обновления.");
    }

    private static void ValidatePending(PendingSelfUpdate pending)
    {
        SemVersion.Parse(pending.Version);
        if (!SamePath(pending.FilePath, PendingPath)) throw new InvalidDataException("Неверный путь отложенного обновления.");
        if (pending.Size <= 0 || pending.Size > 512L * 1024 * 1024 ||
            new FileInfo(PendingPath).Length != pending.Size ||
            !string.Equals(AtomicFile.Sha256(PendingPath), pending.Sha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Размер или SHA-256 pending EXE не соответствует metadata.");
    }

    private static async Task WaitForPreviousUpdaterAsync(int oldPid)
    {
        Process process;
        try { process = Process.GetProcessById(oldPid); }
        catch (ArgumentException) { return; }
        using (process)
        {
            if (process.HasExited) return;
            string? executable;
            try { executable = process.MainModule?.FileName; }
            catch (InvalidOperationException) when (process.HasExited) { return; }
            if (!SamePath(executable, AppRuntime.Paths.Executable))
                throw new InvalidDataException("PID не принадлежит установленному updater.");
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(60));
            try { await process.WaitForExitAsync(timeout.Token).ConfigureAwait(false); }
            catch (OperationCanceledException) { throw new TimeoutException("Предыдущий updater не завершился за 60 секунд."); }
        }
    }

    private static string ReadFileVersion(string path)
    {
        var info = FileVersionInfo.GetVersionInfo(path);
        if (info.FilePrivatePart != 0 || info.FileMajorPart < 0 || info.FileMinorPart < 0 || info.FileBuildPart < 0)
            throw new InvalidDataException("Некорректная file version updater.");
        return $"{info.FileMajorPart}.{info.FileMinorPart}.{info.FileBuildPart}";
    }

    private static bool SamePath(string? left, string right) => left is not null &&
        string.Equals(Path.GetFullPath(left), Path.GetFullPath(right), StringComparison.OrdinalIgnoreCase);
}
