using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public sealed class SelfUpdateTests
{
    [TestMethod]
    [DataRow("1.2.3")]
    [DataRow("2.0.0")]
    public async Task SameOrOlderChannelDoesNotDownload(string installedVersion)
    {
        using var fixture = new DownloadFixture(true);
        Assert.IsNull(await new SelfUpdater(fixture.Client).StageAsync(installedVersion, Path.Combine(fixture.Root, "updates"), default));
        Assert.AreEqual(1, fixture.Requests.Count);
        Assert.IsFalse(Directory.Exists(Path.Combine(fixture.Root, "updates")));
    }
    [TestMethod]
    public async Task NewerClientStagesVerifiedFixedFilename()
    {
        using var fixture = new DownloadFixture(true);
        var pending = await new SelfUpdater(fixture.Client).StageAsync("1.0.0", Path.Combine(fixture.Root, "updates"), default);
        Assert.IsNotNull(pending);
        Assert.AreEqual("new.pending.exe", Path.GetFileName(pending.FilePath));
        Assert.AreEqual(DownloadFixture.Hash, AtomicFile.Sha256(pending.FilePath));
        Assert.AreEqual("1.2.3", pending.Version);
    }
    [TestMethod]
    public async Task BadExeHashDoesNotStageUpdate()
    {
        using var fixture = new DownloadFixture(true);
        var respond = fixture.Respond;
        fixture.Respond = uri => uri.Host == "github.com" ? new(System.Net.HttpStatusCode.OK) { Content = new ByteArrayContent([9, 9, 9, 9]) } : respond(uri);
        await Assert.ThrowsAsync<InvalidDataException>(() => new SelfUpdater(fixture.Client).StageAsync("1.0.0", Path.Combine(fixture.Root, "updates"), default));
        Assert.AreEqual(0, Directory.GetFiles(Path.Combine(fixture.Root, "updates")).Length);
    }
    [TestMethod]
    public async Task FailedSelfReplacementPreservesInstalledUpdater()
    {
        using var fixture = new DownloadFixture(true);
        var pending = await new SelfUpdater(fixture.Client).StageAsync("1.0.0", Path.Combine(fixture.Root, "updates"), default);
        var installed = Path.Combine(fixture.Root, "ASA-RU-Fix.exe");
        File.WriteAllText(installed, "old exe");
        Assert.Throws<IOException>(() => SelfUpdater.Complete(pending!, installed, () => throw new IOException("simulated")));
        Assert.AreEqual("old exe", File.ReadAllText(installed));
        Assert.AreEqual(1, Directory.GetFiles(fixture.Root).Length);
    }
    [TestMethod]
    public async Task CompleteInstallsOnlyVerifiedPendingUnderInstallDirectory()
    {
        using var fixture = new DownloadFixture(true);
        var pending = await new SelfUpdater(fixture.Client).StageAsync("1.0.0", Path.Combine(fixture.Root, "updates"), default);
        var installed = Path.Combine(fixture.Root, "ASA-RU-Fix.exe");
        File.WriteAllText(installed, "old exe");
        SelfUpdater.Complete(pending!, installed);
        Assert.AreEqual(DownloadFixture.Hash, AtomicFile.Sha256(installed));
        Assert.Throws<InvalidDataException>(() => SelfUpdater.Complete(pending! with { FilePath = installed }, installed));
    }

    [TestMethod]
    public async Task CompleteRechecksPendingHashBeforeReplacement()
    {
        using var fixture = new DownloadFixture(true);
        var pending = await new SelfUpdater(fixture.Client).StageAsync("1.0.0", Path.Combine(fixture.Root, "updates"), default);
        var installed = Path.Combine(fixture.Root, "ASA-RU-Fix.exe");
        File.WriteAllText(installed, "old exe");
        File.WriteAllBytes(pending!.FilePath, [9, 9, 9, 9]);
        Assert.Throws<InvalidDataException>(() => SelfUpdater.Complete(pending, installed));
        Assert.AreEqual("old exe", File.ReadAllText(installed));
        Assert.AreEqual(1, Directory.GetFiles(fixture.Root).Length);
    }
}
