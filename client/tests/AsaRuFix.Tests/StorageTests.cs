using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Globalization;

namespace AsaRuFix.Tests;

[TestClass]
public class StorageTests
{
    [TestMethod]
    public void ConstructingPathsDoesNotInstallAnything()
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
        var paths = new AppPaths(root);
        Assert.IsFalse(Directory.Exists(root));
        Assert.AreEqual(Path.Combine(root, "ASA-RU-Fix.exe"), paths.Executable);
    }

    [TestMethod]
    public void ConfigRoundTripsExactOptionsAndRetainsRecoveryCopy()
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
        try
        {
            var store = new ConfigStore(new AppPaths(root));
            var value = new ClientConfig { GamePath = "C:\\Игра с пробелами", OriginalLaunchOptions = "  -foo \"\" -bar  " };
            store.Save(value);
            Assert.AreEqual(value.OriginalLaunchOptions, store.Load()!.OriginalLaunchOptions);
            value.UpdaterVersion = "1.0.1"; store.Save(value);
            File.WriteAllText(store.Paths.Config, "{broken");
            Assert.AreEqual("1.0.0", store.Load()!.UpdaterVersion);
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }

    [TestMethod]
    public void FirstInstallHasRecoveryCopyAndRepairNeverBacksUpCorruptPrimary()
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
        try
        {
            var store = new ConfigStore(new AppPaths(root));
            store.Save(new() { OriginalLaunchOptions = " -high " });
            File.WriteAllText(store.Paths.Config, "{broken");
            Assert.AreEqual(" -high ", store.Load()!.OriginalLaunchOptions);
            store.Save(new() { UpdaterVersion = "1.0.1", OriginalLaunchOptions = " -high " });
            File.WriteAllText(store.Paths.Config, "{broken again");
            Assert.AreEqual(" -high ", store.Load()!.OriginalLaunchOptions);
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }

    [TestMethod]
    public void LoggerUsesLocalIso8601TimestampAndPreservesEntryContent()
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
        try
        {
            var logger = new LocalLogger(new AppPaths(root));
            var before = DateTimeOffset.UtcNow;
            logger.Write("translation-Current", "1.0.0");
            var after = DateTimeOffset.UtcNow;
            var entry = File.ReadAllText(Path.Combine(root, "logs", "updater.log"));
            var separator = entry.IndexOf(' ');
            Assert.IsTrue(separator > 0);
            var timestampText = entry[..separator];
            Assert.IsTrue(DateTimeOffset.TryParseExact(timestampText, "O", CultureInfo.InvariantCulture,
                DateTimeStyles.None, out var timestamp));
            Assert.AreEqual(TimeZoneInfo.Local.GetUtcOffset(timestamp), timestamp.Offset);
            Assert.AreEqual(timestamp.ToString("O", CultureInfo.InvariantCulture), timestampText);
            Assert.IsTrue(timestamp >= before && timestamp <= after);
            Assert.AreEqual(" translation-Current 1.0.0\n", entry[separator..]);
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }

    [TestMethod]
    public void LoggerRotatesAndNeverExceedsBoundedNumberOfFiles()
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString());
        try
        {
            var logger = new LocalLogger(new AppPaths(root), 128);
            for (var i = 0; i < 100; i++) logger.Write("test", new string('x', 90));
            Assert.IsTrue(Directory.GetFiles(Path.Combine(root, "logs")).Length <= 4);
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }
}
