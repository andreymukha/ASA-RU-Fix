using System.Text;

namespace AsaRuFix.Core;

public static class LaunchOptionsManager
{
    private static readonly string[] LaunchPath = ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps", "2399830", "LaunchOptions"];

    public static string? Read(string path) => VdfDocument.Parse(Decode(File.ReadAllBytes(path)).Text).Get(LaunchPath);

    public static void Write(string path, string? value, Func<bool> steamRunning)
    {
        ArgumentNullException.ThrowIfNull(steamRunning);
        EnsureSteamStopped(steamRunning);
        path = Path.GetFullPath(path);
        byte[] original = File.ReadAllBytes(path);
        var decoded = Decode(original);
        var document = VdfDocument.Parse(decoded.Text);
        string patched = value is null ? document.Remove(LaunchPath) : document.Set(LaunchPath, value);
        if (patched == decoded.Text) return;
        string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                output.Write(decoded.Preamble);
                output.Write(decoded.Encoding.GetBytes(patched));
                output.Flush(true);
            }
            if (Read(temp) != value) throw new IOException("Проверка записанных LaunchOptions не прошла.");
            EnsureSteamStopped(steamRunning);
            // Hold a read handle which denies ordinary writes but permits atomic replacement.
            using var guard = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete);
            using var current = new MemoryStream();
            guard.CopyTo(current);
            if (!original.AsSpan().SequenceEqual(current.GetBuffer().AsSpan(0, checked((int)current.Length))))
                throw new IOException("Steam localconfig изменился во время настройки. Повторите операцию.");
            File.Replace(temp, path, null);
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
        }
    }

    public static string Managed(string exe) => GameCommandBuilder.Quote(exe) + " --steam-launch -- %command%";

    public static string? Restore(string? current, string managed, string? original)
    {
        if (string.Equals(current, managed, StringComparison.Ordinal)) return original;
        if (current is not null && current.StartsWith(managed, StringComparison.Ordinal) && current.Length > managed.Length && char.IsWhiteSpace(current[managed.Length]))
        {
            string extra = current[managed.Length..].TrimStart(' ', '\t');
            try
            {
                GameCommandBuilder.ValidateOriginal(extra);
                if (extra.Contains('%') || !extra.StartsWith('-')) throw new ArgumentException("Добавлены сложные параметры.");
                return string.IsNullOrEmpty(original) ? extra : original + " " + extra;
            }
            catch (ArgumentException ex)
            {
                throw new InvalidOperationException("LaunchOptions изменены пользователем; автоматическое восстановление небезопасно.", ex);
            }
        }
        throw new InvalidOperationException("LaunchOptions изменены пользователем; автоматическое восстановление небезопасно.");
    }

    private static void EnsureSteamStopped(Func<bool> steamRunning)
    {
        if (steamRunning()) throw new InvalidOperationException("Для настройки запуска ARK необходимо закрыть Steam.");
    }

    private sealed record Decoded(string Text, Encoding Encoding, byte[] Preamble);

    private static Decoded Decode(byte[] bytes)
    {
        Encoding encoding = new UTF8Encoding(false, true);
        int prefix = 0;
        if (bytes.AsSpan().StartsWith(new byte[] { 0xEF, 0xBB, 0xBF })) prefix = 3;
        else if (bytes.AsSpan().StartsWith(new byte[] { 0xFF, 0xFE })) { encoding = new UnicodeEncoding(false, false, true); prefix = 2; }
        else if (bytes.AsSpan().StartsWith(new byte[] { 0xFE, 0xFF })) { encoding = new UnicodeEncoding(true, false, true); prefix = 2; }
        return new Decoded(encoding.GetString(bytes, prefix, bytes.Length - prefix), encoding, bytes[..prefix]);
    }
}
