using System.Globalization;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace AsaRuFix.Core;

public sealed record Artifact(string Filename, long Size, string Sha256, string DownloadUrl)
{
    internal const string PakFilename = "ASA_RU_Fix_P.pak";
    internal const string UtocFilename = "ASA_RU_Fix_P.utoc";
    internal const string UcasFilename = "ASA_RU_Fix_P.ucas";
    internal const string ClientFilename = "ASA-RU-Fix.exe";

    internal void Validate(string? expectedVersion = null)
    {
        var maxMegabytes = Filename switch
        {
            ClientFilename => 512L,
            PakFilename or UcasFilename => 128L,
            UtocFilename => 8L,
            _ => throw new InvalidDataException("Неизвестное имя файла обновления.")
        };
        if (Size <= 0 || Size > maxMegabytes * 1024 * 1024) throw new InvalidDataException("Недопустимый размер обновления.");
        if (Sha256 is null || !Regex.IsMatch(Sha256, "\\A[0-9a-fA-F]{64}\\z", RegexOptions.CultureInvariant))
            throw new InvalidDataException("Некорректный SHA-256.");
        const string prefix = "https://github.com/andreymukha/ASA-RU-Fix/releases/download/";
        if (DownloadUrl is null || !DownloadUrl.StartsWith(prefix, StringComparison.Ordinal)) throw new InvalidDataException("Недопустимый URL обновления.");
        var parts = DownloadUrl[prefix.Length..].Split('/');
        var tagPrefix = Filename == ClientFilename ? "updater-v" : "v";
        if (parts.Length != 2 || parts[1] != Filename || !parts[0].StartsWith(tagPrefix, StringComparison.Ordinal))
            throw new InvalidDataException("URL не соответствует файлу release.");
        var version = parts[0][tagPrefix.Length..];
        SemVersion.Parse(version);
        if (expectedVersion is not null && version != expectedVersion) throw new InvalidDataException("URL не соответствует версии manifest.");
    }
}

public sealed record ChannelManifest(int Schema, string Version, Artifact Artifact)
{
    public IReadOnlyList<Artifact> Companions { get; private init; } = Array.Empty<Artifact>();

    public static ChannelManifest ParseStable(string json) => Parse(json, false);
    public static ChannelManifest ParseClient(string json) => Parse(json, true);
    private static ChannelManifest Parse(string json, bool client)
    {
        try
        {
            using var document = JsonDocument.Parse(json, new JsonDocumentOptions { MaxDepth = 32 });
            var root = document.RootElement;
            RejectDuplicateKeys(root);
            var schema = root.GetProperty("schema").GetInt32();
            if (schema != 1) throw new InvalidDataException("Неизвестная схема manifest.");
            if ((!client || root.TryGetProperty("channel", out _)) && root.GetProperty("channel").GetString() != "stable")
                throw new InvalidDataException("Неизвестный канал обновлений.");
            var version = root.GetProperty("version").GetString() ?? throw new InvalidDataException("Отсутствует версия.");
            var legacyVersion = SemVersion.Parse(version);
            if (root.TryGetProperty("release", out var release) && release.TryGetProperty("tag", out var tag) &&
                tag.GetString() != (client ? "updater-v" : "v") + version)
                throw new InvalidDataException("Release tag не соответствует версии.");
            var artifact = ReadArtifact(root.GetProperty("artifact"), version);
            if (artifact.Filename != (client ? Artifact.ClientFilename : Artifact.PakFilename))
                throw new InvalidDataException("Неверное имя файла для канала.");
            if (!client && root.TryGetProperty("bundle", out var bundle))
                return ParseBundle(bundle, schema, legacyVersion);
            return new(schema, version, artifact);
        }
        catch (Exception exception) when (exception is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        { throw new InvalidDataException("Некорректный manifest обновления.", exception); }
    }

    private static ChannelManifest ParseBundle(JsonElement bundle, int schema, SemVersion legacyVersion)
    {
        var version = bundle.GetProperty("version").GetString() ?? throw new InvalidDataException("Отсутствует версия комплекта перевода.");
        if (SemVersion.Parse(version).CompareTo(legacyVersion) <= 0)
            throw new InvalidDataException("Версия комплекта перевода должна быть новее версии отдельного PAK.");
        if (bundle.GetProperty("release").GetProperty("tag").GetString() != "v" + version)
            throw new InvalidDataException("Release tag не соответствует версии комплекта перевода.");

        var files = bundle.GetProperty("artifacts");
        if (files.GetArrayLength() != 3) throw new InvalidDataException("Комплект перевода должен содержать PAK, UTOC и UCAS.");
        var artifacts = new Dictionary<string, Artifact>(StringComparer.Ordinal);
        foreach (var file in files.EnumerateArray())
        {
            var artifact = ReadArtifact(file, version);
            if (!artifacts.TryAdd(artifact.Filename, artifact))
                throw new InvalidDataException("Комплект перевода содержит повторяющиеся файлы.");
        }
        if (!artifacts.TryGetValue(Artifact.PakFilename, out var pak) ||
            !artifacts.TryGetValue(Artifact.UtocFilename, out var utoc) ||
            !artifacts.TryGetValue(Artifact.UcasFilename, out var ucas))
            throw new InvalidDataException("Комплект перевода должен содержать PAK, UTOC и UCAS.");
        return new(schema, version, pak)
        {
            Companions = Array.AsReadOnly(new[] { utoc, ucas })
        };
    }

    private static Artifact ReadArtifact(JsonElement data, string version)
    {
        var artifact = new Artifact(data.GetProperty("filename").GetString()!, data.GetProperty("size").GetInt64(),
            data.GetProperty("sha256").GetString()!, data.GetProperty("download_url").GetString()!);
        artifact.Validate(version);
        return artifact with { Sha256 = artifact.Sha256.ToLowerInvariant() };
    }

    private static void RejectDuplicateKeys(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new InvalidDataException("Повторяющийся ключ manifest.");
                RejectDuplicateKeys(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (var item in element.EnumerateArray()) RejectDuplicateKeys(item);
    }
}

public sealed record SemVersion(int Major, int Minor, int Patch) : IComparable<SemVersion>
{
    public static SemVersion Parse(string value)
    {
        if (value is null || !Regex.IsMatch(value, "\\A(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\z", RegexOptions.CultureInvariant))
            throw new InvalidDataException("Версия должна иметь формат major.minor.patch.");
        var parts = value.Split('.');
        if (!int.TryParse(parts[0], NumberStyles.None, CultureInfo.InvariantCulture, out var major) ||
            !int.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out var minor) ||
            !int.TryParse(parts[2], NumberStyles.None, CultureInfo.InvariantCulture, out var patch))
            throw new InvalidDataException("Слишком большое число в версии.");
        return new(major, minor, patch);
    }
    public int CompareTo(SemVersion? other)
    {
        if (other is null) return 1;
        var result = Major.CompareTo(other.Major);
        if (result == 0) result = Minor.CompareTo(other.Minor);
        return result == 0 ? Patch.CompareTo(other.Patch) : result;
    }
    public override string ToString() => $"{Major}.{Minor}.{Patch}";
}

public sealed class ChannelClient
{
    public const string StableUrl = "https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/stable.json";
    public const string ClientUrl = "https://raw.githubusercontent.com/andreymukha/ASA-RU-Fix/channel/client.json";
    private readonly HttpClient http;
    private readonly string clientVersion;

    /// <summary>Production transport must disable automatic redirects; use CreateHttpClient.</summary>
    public ChannelClient(HttpClient http, string clientVersion)
    {
        ArgumentNullException.ThrowIfNull(http);
        SemVersion.Parse(clientVersion);
        this.http = http;
        this.clientVersion = clientVersion;
    }
    public static HttpClient CreateHttpClient() => new(new SocketsHttpHandler
    {
        AllowAutoRedirect = false, ConnectTimeout = TimeSpan.FromSeconds(5), UseCookies = false,
        AutomaticDecompression = DecompressionMethods.None
    }) { Timeout = Timeout.InfiniteTimeSpan };
    public Task<ChannelManifest> GetStableAsync(CancellationToken cancellationToken) => GetManifestAsync(StableUrl, false, cancellationToken);
    public Task<ChannelManifest> GetClientAsync(CancellationToken cancellationToken) => GetManifestAsync(ClientUrl, true, cancellationToken);

    private async Task<ChannelManifest> GetManifestAsync(string url, bool client, CancellationToken cancellationToken)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(5));
        using var response = await GetAsync(new Uri(url), true, timeout.Token).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        const int limit = 128 * 1024;
        if (response.Content.Headers.ContentLength > limit) throw new InvalidDataException("Manifest превышает допустимый размер.");
        using var output = new MemoryStream();
        await CopyLimitedAsync(response.Content, output, limit, null, timeout.Token).ConfigureAwait(false);
        var json = Encoding.UTF8.GetString(output.ToArray());
        return client ? ChannelManifest.ParseClient(json) : ChannelManifest.ParseStable(json);
    }

    public async Task DownloadAsync(Artifact artifact, string destination, IProgress<double>? progress, CancellationToken cancellationToken)
    {
        artifact.Validate();
        cancellationToken.ThrowIfCancellationRequested();
        destination = Path.GetFullPath(destination);
        var temporary = destination + ".download-" + Guid.NewGuid().ToString("N");
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromMinutes(2));
        try
        {
            progress?.Report(0);
            using var response = await GetAsync(new Uri(artifact.DownloadUrl), false, timeout.Token).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            if (response.Content.Headers.ContentLength is long length && length != artifact.Size)
                throw new InvalidDataException("HTTP размер не соответствует manifest.");
            await using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 81920, FileOptions.Asynchronous))
            {
                var size = await CopyLimitedAsync(response.Content, output, artifact.Size, progress, timeout.Token).ConfigureAwait(false);
                if (size != artifact.Size) throw new InvalidDataException("Загрузка оборвалась: размер не соответствует manifest.");
                await output.FlushAsync(timeout.Token).ConfigureAwait(false);
            }
            timeout.Token.ThrowIfCancellationRequested();
            AtomicFile.InstallVerified(temporary, destination, artifact.Size, artifact.Sha256, timeout.Token.ThrowIfCancellationRequested);
            progress?.Report(1);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private async Task<HttpResponseMessage> GetAsync(Uri uri, bool manifest, CancellationToken cancellationToken)
    {
        var originalUri = uri;
        for (int redirect = 0; redirect <= 5; redirect++)
        {
            ValidateTransportUri(uri, originalUri, manifest);
            using var request = new HttpRequestMessage(HttpMethod.Get, uri);
            request.Headers.UserAgent.Add(new ProductInfoHeaderValue("ASA-RU-Fix-Updater", clientVersion));
            var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
            try
            {
                if (response.RequestMessage?.RequestUri is Uri finalUri) ValidateTransportUri(finalUri, originalUri, manifest);
                if ((int)response.StatusCode is 301 or 302 or 303 or 307 or 308)
                {
                    var location = response.Headers.Location ?? throw new InvalidDataException("Redirect не содержит Location.");
                    uri = location.IsAbsoluteUri ? location : new Uri(uri, location);
                    ValidateTransportUri(uri, originalUri, manifest);
                    response.Dispose();
                    continue;
                }
                return response;
            }
            catch { response.Dispose(); throw; }
        }
        throw new InvalidDataException("Слишком много HTTP redirect.");
    }
    private static void ValidateTransportUri(Uri uri, Uri originalUri, bool manifest)
    {
        if (uri.Scheme != Uri.UriSchemeHttps || !uri.IsDefaultPort || uri.UserInfo.Length != 0 || uri.Fragment.Length != 0)
            throw new InvalidDataException("Разрешены только безопасные HTTPS URL.");
        if (manifest)
        {
            if (uri.AbsoluteUri != originalUri.AbsoluteUri) throw new InvalidDataException("Недопустимый redirect manifest.");
        }
        else if (uri.Host == "github.com" && uri.AbsoluteUri != originalUri.AbsoluteUri)
            throw new InvalidDataException("Redirect GitHub не соответствует ожидаемому release.");
        else if (uri.Host != "github.com" && uri.Host != "release-assets.githubusercontent.com" &&
            uri.Host != "objects.githubusercontent.com" && uri.Host != "github-releases.githubusercontent.com")
            throw new InvalidDataException("Недопустимый хост HTTP redirect.");
    }
    private static async Task<long> CopyLimitedAsync(HttpContent content, Stream output, long limit, IProgress<double>? progress, CancellationToken cancellationToken)
    {
        await using var input = await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        var buffer = new byte[81920];
        long total = 0;
        while (true)
        {
            var count = await input.ReadAsync(buffer, cancellationToken).ConfigureAwait(false);
            if (count == 0) break;
            total += count;
            if (total > limit) throw new InvalidDataException("Загрузка превышает разрешённый размер.");
            await output.WriteAsync(buffer.AsMemory(0, count), cancellationToken).ConfigureAwait(false);
            progress?.Report((double)total / limit);
        }
        return total;
    }
}
