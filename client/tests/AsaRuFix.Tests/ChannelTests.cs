using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public sealed class ChannelTests
{
    [TestMethod]
    public void StableAndClientManifestValidateIndependentVersions()
    {
        Assert.AreEqual("1.2.3", ChannelManifest.ParseStable(DownloadFixture.Manifest(false, "1.2.3")).Version);
        Assert.AreEqual("1.2.3", ChannelManifest.ParseClient(DownloadFixture.Manifest(true, "1.2.3")).Version);
    }

    [TestMethod]
    [DataRow("schema", "2")]
    [DataRow("channel", "\"beta\"")]
    [DataRow("version", "\"v01.2.3\"")]
    [DataRow("artifact.filename", "\"evil.pak\"")]
    [DataRow("artifact.size", "0")]
    [DataRow("artifact.size", "134217729")]
    [DataRow("artifact.sha256", "\"not-a-sha\"")]
    [DataRow("artifact.download_url", "\"http://github.com/andreymukha/ASA-RU-Fix/releases/download/v1.2.3/ASA_RU_Fix_P.pak\"")]
    [DataRow("artifact.download_url", "\"https://github.com.evil.example/andreymukha/ASA-RU-Fix/releases/download/v1.2.3/ASA_RU_Fix_P.pak\"")]
    [DataRow("artifact.download_url", "\"https://github.com/other/ASA-RU-Fix/releases/download/v1.2.3/ASA_RU_Fix_P.pak\"")]
    [DataRow("artifact.download_url", "\"https://github.com/andreymukha/ASA-RU-Fix/releases/download/v9.9.9/ASA_RU_Fix_P.pak\"")]
    [DataRow("artifact.download_url", "\"https://github.com/andreymukha/ASA-RU-Fix/releases/download/v1.2.3/ASA_RU_Fix_P.pak?bad=1\"")]
    public void RejectsInvalidStableFields(string field, string value)
    {
        var root = System.Text.Json.Nodes.JsonNode.Parse(DownloadFixture.Manifest(false, "1.2.3"))!;
        var parts = field.Split('.');
        if (parts.Length == 2) root[parts[0]]![parts[1]] = System.Text.Json.Nodes.JsonNode.Parse(value);
        else root[field] = System.Text.Json.Nodes.JsonNode.Parse(value);
        Assert.Throws<InvalidDataException>(() => ChannelManifest.ParseStable(root.ToJsonString()));
    }

    [TestMethod]
    public void RejectsClientTranslationTagAndOversizedExe()
    {
        Assert.Throws<InvalidDataException>(() => ChannelManifest.ParseClient(DownloadFixture.Manifest(true, "1.2.3").Replace("updater-v", "v")));
        Assert.Throws<InvalidDataException>(() => ChannelManifest.ParseClient(DownloadFixture.Manifest(true, "1.2.3").Replace("\"size\":4", "\"size\":536870913")));
    }

    [TestMethod]
    public void SemanticComparisonUsesNumericComponentsAndRejectsNoncanonicalVersions()
    {
        Assert.IsTrue(SemVersion.Parse("1.10.0").CompareTo(SemVersion.Parse("1.9.9")) > 0);
        foreach (var value in new[] { "1.0", "v1.0.0", "01.0.0", "1.0.0-beta", "-1.0.0", "1.0.0 " })
            Assert.Throws<InvalidDataException>(() => SemVersion.Parse(value));
    }

    [TestMethod]
    public async Task RequestsUseOnlyGetAndVersionUserAgent()
    {
        using var fixture = new DownloadFixture();
        await fixture.Client.GetStableAsync(default);
        Assert.AreEqual("GET", fixture.Requests.Single().Method.Method);
        Assert.AreEqual(ChannelClient.StableUrl, fixture.Requests.Single().Uri.AbsoluteUri);
        Assert.AreEqual("ASA-RU-Fix-Updater/1.0.0", fixture.Requests.Single().UserAgent);
    }

    [TestMethod]
    public async Task NetworkFailurePropagates()
    {
        using var fixture = new DownloadFixture();
        fixture.Respond = _ => throw new HttpRequestException("offline");
        await Assert.ThrowsAsync<HttpRequestException>(() => fixture.Client.GetStableAsync(default));
    }

    [TestMethod]
    public async Task DownloadSignalsProgressBeforeWaitingForHttpHeaders()
    {
        using var fixture = new DownloadFixture();
        var progress = new ImmediateProgress();
        fixture.Respond = _ =>
        {
            Assert.AreEqual(0d, progress.Value, "Slow headers must already enable the skip window");
            throw new HttpRequestException("fixture offline");
        };
        var artifact = ChannelManifest.ParseStable(DownloadFixture.Manifest(false, "1.2.3")).Artifact;
        await Assert.ThrowsAsync<HttpRequestException>(() => fixture.Client.DownloadAsync(artifact, Path.Combine(fixture.Root, "target"), progress, default));
    }
    private sealed class ImmediateProgress : IProgress<double>
    {
        public double Value = -1;
        public void Report(double value) => Value = value;
    }

    [TestMethod]
    public async Task ManifestLimitRejectsOversizedContent()
    {
        using var fixture = new DownloadFixture();
        fixture.Respond = _ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(new string(' ', 131073)) };
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Client.GetStableAsync(default));
    }

    [TestMethod]
    public async Task ValidatedDownloadWritesExactBytes()
    {
        using var fixture = new DownloadFixture();
        var artifact = (await fixture.Client.GetStableAsync(default)).Artifact;
        var target = Path.Combine(fixture.Root, "download");
        await fixture.Client.DownloadAsync(artifact, target, null, default);
        CollectionAssert.AreEqual(DownloadFixture.Bytes, File.ReadAllBytes(target));
    }

    [TestMethod]
    [DataRow("hash")]
    [DataRow("truncated")]
    [DataRow("oversized")]
    [DataRow("status")]
    public async Task FailedDownloadPreservesExistingDestinationAndCleansTemp(string mode)
    {
        using var fixture = new DownloadFixture();
        var artifact = (await fixture.Client.GetStableAsync(default)).Artifact;
        fixture.Respond = _ => mode == "status" ? new(HttpStatusCode.ServiceUnavailable) : new(HttpStatusCode.OK)
        { Content = new ByteArrayContent(mode == "truncated" ? [1] : mode == "oversized" ? [1, 2, 3, 4, 5] : [9, 9, 9, 9]) };
        var target = Path.Combine(fixture.Root, "download");
        File.WriteAllText(target, "old");
        await Assert.ThrowsAsync<Exception>(() => fixture.Client.DownloadAsync(artifact, target, null, default));
        Assert.AreEqual("old", File.ReadAllText(target));
        Assert.AreEqual(1, Directory.GetFiles(fixture.Root).Length);
    }

    [TestMethod]
    [DataRow("http://release-assets.githubusercontent.com/file")]
    [DataRow("https://evil.example/file")]
    [DataRow("https://github.com/evil/repository/releases/download/v1.2.3/ASA_RU_Fix_P.pak")]
    public async Task RejectsRedirectBeforeContactingUnsafeDestination(string location)
    {
        using var fixture = new DownloadFixture();
        var artifact = (await fixture.Client.GetStableAsync(default)).Artifact;
        fixture.Requests.Clear();
        fixture.Respond = _ => new(HttpStatusCode.Redirect) { Headers = { Location = new Uri(location) } };
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Client.DownloadAsync(artifact, Path.Combine(fixture.Root, "download"), null, default));
        Assert.AreEqual(1, fixture.Requests.Count);
        Assert.AreEqual(0, Directory.GetFiles(fixture.Root).Length);
    }

    [TestMethod]
    public async Task AllowsGithubHttpsCdnRedirect()
    {
        using var fixture = new DownloadFixture();
        var artifact = (await fixture.Client.GetStableAsync(default)).Artifact;
        fixture.Requests.Clear();
        fixture.Respond = uri => uri.Host == "github.com" ? new(HttpStatusCode.Redirect)
        { Headers = { Location = new Uri("https://release-assets.githubusercontent.com/file?signature=ok") } }
        : new(HttpStatusCode.OK) { Content = new ByteArrayContent(DownloadFixture.Bytes) };
        await fixture.Client.DownloadAsync(artifact, Path.Combine(fixture.Root, "download"), null, default);
        Assert.AreEqual(2, fixture.Requests.Count);
    }

    [TestMethod]
    public async Task CancellationLeavesNoTemporaryFiles()
    {
        using var fixture = new DownloadFixture();
        var artifact = (await fixture.Client.GetStableAsync(default)).Artifact;
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await Assert.ThrowsAsync<OperationCanceledException>(() => fixture.Client.DownloadAsync(artifact, Path.Combine(fixture.Root, "download"), null, cancellation.Token));
        Assert.AreEqual(0, Directory.GetFiles(fixture.Root).Length);
    }

    [TestMethod]
    public async Task ManifestCannotRedirectIntoDifferentChannel()
    {
        using var fixture = new DownloadFixture();
        fixture.Respond = _ => new(HttpStatusCode.Redirect) { Headers = { Location = new Uri(ChannelClient.ClientUrl) } };
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Client.GetStableAsync(default));
        Assert.AreEqual(1, fixture.Requests.Count);
    }

    [TestMethod]
    [DataRow(1)]
    [DataRow(5)]
    public async Task ChunkedDownloadCannotBypassActualSizeChecks(int length)
    {
        using var fixture = new DownloadFixture();
        var artifact = (await fixture.Client.GetStableAsync(default)).Artifact;
        fixture.Respond = _ => new(HttpStatusCode.OK) { Content = new ChunkedContent(new byte[length]) };
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Client.DownloadAsync(artifact, Path.Combine(fixture.Root, "download"), null, default));
        Assert.AreEqual(0, Directory.GetFiles(fixture.Root).Length);
    }

    [TestMethod]
    public async Task ManifestReadHasBoundedTimeout()
    {
        using var http = new HttpClient(new BlockingHandler());
        var watch = System.Diagnostics.Stopwatch.StartNew();
        await Assert.ThrowsAsync<OperationCanceledException>(() => new ChannelClient(http, "1.0.0").GetStableAsync(default));
        Assert.IsTrue(watch.Elapsed < TimeSpan.FromSeconds(10));
    }

    [TestMethod]
    public void DuplicateOrMalformedJsonIsRejected()
    {
        Assert.Throws<InvalidDataException>(() => ChannelManifest.ParseStable("{"));
        Assert.Throws<InvalidDataException>(() => ChannelManifest.ParseStable(DownloadFixture.Manifest(false, "1.2.3").Replace("\"schema\":1", "\"schema\":1,\"schema\":1")));
    }

    private sealed class ChunkedContent(byte[] data) : HttpContent
    {
        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) => stream.WriteAsync(data).AsTask();
        protected override Task<Stream> CreateContentReadStreamAsync() => Task.FromResult<Stream>(new MemoryStream(data));
    }
    private sealed class BlockingHandler : HttpMessageHandler
    {
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            throw new InvalidOperationException("unreachable");
        }
    }
}

internal sealed class DownloadFixture : IDisposable
{
    internal static readonly byte[] Bytes = [1, 2, 3, 4];
    internal static string Hash => Convert.ToHexStringLower(SHA256.HashData(Bytes));
    internal string Root { get; } = Path.Combine(Path.GetTempPath(), "asa-download-tests-" + Guid.NewGuid().ToString("N"));
    internal List<(HttpMethod Method, Uri Uri, string UserAgent)> Requests { get; } = [];
    internal Func<Uri, HttpResponseMessage> Respond { get; set; }
    internal ChannelClient Client { get; }
    private readonly HttpClient http;
    internal DownloadFixture(bool client = false, string version = "1.2.3")
    {
        Directory.CreateDirectory(Root);
        Respond = uri => new(HttpStatusCode.OK) { Content = uri.Host == "raw.githubusercontent.com"
            ? new StringContent(Manifest(uri.AbsolutePath.EndsWith("client.json"), version)) : new ByteArrayContent(Bytes) };
        http = new HttpClient(new Handler(this));
        Client = new ChannelClient(http, "1.0.0");
    }
    internal static string Manifest(bool client, string version) => JsonSerializer.Serialize(new
    {
        schema = 1, channel = "stable", version,
        release = new { tag = (client ? "updater-v" : "v") + version },
        artifact = new { filename = client ? "ASA-RU-Fix.exe" : "ASA_RU_Fix_P.pak", size = Bytes.Length,
            sha256 = Hash, download_url = "https://github.com/andreymukha/ASA-RU-Fix/releases/download/" +
            (client ? "updater-v" : "v") + version + "/" + (client ? "ASA-RU-Fix.exe" : "ASA_RU_Fix_P.pak") }
    });
    public void Dispose() { http.Dispose(); Directory.Delete(Root, true); }
    private sealed class Handler(DownloadFixture fixture) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            fixture.Requests.Add((request.Method, request.RequestUri!, request.Headers.UserAgent.ToString()));
            return Task.FromResult(fixture.Respond(request.RequestUri!));
        }
    }
}
