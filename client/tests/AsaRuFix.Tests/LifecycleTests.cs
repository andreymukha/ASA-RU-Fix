using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public class LifecycleTests
{
    private sealed class Platform : IClientPlatform
    {
        public bool SteamRunning; public bool GameRunning; public bool Registered;
        public bool IsSteamRunning(string root) => SteamRunning;
        public bool IsGameRunning(string root) => GameRunning;
        public void Register(string exe, string version) => Registered = true;
        public void Unregister() => Registered = false;
    }
    [TestMethod]
    public async Task FixtureInstallRepairUninstallPreservesUserData()
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
        Directory.CreateDirectory(root);
        try
        {
            var steam = Path.Combine(root, "Steam");
            var game = Path.Combine(steam, "steamapps/common/ARK");
            Directory.CreateDirectory(Path.Combine(game, "ShooterGame/Binaries/Win64"));
            Directory.CreateDirectory(Path.Combine(game, "ShooterGame/Content/Paks"));
            var vdf = Path.Combine(steam, "userdata/123/config/localconfig.vdf");
            Directory.CreateDirectory(Path.GetDirectoryName(vdf)!);
            var unrelated = "\"other\" \"Данные игрока\"\n";
            File.WriteAllText(vdf, unrelated + "\"UserLocalConfigStore\" { \"Software\" { \"Valve\" { \"Steam\" { \"apps\" { \"2399830\" { \"LaunchOptions\" \" -high  \" } } } } } }");
            var user = new SteamUser("123", "Игрок", vdf);
            var install = new SteamInstallation(steam, game, new[] { user }, "123");
            var store = new ConfigStore(new AppPaths(Path.Combine(root, "Installed")));
            var platform = new Platform();
            var bootstrap = Path.Combine(root, "Downloaded.exe"); File.WriteAllText(bootstrap, "fixture executable");
            async Task<(string Version, string Sha256)> Update(string folder, CancellationToken ct)
            {
                await File.WriteAllTextAsync(Path.Combine(folder, "ShooterGame/Content/Paks/ASA_RU_Fix_P.pak"), "fixture translation", ct);
                return ("1.0.0", "a".PadLeft(64, 'a'));
            }
            var installer = new Installer(store, platform, Update);
            await installer.InstallAsync(install, user, bootstrap, "1.0.0", CancellationToken.None);
            Assert.IsTrue(File.Exists(store.Paths.Executable));
            Assert.IsTrue(platform.Registered);
            Assert.AreEqual(" -high  ", store.Load()!.OriginalLaunchOptions);
            Assert.IsTrue(File.ReadAllText(vdf).StartsWith(unrelated));
            await installer.InstallAsync(install, user, store.Paths.Executable, "1.0.0", CancellationToken.None);
            Assert.AreEqual(" -high  ", store.Load()!.OriginalLaunchOptions);
            new Uninstaller(store, platform).RemoveIntegrationAndData();
            Assert.AreEqual(" -high  ", LaunchOptionsManager.Read(vdf));
            Assert.IsFalse(platform.Registered);
            Assert.IsFalse(File.Exists(Path.Combine(game, "ShooterGame/Content/Paks/ASA_RU_Fix_P.pak")));
            Assert.IsTrue(File.Exists(bootstrap));
        }
        finally { Directory.Delete(root, true); }
    }

    [TestMethod]
    public async Task RunningSteamOrGamePreventsAllInstallWrites()
    {
        foreach (var runningGame in new[] { false, true })
        {
            var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
            try
            {
                var store = new ConfigStore(new AppPaths(root));
                var platform = new Platform { SteamRunning = !runningGame, GameRunning = runningGame };
                var installer = new Installer(store, platform, (p, c) => throw new AssertFailedException("download must not be called"));
                await Assert.ThrowsAsync<InvalidOperationException>(() => installer.InstallAsync(
                    new SteamInstallation("Steam", "Game", [], null), new SteamUser("1", "", "cfg"), "source", "1.0.0", CancellationToken.None));
                Assert.IsFalse(Directory.Exists(root));
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
        }
    }

    [TestMethod]
    public void AmbiguousEditedIntegrationDoesNotDeleteUpdater()
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
        try
        {
            var store = new ConfigStore(new AppPaths(root));
            Directory.CreateDirectory(root); File.WriteAllText(store.Paths.Executable, "keep");
            var vdf = Path.Combine(root, "localconfig.vdf");
            File.WriteAllText(vdf, "\"UserLocalConfigStore\" {\"Software\" {\"Valve\" {\"Steam\" {\"apps\" {\"2399830\" {\"LaunchOptions\" \"complex ASA-RU-Fix.exe --steam-launch edited\"}}}}}}");
            store.Save(new ClientConfig { SteamPath = root, GamePath = root, Integrations = [new() { AccountId="1", LocalConfigPath=vdf, ManagedLaunchOptions="old", OriginalLaunchOptions="-old" }] });
            Assert.Throws<InvalidOperationException>(() => new Uninstaller(store, new Platform()).RemoveIntegrationAndData());
            Assert.IsTrue(File.Exists(store.Paths.Executable));
            Assert.IsTrue(File.Exists(store.Paths.Config));
        }
        finally { Directory.Delete(root, true); }
    }
}
