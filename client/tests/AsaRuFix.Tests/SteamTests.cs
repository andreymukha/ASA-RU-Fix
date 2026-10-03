using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public sealed class SteamTests
{
    [TestMethod]
    public void DiscoversGameInNonDefaultLibraryAndResolvesActiveAccount()
    {
        var root = Path.Combine(Path.GetTempPath(), "asa-steam-" + Guid.NewGuid().ToString("N"));
        try
        {
            var steam = Path.Combine(root, "Steam Client");
            var library = Path.Combine(root, "Other Library");
            Directory.CreateDirectory(Path.Combine(steam, "steamapps"));
            Directory.CreateDirectory(Path.Combine(steam, "config"));
            Directory.CreateDirectory(Path.Combine(library, "steamapps"));
            var game = Path.Combine(library, "steamapps", "common", "ARK Custom");
            Directory.CreateDirectory(Path.Combine(game, "ShooterGame", "Binaries", "Win64"));
            Directory.CreateDirectory(Path.Combine(game, "ShooterGame", "Content", "Paks"));
            File.WriteAllText(Path.Combine(steam, "steamapps", "libraryfolders.vdf"), "\"libraryfolders\" { \"1\" { \"path\" \"" + library.Replace("\\", "\\\\") + "\" } }");
            File.WriteAllText(Path.Combine(library, "steamapps", "appmanifest_2399830.acf"), "AppState { appid 2399830 installdir \"ARK Custom\" }");
            File.WriteAllText(Path.Combine(steam, "config", "loginusers.vdf"), "users { 76561197960265770 { PersonaName \"First player\" MostRecent 1 } 76561197960265771 { PersonaName \"Второй\" } }");
            foreach (var id in new[] { "42", "43" })
            {
                var config = Path.Combine(steam, "userdata", id, "config");
                Directory.CreateDirectory(config);
                File.WriteAllText(Path.Combine(config, "localconfig.vdf"), "UserLocalConfigStore {}");
            }
            var installation = SteamDiscovery.Find(steam, 43)!;
            Assert.AreEqual(game, installation.GamePath);
            Assert.AreEqual("43", installation.ActiveAccountId);
            Assert.AreEqual("Второй", SteamUserResolver.Resolve(installation)!.DisplayName);
            Assert.IsNull(SteamUserResolver.Resolve(SteamDiscovery.Find(steam)!));
            Assert.IsTrue(SteamDiscovery.IsGameDirectory(game));
        }
        finally { Directory.Delete(root, true); }
    }

    [TestMethod]
    public void SingleProfileMayBeResolvedWithoutActiveRegistry()
    {
        var user = new SteamUser("42", "Player", "fixture.vdf");
        Assert.AreEqual(user, SteamUserResolver.Resolve(new SteamInstallation("fixture", null, [user], null)));
        Assert.IsNull(SteamUserResolver.Resolve(new SteamInstallation("fixture", null, [user], "missing")));
    }

    [TestMethod]
    public void MissingSteamRootReturnsNull() => Assert.IsNull(SteamDiscovery.Find(Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"))));

    [TestMethod]
    public void GameDirectoryNeedsBothExpectedDirectories()
    {
        var root = Path.Combine(Path.GetTempPath(), "asa-game-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(Path.Combine(root, "ShooterGame", "Content", "Paks"));
            Assert.IsFalse(SteamDiscovery.IsGameDirectory(root));
            Directory.CreateDirectory(Path.Combine(root, "ShooterGame", "Binaries", "Win64"));
            Assert.IsTrue(SteamDiscovery.IsGameDirectory(root));
        }
        finally { Directory.Delete(root, true); }
    }
}
