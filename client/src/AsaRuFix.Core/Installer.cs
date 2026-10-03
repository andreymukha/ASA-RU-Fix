namespace AsaRuFix.Core;

public interface IClientPlatform
{
    bool IsSteamRunning(string steamRoot);
    bool IsGameRunning(string gameRoot);
    void Register(string installedExe, string version);
    void Unregister();
}

public sealed class Installer(ConfigStore store, IClientPlatform platform,
    Func<string, CancellationToken, Task<(string Version, string Sha256)>> updatePak)
{
    public async Task InstallAsync(SteamInstallation steam, SteamUser user, string sourceExe,
                                  string version, CancellationToken cancellation)
    {
        if (platform.IsGameRunning(steam.GamePath ?? "")) throw new InvalidOperationException("Закройте ARK и повторите установку/обновление.");
        if (platform.IsSteamRunning(steam.SteamPath)) throw new InvalidOperationException("Для настройки запуска ARK необходимо перезапустить Steam.");
        if (steam.GamePath is null || !SteamDiscovery.IsGameDirectory(steam.GamePath))
            throw new InvalidOperationException("Не найдена папка ARK: Survival Ascended.");
        if (!steam.Users.Any(candidate => candidate.AccountId == user.AccountId && candidate.LocalConfigPath == user.LocalConfigPath))
            throw new InvalidOperationException("Выбранный профиль Steam не подтверждён.");
        var current = LaunchOptionsManager.Read(user.LocalConfigPath);
        var managed = LaunchOptionsManager.Managed(store.Paths.Executable);
        var config = store.Load();
        var previous = config?.Integrations.FirstOrDefault(item => item.AccountId == user.AccountId && item.LocalConfigPath == user.LocalConfigPath);
        string? original;
        if (previous is not null && current == previous.ManagedLaunchOptions) original = previous.OriginalLaunchOptions;
        else if (current?.Contains("ASA-RU-Fix.exe", StringComparison.OrdinalIgnoreCase) == true)
        {
            if (previous is null) throw new InvalidOperationException("Обнаружена интеграция без сохранённых исходных параметров. Автоматическое восстановление небезопасно.");
            original = LaunchOptionsManager.Restore(current, previous.ManagedLaunchOptions, previous.OriginalLaunchOptions);
        }
        else original = current;
        GameCommandBuilder.ValidateOriginal(original ?? "");
        if (config is not null && Version.Parse(config.UpdaterVersion) > Version.Parse(version))
            throw new InvalidOperationException("Установленная версия updater новее скачанного файла.");
        Directory.CreateDirectory(store.Paths.Root);
        if (!string.Equals(Path.GetFullPath(sourceExe), store.Paths.Executable, StringComparison.OrdinalIgnoreCase))
            AtomicFile.InstallVerified(sourceExe, store.Paths.Executable, new FileInfo(sourceExe).Length, AtomicFile.Sha256(sourceExe));
        config ??= new();
        config.UpdaterVersion = version; config.SteamPath = steam.SteamPath;
        config.SteamAccountId = user.AccountId; config.SteamLocalConfigPath = user.LocalConfigPath;
        config.GamePath = steam.GamePath; config.OriginalLaunchOptions = original;
        config.ManagedLaunchOptions = managed;
        config.Integrations.RemoveAll(item => item.AccountId == user.AccountId && item.LocalConfigPath == user.LocalConfigPath);
        config.Integrations.Add(new() { AccountId=user.AccountId, LocalConfigPath=user.LocalConfigPath,
            OriginalLaunchOptions=original, ManagedLaunchOptions=managed });
        // Durable recovery information precedes ANY write to Steam LaunchOptions.
        store.Save(config);
        var pak = await updatePak(config.GamePath, cancellation);
        if (platform.IsGameRunning(config.GamePath)) throw new InvalidOperationException("Закройте ARK и повторите установку/обновление.");
        if (LaunchOptionsManager.Read(user.LocalConfigPath) != current)
            throw new InvalidOperationException("Параметры Steam изменились во время установки. Повторите проверку.");
        LaunchOptionsManager.Write(user.LocalConfigPath, managed, () => platform.IsSteamRunning(steam.SteamPath));
        platform.Register(store.Paths.Executable, version);
        store.SaveState(new() { TranslationVersion=pak.Version, TranslationSha256=pak.Sha256, CheckedAt=DateTimeOffset.UtcNow.ToString("O") });
    }
}
