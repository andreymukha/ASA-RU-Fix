namespace AsaRuFix.Core;

public sealed record PendingSelfUpdate(string Version, string FilePath, long Size, string Sha256);

public sealed class SelfUpdater(ChannelClient client)
{
    public async Task<PendingSelfUpdate?> StageAsync(string installedVersion, string updatesDir, CancellationToken cancellationToken)
    {
        var current = SemVersion.Parse(installedVersion);
        var manifest = await client.GetClientAsync(cancellationToken).ConfigureAwait(false);
        if (SemVersion.Parse(manifest.Version).CompareTo(current) <= 0) return null;
        var directory = Path.GetFullPath(updatesDir);
        Directory.CreateDirectory(directory);
        var pending = Path.Combine(directory, "new.pending.exe");
        await client.DownloadAsync(manifest.Artifact, pending, null, cancellationToken).ConfigureAwait(false);
        return new(manifest.Version, pending, manifest.Artifact.Size, manifest.Artifact.Sha256);
    }

    public static void Complete(PendingSelfUpdate pending, string installedExe, Action? beforeReplace = null)
    {
        SemVersion.Parse(pending.Version);
        installedExe = Path.GetFullPath(installedExe);
        var expected = Path.Combine(Path.GetDirectoryName(installedExe)!, "updates", "new.pending.exe");
        if (Path.GetFileName(installedExe) != "ASA-RU-Fix.exe" || !string.Equals(Path.GetFullPath(pending.FilePath), expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Неверный путь отложенного self-update.");
        new Artifact("ASA-RU-Fix.exe", pending.Size, pending.Sha256,
            $"https://github.com/andreymukha/ASA-RU-Fix/releases/download/updater-v{pending.Version}/ASA-RU-Fix.exe").Validate(pending.Version);
        // The caller waits for the previous updater PID before invoking replacement.
        AtomicFile.InstallVerified(pending.FilePath, installedExe, pending.Size, pending.Sha256, beforeReplace);
    }
}
