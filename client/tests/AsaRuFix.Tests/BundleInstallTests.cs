using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public sealed class BundleInstallTests
{
    private const string Pak = "ASA_RU_Fix_P.pak";
    private const string Utoc = "ASA_RU_Fix_P.utoc";
    private const string Ucas = "ASA_RU_Fix_P.ucas";
    private static readonly Dictionary<string, byte[]> Files = new()
    {
        [Pak] = [1, 2, 3, 4], [Utoc] = [5, 6], [Ucas] = [7, 8, 9],
    };

    private static (string Game, string Paks, string Stage) Create(DownloadFixture fixture)
    {
        string game = Path.Combine(fixture.Root, "game");
        string paks = Path.Combine(game, "ShooterGame", "Content", "Paks");
        Directory.CreateDirectory(paks);
        File.WriteAllText(Path.Combine(paks, Pak), "previous");
        return (game, paks, Path.Combine(fixture.Root, "stage"));
    }

    private static void UseBundle(DownloadFixture fixture, string? corrupted = null)
    {
        var stable = JsonNode.Parse(DownloadFixture.Manifest(false, "1.2.2"))!.AsObject();
        stable["bundle"] = JsonSerializer.SerializeToNode(new
        {
            version = "1.2.3", release = new { tag = "v1.2.3" },
            artifacts = Files.Select(entry => new
            {
                filename = entry.Key, size = entry.Value.Length,
                sha256 = Convert.ToHexStringLower(SHA256.HashData(entry.Value)),
                download_url = "https://github.com/andreymukha/ASA-RU-Fix/releases/download/v1.2.3/" + entry.Key,
            }),
        });
        fixture.Respond = uri =>
        {
            var filename = Path.GetFileName(uri.AbsolutePath);
            return new(HttpStatusCode.OK)
            {
                Content = uri == new Uri(ChannelClient.StableUrl) ? new StringContent(stable.ToJsonString()) :
                    new ByteArrayContent(filename == corrupted ? [0] : Files[filename]),
            };
        };
    }

    [TestMethod]
    public async Task MigratesLegacyPakRepairsMissingCompanionAndSkipsCurrentBundle()
    {
        using var fixture = new DownloadFixture();
        var (game, paks, stage) = Create(fixture);
        UseBundle(fixture);
        var updater = new PakUpdater(fixture.Client);
        Assert.AreEqual("Updated", (await updater.UpdateAsync(game, stage, () => false, null, default)).Status);
        foreach (var (file, bytes) in Files)
            CollectionAssert.AreEqual(bytes, File.ReadAllBytes(Path.Combine(paks, file)));
        fixture.Requests.Clear();
        Assert.AreEqual("Current", (await updater.UpdateAsync(game, stage, () => false, null, default)).Status);
        Assert.HasCount(1, fixture.Requests);
        File.Delete(Path.Combine(paks, Utoc));
        Assert.AreEqual("Updated", (await updater.UpdateAsync(game, stage, () => false, null, default)).Status);
        CollectionAssert.AreEqual(Files[Utoc], File.ReadAllBytes(Path.Combine(paks, Utoc)));
    }

    [TestMethod]
    public async Task CorruptCompanionLeavesOriginalPakAndNoOtherGameFiles()
    {
        using var fixture = new DownloadFixture();
        var (game, paks, stage) = Create(fixture);
        UseBundle(fixture, Utoc);
        await Assert.ThrowsAsync<Exception>(() => new PakUpdater(fixture.Client).UpdateAsync(game, stage, () => false, null, default));
        Assert.AreEqual("previous", File.ReadAllText(Path.Combine(paks, Pak)));
        Assert.HasCount(1, Directory.GetFileSystemEntries(paks));
    }

    [TestMethod]
    public async Task RefusesUnownedConflictingCompanion()
    {
        using var fixture = new DownloadFixture();
        var (game, paks, stage) = Create(fixture);
        UseBundle(fixture);
        string target = Path.Combine(paks, Utoc);
        File.WriteAllText(target, "other");
        await Assert.ThrowsAsync<InvalidOperationException>(() => new PakUpdater(fixture.Client).UpdateAsync(game, stage, () => false, null, default));
        Assert.AreEqual("other", File.ReadAllText(target));
        Assert.AreEqual("previous", File.ReadAllText(Path.Combine(paks, Pak)));
        Assert.IsFalse(File.Exists(Path.Combine(paks, Ucas)));
    }

    [TestMethod]
    public async Task WriteFailureAfterFirstCompanionRollsBack()
    {
        using var fixture = new DownloadFixture();
        var (game, paks, stage) = Create(fixture);
        UseBundle(fixture);
        var blockedTarget = Path.Combine(paks, Utoc);
        Directory.CreateDirectory(blockedTarget);
        await Assert.ThrowsAsync<IOException>(() => new PakUpdater(fixture.Client).UpdateAsync(game, stage, () => false, null, default));
        Assert.AreEqual("previous", File.ReadAllText(Path.Combine(paks, Pak)));
        Assert.IsFalse(File.Exists(Path.Combine(paks, Ucas)));
        Assert.IsTrue(Directory.Exists(blockedTarget));
    }

    [TestMethod]
    public async Task NextAttemptRecoversInterruptedBundleBeforeFetchingManifest()
    {
        using var fixture = new DownloadFixture();
        var (game, paks, stage) = Create(fixture);
        UseBundle(fixture);
        var updater = new PakUpdater(fixture.Client);
        bool Interrupted() => File.Exists(Path.Combine(paks, Ucas));
        await Assert.ThrowsAsync<PakRecoveryException>(() => updater.UpdateAsync(game, stage, Interrupted, null, default));
        Assert.IsTrue(PakUpdater.NeedsRecovery(game));
        Assert.IsFalse(File.Exists(Path.Combine(paks, Pak)));
        fixture.Respond = _ =>
        {
            Assert.AreEqual("previous", File.ReadAllText(Path.Combine(paks, Pak)));
            Assert.IsFalse(File.Exists(Path.Combine(paks, Ucas)));
            Assert.IsFalse(PakUpdater.NeedsRecovery(game));
            return new(HttpStatusCode.BadGateway);
        };
        await Assert.ThrowsAsync<HttpRequestException>(() => updater.UpdateAsync(game, stage, () => false, null, default));
    }

    [TestMethod]
    public async Task UninstallRemovesManagedBundleAndRetainsUnrelatedFiles()
    {
        using var fixture = new DownloadFixture();
        var (game, paks, stage) = Create(fixture);
        UseBundle(fixture);
        await new PakUpdater(fixture.Client).UpdateAsync(game, stage, () => false, null, default);
        string unrelated = Path.Combine(paks, "other.pak");
        File.WriteAllText(unrelated, "other");
        var store = new ConfigStore(new AppPaths(Path.Combine(fixture.Root, "installed")));
        string vdf = Path.Combine(fixture.Root, "localconfig.vdf");
        File.WriteAllText(vdf, """
            "UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "2399830" { "LaunchOptions" "managed" } } } } } }
            """);
        store.Save(new ClientConfig
        {
            SteamPath = fixture.Root, GamePath = game,
            Integrations = [new() { AccountId = "1", LocalConfigPath = vdf, ManagedLaunchOptions = "managed", OriginalLaunchOptions = "-high" }],
        });
        var platform = new TestPlatform();
        new Uninstaller(store, platform).RemoveIntegrationAndData();
        Assert.AreEqual("-high", LaunchOptionsManager.Read(vdf));
        Assert.IsTrue(platform.Unregistered);
        CollectionAssert.AreEqual(new[] { unrelated }, Directory.GetFileSystemEntries(paks));
    }

    [TestMethod]
    public async Task LaunchPropagatesRecoveryFailureBeforeStartingGame()
    {
        var error = await Assert.ThrowsAsync<PakRecoveryException>(() => new LaunchCoordinator().RunAsync(
            ["missing-game.exe"], "", _ => throw new PakRecoveryException("Pending restore"), default));
        Assert.AreEqual("Pending restore", error.Message);
    }

    private sealed class TestPlatform : IClientPlatform
    {
        internal bool Unregistered;
        public bool IsSteamRunning(string root) => false;
        public bool IsGameRunning(string root) => false;
        public void Register(string exe, string version) { }
        public void Unregister() => Unregistered = true;
    }
}
