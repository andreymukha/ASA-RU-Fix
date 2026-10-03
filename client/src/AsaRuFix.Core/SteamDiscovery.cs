using Microsoft.Win32;
using System.Globalization;
using System.Runtime.Versioning;

namespace AsaRuFix.Core;

public sealed record SteamUser(string AccountId, string DisplayName, string LocalConfigPath);
public sealed record SteamInstallation(string SteamPath, string? GamePath, IReadOnlyList<SteamUser> Users, string? ActiveAccountId);
public static class SteamDiscovery
{
    public const string AppId = "2399830";

    public static SteamInstallation? Find(string? steamPath = null, uint? activeUser = null)
    {
        if (steamPath is null && OperatingSystem.IsWindows())
        {
            var registry = ReadRegistry();
            steamPath = registry.Path;
            activeUser ??= registry.Active;
        }
        if (string.IsNullOrWhiteSpace(steamPath) || !Directory.Exists(steamPath)) return null;
        steamPath = Path.GetFullPath(steamPath);
        if (!Directory.Exists(Path.Combine(steamPath, "steamapps")) && !File.Exists(Path.Combine(steamPath, "steam.exe"))) return null;
        var libraries = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { steamPath };
        var folders = ReadVdf(Path.Combine(steamPath, "steamapps", "libraryfolders.vdf"));
        if (folders is not null)
        {
            foreach (var folder in folders.Children("libraryfolders"))
            {
                if (!uint.TryParse(folder.Key, out _)) continue;
                string? library = folder.Children is null ? folder.Value : folders.Get("libraryfolders", folder.Key, "path");
                if (!string.IsNullOrWhiteSpace(library) && Path.IsPathFullyQualified(library)) libraries.Add(Path.GetFullPath(library));
            }
        }
        string? gamePath = null;
        foreach (var library in libraries)
        {
            var manifest = ReadVdf(Path.Combine(library, "steamapps", "appmanifest_2399830.acf"));
            string? installDir = manifest?.Get("AppState", "installdir");
            if (!string.IsNullOrWhiteSpace(installDir) && manifest?.Get("AppState", "appid") == AppId)
            {
                string common = Path.GetFullPath(Path.Combine(library, "steamapps", "common"));
                string candidate = Path.GetFullPath(Path.Combine(common, installDir));
                if (candidate.StartsWith(common + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) && IsGameDirectory(candidate)) { gamePath = candidate; break; }
            }
            string fallback = Path.Combine(library, "steamapps", "common", "ARK Survival Ascended");
            if (IsGameDirectory(fallback)) { gamePath = fallback; break; }
        }
        var users = new List<SteamUser>();
        var loginUsers = ReadVdf(Path.Combine(steamPath, "config", "loginusers.vdf"));
        var names = new Dictionary<string, string>(StringComparer.Ordinal);
        if (loginUsers is not null)
        {
            foreach (var entry in loginUsers.Children("users"))
            {
                if (!ulong.TryParse(entry.Key, NumberStyles.None, CultureInfo.InvariantCulture, out ulong steamId) || entry.Children is null) continue;
                string accountId = ((uint)(steamId & uint.MaxValue)).ToString(CultureInfo.InvariantCulture);
                names[accountId] = loginUsers.Get("users", entry.Key, "PersonaName") ?? loginUsers.Get("users", entry.Key, "AccountName") ?? accountId;
            }
        }
        string userdata = Path.Combine(steamPath, "userdata");
        if (Directory.Exists(userdata))
        {
            foreach (var directory in Directory.EnumerateDirectories(userdata).Order(StringComparer.OrdinalIgnoreCase))
            {
                string id = Path.GetFileName(directory);
                if (!uint.TryParse(id, NumberStyles.None, CultureInfo.InvariantCulture, out uint number) || number == 0) continue;
                string localconfig = Path.Combine(directory, "config", "localconfig.vdf");
                if (!File.Exists(localconfig)) continue;
                users.Add(new SteamUser(id, names.GetValueOrDefault(id, id), localconfig));
            }
        }
        return new SteamInstallation(steamPath, gamePath, users, activeUser is > 0 ? activeUser.Value.ToString(CultureInfo.InvariantCulture) : null);
    }

    public static bool IsGameDirectory(string path) => Directory.Exists(Path.Combine(path, "ShooterGame", "Binaries", "Win64")) && Directory.Exists(Path.Combine(path, "ShooterGame", "Content", "Paks"));

    private static VdfDocument? ReadVdf(string path)
    {
        try { return File.Exists(path) ? VdfDocument.Parse(File.ReadAllText(path)) : null; }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or FormatException) { return null; }
    }

    [SupportedOSPlatform("windows")]
    private static (string? Path, uint? Active) ReadRegistry()
    {
        using var steam = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam", false);
        string? path = steam?.GetValue("SteamPath") as string;
        using var active = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam\ActiveProcess", false);
        uint? user = active?.GetValue("ActiveUser") is int value && value != 0 ? unchecked((uint)value) : null;
        if (path is null)
        {
            using var machine = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\WOW6432Node\Valve\Steam", false);
            path = machine?.GetValue("InstallPath") as string;
        }
        return (path, user);
    }
}
public static class SteamUserResolver
{
    public static SteamUser? Resolve(SteamInstallation installation)
    {
        ArgumentNullException.ThrowIfNull(installation);
        if (installation.ActiveAccountId is not null) return installation.Users.SingleOrDefault(x => x.AccountId == installation.ActiveAccountId);
        return installation.Users.Count == 1 ? installation.Users[0] : null;
    }
}
