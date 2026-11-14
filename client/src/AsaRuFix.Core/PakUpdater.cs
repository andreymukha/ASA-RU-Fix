namespace AsaRuFix.Core;

public sealed record PakUpdateResult(string Status, string Version, string Sha256);

public sealed class PakUpdater(ChannelClient client)
{
    private static string Paks(string gameRoot) => Path.Combine(Path.GetFullPath(gameRoot), "ShooterGame", "Content", "Paks");

    public static bool NeedsRecovery(string gameRoot) => new PakTransaction(Paks(gameRoot)).NeedsRecovery;

    public static bool MatchesManifest(string gameRoot, ChannelManifest manifest)
    {
        var transaction = new PakTransaction(Paks(gameRoot));
        return !transaction.NeedsRecovery && transaction.Matches(PakTransaction.Pak, Identity(manifest.Artifact)) &&
            manifest.Companions.All(asset => transaction.Matches(asset.Filename, Identity(asset)));
    }

    public static bool MatchesInstalled(string gameRoot, string pakSha256)
    {
        var directory = Paks(gameRoot);
        var transaction = new PakTransaction(directory);
        var pak = PakTransaction.Identity.Read(Path.Combine(directory, PakTransaction.Pak));
        if (transaction.NeedsRecovery || pak is null || !pak.Sha256.Equals(pakSha256, StringComparison.OrdinalIgnoreCase))
            return false;
        var owned = transaction.ReadOwnership();
        return owned is null || transaction.Matches(PakTransaction.Ucas, owned.Ucas) &&
            transaction.Matches(PakTransaction.Utoc, owned.Utoc);
    }

    public async Task<PakUpdateResult> UpdateAsync(string gameRoot, string stagingDir, Func<bool> gameRunning,
        IProgress<double>? progress, CancellationToken cancellationToken)
    {
        var directory = Paks(gameRoot);
        var transaction = new PakTransaction(directory);
        transaction.Recover(EnsureGameClosed);
        var manifest = await client.GetStableAsync(cancellationToken).ConfigureAwait(false);
        var owned = transaction.ReadOwnership();
        if (manifest.Companions.Count == 0 && owned is not null)
            throw new InvalidDataException("В канале обновлений отсутствуют файлы установленного комплекта. Перевод оставлен на месте.");

        PakTransaction.Ownership? incoming = null;
        if (manifest.Companions.Count != 0)
        {
            incoming = new(Identity(manifest.Companions.Single(x => x.Filename == PakTransaction.Ucas)),
                Identity(manifest.Companions.Single(x => x.Filename == PakTransaction.Utoc)));
            transaction.CheckCompanions(owned, incoming);
        }
        if (MatchesManifest(gameRoot, manifest) && incoming == owned)
            return new("Current", manifest.Version, manifest.Artifact.Sha256);

        EnsureCanUpdate();
        if (!Directory.Exists(directory)) throw new DirectoryNotFoundException("Каталог Paks игры не найден.");
        Directory.CreateDirectory(stagingDir);
        var staged = Path.Combine(stagingDir, "pak-" + Guid.NewGuid().ToString("N") + ".pending");
        if (incoming is null)
        {
            try
            {
                await client.DownloadAsync(manifest.Artifact, staged, progress, cancellationToken).ConfigureAwait(false);
                AtomicFile.InstallVerified(staged, Path.Combine(directory, PakTransaction.Pak), manifest.Artifact.Size,
                    manifest.Artifact.Sha256, EnsureCanUpdate);
            }
            finally { if (File.Exists(staged)) File.Delete(staged); }
        }
        else
        {
            Directory.CreateDirectory(staged);
            try
            {
                var files = new Dictionary<string, string>();
                foreach (var artifact in manifest.Companions.Append(manifest.Artifact))
                {
                    var path = Path.Combine(staged, artifact.Filename);
                    await client.DownloadAsync(artifact, path, artifact == manifest.Artifact ? progress : null,
                        cancellationToken).ConfigureAwait(false);
                    files.Add(artifact.Filename, path);
                }
                EnsureCanUpdate();
                transaction.CheckCompanions(owned, incoming);
                transaction.Install(files, manifest, incoming, EnsureGameClosed);
            }
            finally
            {
                foreach (var file in Directory.GetFiles(staged)) File.Delete(file);
                Directory.Delete(staged);
            }
        }
        return new("Updated", manifest.Version, manifest.Artifact.Sha256);

        void EnsureGameClosed()
        {
            if (gameRunning()) throw new InvalidOperationException("Закройте ARK и повторите обновление.");
        }

        void EnsureCanUpdate()
        {
            cancellationToken.ThrowIfCancellationRequested();
            EnsureGameClosed();
        }
    }

    private static PakTransaction.Identity Identity(Artifact artifact) => new(artifact.Size, artifact.Sha256);
}
