using System.Text.Json;

namespace AsaRuFix.Core;

/// <summary>Читает только локальные данные, без обращения к сети и изменения установки.</summary>
public static class MainWindowSnapshotReader
{
    public static MainWindowSnapshot Read(AppPaths paths, SteamInstallation? steam, SteamUser? user, string? processPath)
    {
        var store = new ConfigStore(paths);
        var config = store.Load();
        var state = store.LoadState();
        string? current = null;
        bool readable = true;
        try { if (user is not null) current = LaunchOptionsManager.Read(user.LocalConfigPath); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or FormatException) { readable = false; }
        var managed = LaunchOptionsManager.Managed(paths.Executable);
        bool referenced = current?.Contains("ASA-RU-Fix.exe", StringComparison.OrdinalIgnoreCase) == true;
        var matches = config?.Integrations?.Where(x => x is not null && x.AccountId == user?.AccountId && x.LocalConfigPath == user?.LocalConfigPath).ToArray() ?? [];
        var previous = matches.Length == 1 ? matches[0] : null;
        bool safe = false, integration = false;
        if (readable && user is not null)
            try
            {
                string? original;
                if (referenced)
                {
                    if (previous is null || previous.ManagedLaunchOptions != managed) throw new InvalidOperationException();
                    original = LaunchOptionsManager.Restore(current, managed, previous.OriginalLaunchOptions);
                    integration = true;
                }
                else original = current;
                GameCommandBuilder.ValidateOriginal(original ?? "");
                safe = matches.Length <= 1 && (config is null || config.Integrations is not null);
            }
            catch (Exception error) when (error is ArgumentException or InvalidOperationException) { }
        bool stateValid = HasSchemaOne(paths.State) && !string.IsNullOrWhiteSpace(state.TranslationVersion) &&
            state.TranslationSha256 is { Length: 64 } hash && hash.All(Uri.IsHexDigit);
        bool pakVerified = false;
        if (stateValid && steam?.GamePath is not null)
            try
            {
                string pak = Path.Combine(steam.GamePath, "ShooterGame/Content/Paks/ASA_RU_Fix_P.pak");
                pakVerified = File.Exists(pak) && AtomicFile.Sha256(pak).Equals(state.TranslationSha256, StringComparison.OrdinalIgnoreCase);
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }
        return new()
        {
            SteamFound = steam is not null, ArkFound = steam?.GamePath is not null && SteamDiscovery.IsGameDirectory(steam.GamePath),
            ProfileCount = steam?.Users.Count ?? 0, ProfileName = user?.DisplayName, ProfileSelected = user is not null,
            ExecutablePresent = File.Exists(paths.Executable), ConfigFilePresent = File.Exists(paths.Config) || File.Exists(paths.Config + ".backup"),
            ConfigValid = config?.Integrations is not null && HasSchemaOne(paths.Config), StateValid = stateValid,
            IntegrationValid = integration && safe, ManagedOptionsReferenced = referenced, OptionsReadable = readable,
            RecoverySafe = safe, PakVerified = pakVerified, TranslationVersion = stateValid ? state.TranslationVersion : null,
            RunningInstalledCopy = string.Equals(processPath, paths.Executable, StringComparison.OrdinalIgnoreCase),
            LogExists = File.Exists(Path.Combine(paths.Logs, "updater.log"))
        };
    }

    private static bool HasSchemaOne(string path)
    {
        try
        {
            using var json = JsonDocument.Parse(File.ReadAllText(path));
            return json.RootElement.TryGetProperty("schema", out var schema) && schema.TryGetInt32(out int value) && value == 1;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException) { return false; }
    }
}
