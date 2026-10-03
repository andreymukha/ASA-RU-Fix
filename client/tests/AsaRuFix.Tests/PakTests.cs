using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public sealed class PakTests
{
    private static string PakPath(DownloadFixture fixture)
    {
        var directory = Path.Combine(fixture.Root, "Game", "ShooterGame", "Content", "Paks");
        Directory.CreateDirectory(directory);
        return Path.Combine(directory, "ASA_RU_Fix_P.pak");
    }
    [TestMethod]
    public async Task SameActualHashSkipsDownload()
    {
        using var fixture = new DownloadFixture();
        File.WriteAllBytes(PakPath(fixture), DownloadFixture.Bytes);
        var result = await new PakUpdater(fixture.Client).UpdateAsync(Path.Combine(fixture.Root, "Game"), Path.Combine(fixture.Root, "stage"), () => false, null, default);
        Assert.AreEqual("Current", result.Status);
        Assert.AreEqual(1, fixture.Requests.Count);
    }
    [TestMethod]
    public async Task DifferentHashAtomicallyReplacesPak()
    {
        using var fixture = new DownloadFixture();
        var target = PakPath(fixture);
        File.WriteAllText(target, "old");
        var result = await new PakUpdater(fixture.Client).UpdateAsync(Path.Combine(fixture.Root, "Game"), Path.Combine(fixture.Root, "stage"), () => false, null, default);
        Assert.AreEqual("Updated", result.Status);
        CollectionAssert.AreEqual(DownloadFixture.Bytes, File.ReadAllBytes(target));
        Assert.AreEqual(1, Directory.GetFiles(Path.GetDirectoryName(target)!).Length);
    }
    [TestMethod]
    public async Task RunningGamePreventsAnyWrite()
    {
        using var fixture = new DownloadFixture();
        var target = PakPath(fixture);
        File.WriteAllText(target, "old");
        await Assert.ThrowsAsync<InvalidOperationException>(() => new PakUpdater(fixture.Client).UpdateAsync(Path.Combine(fixture.Root, "Game"), Path.Combine(fixture.Root, "stage"), () => true, null, default));
        Assert.IsFalse(Directory.Exists(Path.Combine(fixture.Root, "stage")));
        Assert.AreEqual("old", File.ReadAllText(target));
    }
    [TestMethod]
    public async Task GameStartingDuringDownloadPreventsReplacement()
    {
        using var fixture = new DownloadFixture();
        var target = PakPath(fixture);
        File.WriteAllText(target, "old");
        int checks = 0;
        await Assert.ThrowsAsync<InvalidOperationException>(() => new PakUpdater(fixture.Client).UpdateAsync(Path.Combine(fixture.Root, "Game"), Path.Combine(fixture.Root, "stage"), () => ++checks >= 2, null, default));
        Assert.AreEqual("old", File.ReadAllText(target));
        Assert.AreEqual(1, Directory.GetFiles(Path.GetDirectoryName(target)!).Length);
    }
    [TestMethod]
    public void SimulatedReplacementFailurePreservesOldTarget()
    {
        using var fixture = new DownloadFixture();
        var target = PakPath(fixture);
        File.WriteAllText(target, "old");
        var source = Path.Combine(fixture.Root, "source");
        File.WriteAllBytes(source, DownloadFixture.Bytes);
        Assert.Throws<IOException>(() => AtomicFile.InstallVerified(source, target, 4, DownloadFixture.Hash, () => throw new IOException("simulated")));
        Assert.AreEqual("old", File.ReadAllText(target));
        Assert.AreEqual(1, Directory.GetFiles(Path.GetDirectoryName(target)!).Length);
    }
    [TestMethod]
    public void InvalidSourceDoesNotReplaceTarget()
    {
        using var fixture = new DownloadFixture();
        var target = PakPath(fixture);
        File.WriteAllText(target, "old");
        var source = Path.Combine(fixture.Root, "source");
        File.WriteAllBytes(source, [9, 9, 9, 9]);
        Assert.Throws<InvalidDataException>(() => AtomicFile.InstallVerified(source, target, 4, DownloadFixture.Hash));
        Assert.AreEqual("old", File.ReadAllText(target));
    }

    [TestMethod]
    [DataRow("hash")]
    [DataRow("truncated")]
    [DataRow("oversized")]
    [DataRow("status")]
    public async Task FailedPakDownloadPreservesInstalledPak(string mode)
    {
        using var fixture = new DownloadFixture();
        var target = PakPath(fixture);
        File.WriteAllText(target, "old");
        var respond = fixture.Respond;
        fixture.Respond = uri => uri.Host == "raw.githubusercontent.com" ? respond(uri) :
            mode == "status" ? new(System.Net.HttpStatusCode.BadGateway) : new(System.Net.HttpStatusCode.OK)
            { Content = new ByteArrayContent(mode == "truncated" ? [1] : mode == "oversized" ? [1, 2, 3, 4, 5] : [9, 9, 9, 9]) };
        await Assert.ThrowsAsync<Exception>(() => new PakUpdater(fixture.Client).UpdateAsync(Path.Combine(fixture.Root, "Game"), Path.Combine(fixture.Root, "stage"), () => false, null, default));
        Assert.AreEqual("old", File.ReadAllText(target));
        Assert.AreEqual(0, Directory.GetFiles(Path.Combine(fixture.Root, "stage")).Length);
        Assert.AreEqual(1, Directory.GetFiles(Path.GetDirectoryName(target)!).Length);
    }
}
