using System.Text.Json;

namespace AsaRuFix.Core;

public sealed class PakRecoveryException(string message, Exception? inner = null) : IOException(message, inner);

internal sealed class PakTransaction(string directory)
{
    internal const string Pak = Artifact.PakFilename;
    internal const string Utoc = Artifact.UtocFilename;
    internal const string Ucas = Artifact.UcasFilename;
    private const string OwnershipFile = ".asa-ru-fix-bundle.json";
    private static readonly string[] Names = [Ucas, Utoc, OwnershipFile, Pak];
    private string Work => Path.Combine(directory, ".asa-ru-fix-transaction");
    private string JournalPath => Path.Combine(Work, "journal.json");
    private string PathFor(string name) => Path.Combine(directory, name);

    internal sealed record Identity(long Size, string Sha256)
    {
        internal static Identity? Read(string path) => File.Exists(path)
            ? new(new FileInfo(path).Length, AtomicFile.Sha256(path)) : null;

        internal bool Valid => Size > 0 && Sha256 is { Length: 64 } && Sha256.All(Uri.IsHexDigit);
    }

    internal sealed record Ownership(Identity Ucas, Identity Utoc);
    private sealed record Entry(Identity? Previous, Identity? Next);
    private sealed record Journal(Entry[] Files);

    internal bool NeedsRecovery => File.Exists(JournalPath);

    internal Ownership? ReadOwnership()
    {
        var path = PathFor(OwnershipFile);
        if (!File.Exists(path)) return null;
        var value = JsonSerializer.Deserialize<Ownership>(File.ReadAllText(path));
        if (value is not { Ucas.Valid: true, Utoc.Valid: true })
            throw new InvalidDataException("Повреждены данные об установленном комплекте ASA RU Fix.");
        return value;
    }

    internal bool Matches(string name, Identity identity) => Identity.Read(PathFor(name)) == identity;

    internal void CheckCompanions(Ownership? owned, Ownership? incoming)
    {
        Check(Ucas, owned?.Ucas, incoming?.Ucas);
        Check(Utoc, owned?.Utoc, incoming?.Utoc);

        void Check(string name, Identity? existing, Identity? next)
        {
            var actual = Identity.Read(PathFor(name));
            if (actual is not null && actual != existing && actual != next)
                throw new InvalidOperationException($"Файл {name} не совпадает с проверенным комплектом ASA RU Fix. Он сохранён.");
        }
    }

    internal void Install(IReadOnlyDictionary<string, string> staged, ChannelManifest manifest,
        Ownership ownership, Action ensureGameClosed)
    {
        var desired = staged.ToDictionary();
        string metadata = Path.Combine(Path.GetDirectoryName(staged[Pak])!, OwnershipFile);
        WriteJson(metadata, ownership);
        desired.Add(OwnershipFile, metadata);
        var expected = manifest.Companions.Append(manifest.Artifact).ToDictionary(
            asset => asset.Filename, asset => new Identity(asset.Size, asset.Sha256));
        expected.Add(OwnershipFile, Identity.Read(metadata)!);
        Apply(desired, expected, ensureGameClosed);
    }

    internal void CheckRemoval(Action ensureGameClosed)
    {
        Recover(ensureGameClosed);
        var owned = ReadOwnership();
        if (owned is not null) CheckCompanions(owned, null);
    }

    internal void Remove(Action ensureGameClosed)
    {
        var owned = ReadOwnership();
        if (owned is null)
        {
            ensureGameClosed();
            File.Delete(PathFor(Pak));
            return;
        }
        CheckCompanions(owned, null);
        Apply(new Dictionary<string, string>(), new Dictionary<string, Identity>(), ensureGameClosed);
    }

    internal void Recover(Action ensureGameClosed)
    {
        if (!NeedsRecovery) return;
        try
        {
            ensureGameClosed();
            var journal = JsonSerializer.Deserialize<Journal>(File.ReadAllText(JournalPath));
            if (journal?.Files is not { Length: 4 } entries ||
                entries.Any(x => x is null || x.Previous is { Valid: false } || x.Next is { Valid: false }))
                throw new InvalidDataException("Повреждён журнал установки перевода.");

            // Validate every saved input and every destination before touching the game.
            for (int i = 0; i < Names.Length; i++)
            {
                var entry = entries[i];
                if (Identity.Read(Snapshot(i)) != entry.Previous)
                    throw new InvalidDataException("Резервная копия комплекта не прошла проверку.");
                var current = Identity.Read(PathFor(Names[i]));
                if (current is not null && current != entry.Previous && current != entry.Next)
                    throw new InvalidDataException($"Во время восстановления изменился файл {Names[i]}.");
            }

            // Hide the PAK until the previous companions are in place.
            File.Delete(PathFor(Pak));
            for (int i = 0; i < Names.Length; i++)
                Replace(Names[i], entries[i].Previous is null ? null : Snapshot(i), entries[i].Previous);
            Finish();
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException or InvalidDataException or JsonException)
        {
            throw new PakRecoveryException("Не удалось восстановить комплект перевода. Закройте ARK и повторите запуск ASA RU Fix.", error);
        }
    }

    private void Apply(IReadOnlyDictionary<string, string> desired,
        IReadOnlyDictionary<string, Identity> expected, Action ensureGameClosed)
    {
        CleanStaging();
        Directory.CreateDirectory(Work);
        try
        {
            var entries = new Entry[Names.Length];
            for (int i = 0; i < Names.Length; i++)
            {
                var current = PathFor(Names[i]);
                var previous = Identity.Read(current);
                if (previous is not null)
                {
                    CopyDurably(current, Snapshot(i));
                    if (Identity.Read(Snapshot(i)) != previous)
                        throw new InvalidDataException("Не удалось подтвердить резервную копию комплекта.");
                }
                var next = expected.GetValueOrDefault(Names[i]);
                if (desired.TryGetValue(Names[i], out var source) && Identity.Read(source) != next)
                    throw new InvalidDataException($"Подготовленный файл {Names[i]} не соответствует манифесту.");
                entries[i] = new(previous, next);
            }

            ensureGameClosed();
            WriteJson(JournalPath, new Journal(entries));
            // A launch outside the updater during replacement cannot mount mixed files.
            File.Delete(PathFor(Pak));
            for (int i = 0; i < Names.Length; i++)
            {
                ensureGameClosed();
                Replace(Names[i], desired.GetValueOrDefault(Names[i]), entries[i].Next);
            }
            Finish();
        }
        catch
        {
            // Cancellation must not prevent restoration after mutations have begun.
            Recover(ensureGameClosed);
            throw;
        }
        finally
        {
            if (!NeedsRecovery) CleanStaging();
        }
    }

    private void Replace(string name, string? source, Identity? identity)
    {
        string target = PathFor(name);
        if (Identity.Read(target) == identity) return;
        if (source is null || identity is null)
            File.Delete(target);
        else
        {
            var staged = Path.Combine(Work, "replace.tmp");
            File.Delete(staged);
            CopyDurably(source, staged);
            if (Identity.Read(staged) != identity)
                throw new InvalidDataException($"Размер или SHA-256 файла {name} не соответствует ожидаемому.");
            if (File.Exists(target)) File.Replace(staged, target, null);
            else File.Move(staged, target);
        }
    }

    private string Snapshot(int i) => Path.Combine(Work, $"{i}.old");

    private void Finish() => File.Delete(JournalPath);

    private void CleanStaging()
    {
        if (!Directory.Exists(Work) || NeedsRecovery) return;
        // Only remove files created by this transaction implementation.
        for (int i = 0; i < Names.Length; i++) File.Delete(Snapshot(i));
        File.Delete(JournalPath + ".new");
        File.Delete(Path.Combine(Work, "replace.tmp"));
        Directory.Delete(Work);
    }

    private static void CopyDurably(string source, string target)
    {
        using var input = File.OpenRead(source);
        using var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        input.CopyTo(output);
        output.Flush(flushToDisk: true);
    }

    private static void WriteJson<T>(string path, T data)
    {
        var temporary = path + ".new";
        using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            JsonSerializer.Serialize(stream, data);
            stream.Flush(flushToDisk: true);
        }
        File.Move(temporary, path);
    }
}
