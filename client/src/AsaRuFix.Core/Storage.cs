using System.Text.Json;

namespace AsaRuFix.Core;

public sealed class AppPaths(string root)
{
    public string Root { get; } = Path.GetFullPath(root);
    public string Executable => Path.Combine(Root, "ASA-RU-Fix.exe");
    public string Config => Path.Combine(Root, "config.json");
    public string State => Path.Combine(Root, "state.json");
    public string Logs => Path.Combine(Root, "logs");
    public string Updates => Path.Combine(Root, "updates");
    public static AppPaths Default => new(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ASA-RU-Fix"));
}

public sealed record SteamProfileIntegration
{
    public string AccountId { get; init; } = "";
    public string LocalConfigPath { get; init; } = "";
    public string? OriginalLaunchOptions { get; init; }
    public string ManagedLaunchOptions { get; init; } = "";
}

public sealed record ClientConfig
{
    public int Schema { get; init; } = 1;
    public string UpdaterVersion { get; set; } = "1.0.0";
    public string SteamPath { get; set; } = "";
    public string SteamAccountId { get; set; } = "";
    public string SteamLocalConfigPath { get; set; } = "";
    public string GamePath { get; set; } = "";
    public string? OriginalLaunchOptions { get; set; }
    public string ManagedLaunchOptions { get; set; } = "";
    public string InstalledAt { get; init; } = DateTimeOffset.UtcNow.ToString("O");
    public List<SteamProfileIntegration> Integrations { get; set; } = [];
}

public sealed record ClientState
{
    public int Schema { get; init; } = 1;
    public string? TranslationVersion { get; set; }
    public string? TranslationSha256 { get; set; }
    public string? CheckedAt { get; set; }
    public string? LastError { get; set; }
}

public sealed class ConfigStore(AppPaths paths)
{
    public AppPaths Paths { get; } = paths;
    public static JsonSerializerOptions JsonOptions { get; } = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, WriteIndented = true };
    public ClientConfig? Load()
    {
        foreach (var path in new[] { Paths.Config, Paths.Config + ".backup" })
            try
            {
                if (!File.Exists(path)) continue;
                var config = JsonSerializer.Deserialize<ClientConfig>(File.ReadAllText(path), JsonOptions);
                if (config?.Schema == 1) return config;
            }
            catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException) { }
        return null;
    }
    public ClientState LoadState()
    {
        try { return JsonSerializer.Deserialize<ClientState>(File.ReadAllText(Paths.State), JsonOptions) is { Schema: 1 } state ? state : new(); }
        catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException) { return new(); }
    }
    public void Save(ClientConfig config)
    {
        var previous = Load();
        // Never copy a damaged primary over the last valid recovery data.
        SaveJson(Paths.Config + ".backup", previous ?? config);
        SaveJson(Paths.Config, config);
    }
    public void SaveState(ClientState state) => SaveJson(Paths.State, state);
    public static void SaveJson<T>(string path, T value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                output.Write(System.Text.Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value, JsonOptions) + "\n"));
                output.Flush(true);
            }
            _ = JsonSerializer.Deserialize<T>(File.ReadAllText(temp), JsonOptions);
            if (File.Exists(path)) File.Replace(temp, path, null); else File.Move(temp, path);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
}

public sealed class LocalLogger(AppPaths paths, long maxBytes = 256 * 1024)
{
    private readonly object gate = new();
    public void Write(string kind, string detail = "")
    {
        try
        {
            lock (gate)
            {
                Directory.CreateDirectory(paths.Logs);
                var file = Path.Combine(paths.Logs, "updater.log");
                if (File.Exists(file) && new FileInfo(file).Length >= maxBytes)
                {
                    for (var i = 3; i >= 1; i--)
                    {
                        var previous = i == 1 ? file : file + "." + (i - 1);
                        if (File.Exists(previous)) File.Move(previous, file + "." + i, true);
                    }
                }
                File.AppendAllText(file, $"{DateTimeOffset.Now:O} {kind} {detail[..Math.Min(detail.Length, 1000)]}\n");
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }
    }
}
