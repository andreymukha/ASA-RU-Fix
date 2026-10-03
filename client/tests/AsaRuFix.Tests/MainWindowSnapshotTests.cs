using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public class MainWindowSnapshotTests
{
    private sealed class Fixture : IDisposable
    {
        public string Root { get; } = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
        public AppPaths Paths { get; }
        public SteamUser User { get; }
        public SteamInstallation Steam { get; }
        public string Pak { get; }
        public Fixture(bool installed = true)
        {
            Paths = new AppPaths(Path.Combine(Root, "Installed"));
            string game = Path.Combine(Root, "Game");
            Directory.CreateDirectory(Path.Combine(game, "ShooterGame/Binaries/Win64"));
            Directory.CreateDirectory(Path.Combine(game, "ShooterGame/Content/Paks"));
            Pak = Path.Combine(game, "ShooterGame/Content/Paks/ASA_RU_Fix_P.pak");
            User = new("123", "Игрок", Path.Combine(Root, "localconfig.vdf"));
            Steam = new(Root, game, [User], "123");
            File.WriteAllText(User.LocalConfigPath, "\"UserLocalConfigStore\" {\"Software\" {\"Valve\" {\"Steam\" {\"apps\" {\"2399830\" {\"LaunchOptions\" \"\"}}}}}}");
            LaunchOptionsManager.Write(User.LocalConfigPath, LaunchOptionsManager.Managed(Paths.Executable), () => false);
            if (!installed) return;
            Directory.CreateDirectory(Paths.Root);
            File.WriteAllText(Paths.Executable, "fixture");
            File.WriteAllText(Pak, "fixture translation");
            var store = new ConfigStore(Paths);
            store.Save(new() { SteamPath = Root, GamePath = game, ManagedLaunchOptions = LaunchOptionsManager.Managed(Paths.Executable),
                Integrations = [new() { AccountId = User.AccountId, LocalConfigPath = User.LocalConfigPath,
                    ManagedLaunchOptions = LaunchOptionsManager.Managed(Paths.Executable), OriginalLaunchOptions = " -high " }] });
            store.SaveState(new() { TranslationVersion = "1.0.0", TranslationSha256 = AtomicFile.Sha256(Pak), CheckedAt = DateTimeOffset.UtcNow.ToString("O") });
        }
        public MainWindowSnapshot Read() => MainWindowSnapshotReader.Read(Paths, Steam, User, Paths.Executable);
        public void Dispose() { Directory.Delete(Root, true); }
    }
    [TestMethod] public void LocalHealthyEvidenceIsReadWithoutWrites()
    {
        using var fixture = new Fixture();
        var before = Directory.GetFiles(fixture.Root, "*", SearchOption.AllDirectories).ToDictionary(x => x, AtomicFile.Sha256);
        var snapshot = fixture.Read();
        Assert.IsTrue(MainWindowStateBuilder.Build(snapshot).Healthy);
        Assert.AreEqual(before.Count, Directory.GetFiles(fixture.Root, "*", SearchOption.AllDirectories).Length);
        foreach (var file in before) Assert.AreEqual(file.Value, AtomicFile.Sha256(file.Key));
    }
    [TestMethod] public void OrphanedWrapperHasNoSafeOriginalAndCreatesNothing()
    {
        using var fixture = new Fixture(installed: false);
        var snapshot = fixture.Read();
        Assert.IsTrue(snapshot.ManagedOptionsReferenced);
        Assert.IsFalse(snapshot.RecoverySafe);
        Assert.IsFalse(Directory.Exists(fixture.Paths.Root));
        Assert.IsTrue(MainWindowStateBuilder.Build(snapshot).PartialInstallation);
    }
    [TestMethod] public void MissingExecutableWithSavedOriginalCanRecover()
    {
        using var fixture = new Fixture(); File.Delete(fixture.Paths.Executable);
        var state = MainWindowStateBuilder.Build(fixture.Read());
        Assert.IsTrue(state.PartialInstallation); Assert.IsTrue(state.PrimaryEnabled);
    }
    [TestMethod] public void MismatchedPakCannotBeReportedAsInstalled()
    {
        using var fixture = new Fixture(); File.WriteAllText(fixture.Pak, "changed");
        Assert.IsFalse(fixture.Read().PakVerified);
        Assert.IsFalse(MainWindowStateBuilder.Build(fixture.Read()).Healthy);
    }
    [TestMethod] public void CorruptPrimaryConfigIsPartialButBackupCanProveSafeRecovery()
    {
        using var fixture = new Fixture(); File.WriteAllText(fixture.Paths.Config, "{broken");
        var snapshot = fixture.Read();
        Assert.IsFalse(snapshot.ConfigValid); Assert.IsTrue(snapshot.RecoverySafe);
        Assert.IsTrue(MainWindowStateBuilder.Build(snapshot).PartialInstallation);
    }
    [TestMethod] public void CorruptStateOrVdfNeverLooksHealthy()
    {
        using var fixture = new Fixture(); File.WriteAllText(fixture.Paths.State, "{broken");
        Assert.IsFalse(fixture.Read().StateValid);
        File.WriteAllText(fixture.User.LocalConfigPath, "{broken");
        Assert.IsFalse(fixture.Read().OptionsReadable); Assert.IsFalse(fixture.Read().RecoverySafe);
        Assert.IsFalse(MainWindowStateBuilder.Build(fixture.Read()).Healthy);
    }
    [TestMethod] public void UnknownWrapperEditsBlockRecovery()
    {
        using var fixture = new Fixture();
        LaunchOptionsManager.Write(fixture.User.LocalConfigPath, LaunchOptionsManager.Managed(fixture.Paths.Executable) + " | unknown", () => false);
        Assert.IsFalse(fixture.Read().RecoverySafe);
    }
}
