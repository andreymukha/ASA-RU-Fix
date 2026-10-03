namespace AsaRuFix.Core;

public sealed class Uninstaller(ConfigStore store, IClientPlatform platform)
{
    public void RemoveIntegrationAndData()
    {
        var config = store.Load() ?? throw new InvalidOperationException("Не найдены исходные параметры запуска. Updater не удалён: сначала восстановите интеграцию Steam.");
        if (platform.IsGameRunning(config.GamePath)) throw new InvalidOperationException("Закройте ARK и повторите удаление.");
        if (platform.IsSteamRunning(config.SteamPath)) throw new InvalidOperationException("Для настройки запуска ARK необходимо перезапустить Steam.");
        var changes = new List<(SteamProfileIntegration Profile, string? Current, string? Restored)>();
        foreach (var profile in config.Integrations)
        {
            var current = LaunchOptionsManager.Read(profile.LocalConfigPath);
            string? restored;
            if (current == profile.ManagedLaunchOptions) restored = profile.OriginalLaunchOptions;
            else if (current?.Contains("ASA-RU-Fix.exe", StringComparison.OrdinalIgnoreCase) != true) restored = current;
            else
            {
                try { restored = LaunchOptionsManager.Restore(current, profile.ManagedLaunchOptions, profile.OriginalLaunchOptions); }
                catch (Exception error) when (error is ArgumentException or InvalidOperationException or FormatException)
                { throw new InvalidOperationException("Параметры запуска изменены пользователем. Updater не удалён: безопасно убрать wrapper не удалось.", error); }
            }
            if (restored?.Contains("ASA-RU-Fix.exe", StringComparison.OrdinalIgnoreCase) == true)
                throw new InvalidOperationException("Steam всё ещё ссылается на updater. Удаление остановлено.");
            changes.Add((profile, current, restored));
        }
        if (changes.Count == 0) throw new InvalidOperationException("Нет подтверждённых данных интеграции; updater не удалён.");
        foreach (var change in changes)
        {
            if (LaunchOptionsManager.Read(change.Profile.LocalConfigPath) != change.Current)
                throw new InvalidOperationException("Настройки Steam изменились во время удаления.");
            if (change.Current != change.Restored)
                LaunchOptionsManager.Write(change.Profile.LocalConfigPath, change.Restored, () => platform.IsSteamRunning(config.SteamPath));
        }
        foreach (var change in changes)
            if (LaunchOptionsManager.Read(change.Profile.LocalConfigPath)?.Contains("ASA-RU-Fix.exe", StringComparison.OrdinalIgnoreCase) == true)
                throw new InvalidOperationException("Интеграция ещё активна. Updater сохранён.");
        if (platform.IsGameRunning(config.GamePath)) throw new InvalidOperationException("Закройте ARK и повторите удаление.");
        File.Delete(Path.Combine(config.GamePath, "ShooterGame/Content/Paks/ASA_RU_Fix_P.pak"));
        platform.Unregister();
        // Running EXE and owned data are removed by a separate fixed-path helper AFTER exit.
    }
}
