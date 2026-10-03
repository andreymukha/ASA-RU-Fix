namespace AsaRuFix.Core;

public sealed record PakUpdateResult(string Status, string Version, string Sha256);

public sealed class PakUpdater(ChannelClient client)
{
    public async Task<PakUpdateResult> UpdateAsync(string gameRoot, string stagingDir, Func<bool> gameRunning,
        IProgress<double>? progress, CancellationToken cancellationToken)
    {
        var manifest = await client.GetStableAsync(cancellationToken).ConfigureAwait(false);
        var target = Path.Combine(Path.GetFullPath(gameRoot), "ShooterGame", "Content", "Paks", "ASA_RU_Fix_P.pak");
        if (File.Exists(target) && string.Equals(AtomicFile.Sha256(target), manifest.Artifact.Sha256, StringComparison.OrdinalIgnoreCase))
            return new("Current", manifest.Version, manifest.Artifact.Sha256);
        EnsureGameClosed();
        if (!Directory.Exists(Path.GetDirectoryName(target))) throw new DirectoryNotFoundException("Каталог Paks игры не найден.");
        Directory.CreateDirectory(stagingDir);
        var staged = Path.Combine(stagingDir, "pak-" + Guid.NewGuid().ToString("N") + ".pending");
        try
        {
            await client.DownloadAsync(manifest.Artifact, staged, progress, cancellationToken).ConfigureAwait(false);
            AtomicFile.InstallVerified(staged, target, manifest.Artifact.Size, manifest.Artifact.Sha256, EnsureGameClosed);
            return new("Updated", manifest.Version, manifest.Artifact.Sha256);
        }
        finally { if (File.Exists(staged)) File.Delete(staged); }

        void EnsureGameClosed()
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (gameRunning()) throw new InvalidOperationException("Закройте ARK и повторите обновление.");
        }
    }
}
