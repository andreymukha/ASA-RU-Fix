using System.Security.Cryptography;

namespace AsaRuFix.Core;

public static class AtomicFile
{
    public static string Sha256(string path)
    {
        using var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return Convert.ToHexStringLower(SHA256.HashData(input));
    }

    public static void InstallVerified(string source, string target, long size, string sha, Action? beforeReplace = null)
    {
        target = Path.GetFullPath(target);
        var temporary = target + ".new-" + Guid.NewGuid().ToString("N");
        try
        {
            File.Copy(source, temporary, false);
            if (new FileInfo(temporary).Length != size || !string.Equals(Sha256(temporary), sha, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Размер или SHA-256 временного файла не соответствует manifest.");
            beforeReplace?.Invoke();
            if (File.Exists(target)) File.Replace(temporary, target, null);
            else File.Move(temporary, target);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
