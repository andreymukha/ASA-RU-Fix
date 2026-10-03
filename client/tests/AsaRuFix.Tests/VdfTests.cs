using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Text;

namespace AsaRuFix.Tests;

[TestClass]
public sealed class VdfTests
{
    [TestMethod]
    public void PatchChangesOnlyValueAndPreservesCommentsBomAndUnknownKeys()
    {
        var source = "\uFEFF// header\r\n\"root\"\r\n{\r\n\t\"unknown\" \"x\" // keep\r\n\t\"target\"\t\"old\"\r\n}\r\n";
        var result = VdfDocument.Parse(source).Set(["root", "target"], "a\\b\"c\n");
        Assert.AreEqual(source.Replace("\"old\"", "\"a\\\\b\\\"c\\n\""), result);
        Assert.AreEqual("a\\b\"c\n", VdfDocument.Parse(result).Get("root", "target"));
    }

    [TestMethod]
    public void MissingAncestorsAreInsertedWithoutChangingExistingText()
    {
        var source = "\"root\" { \"unknown\" \"keep\" } // tail\n";
        var result = VdfDocument.Parse(source).Set(["root", "a", "b", "value"], "new");
        Assert.IsTrue(result.StartsWith("\"root\" { \"unknown\" \"keep\" ", StringComparison.Ordinal));
        Assert.IsTrue(result.EndsWith("} // tail\n", StringComparison.Ordinal));
        Assert.AreEqual("new", VdfDocument.Parse(result).Get("root", "a", "b", "value"));
    }

    [TestMethod]
    public void DuplicateTargetFailsClosed()
    {
        var document = VdfDocument.Parse("root { key one KEY two }");
        Assert.ThrowsExactly<FormatException>(() => document.Get("root", "key"));
        Assert.ThrowsExactly<FormatException>(() => document.Set(["root", "key"], "three"));
    }

    [TestMethod]
    [DataRow("root { key }")]
    [DataRow("root { key \"unfinished }")]
    [DataRow("root { key value")]
    [DataRow("root { key value } }")]
    [DataRow("root { /* unfinished")]
    public void MalformedVdfFails(string source) => Assert.ThrowsExactly<FormatException>(() => VdfDocument.Parse(source));

    [TestMethod]
    public void ReadsUnquotedStringsBlockCommentsAndCaseInsensitivePaths()
    {
        var document = VdfDocument.Parse("/*ignored*/ Root { KEY \"C:\\path\\file\" }");
        Assert.AreEqual("C:\\path\\file", document.Get("root", "key"));
    }

    [TestMethod]
    public void WritePreservesUtf8BomAndCanRestoreAbsentEntry()
    {
        var path = TempPath();
        try
        {
            File.WriteAllText(path, "\"UserLocalConfigStore\" { \"keep\" \"value\" }\r\n", new UTF8Encoding(true));
            var original = File.ReadAllBytes(path);
            LaunchOptionsManager.Write(path, "-high", () => false);
            Assert.AreEqual("-high", LaunchOptionsManager.Read(path));
            CollectionAssert.AreEqual(original[..3], File.ReadAllBytes(path)[..3]);
            LaunchOptionsManager.Write(path, null, () => false);
            Assert.IsNull(LaunchOptionsManager.Read(path));
            Assert.AreEqual("value", VdfDocument.Parse(File.ReadAllText(path)).Get("UserLocalConfigStore", "keep"));
        }
        finally { File.Delete(path); }
    }

    [TestMethod]
    public void RunningSteamPreventsAnyWrite()
    {
        var path = TempPath();
        try
        {
            File.WriteAllText(path, "root { keep value }");
            var original = File.ReadAllBytes(path);
            Assert.ThrowsExactly<InvalidOperationException>(() => LaunchOptionsManager.Write(path, "new", () => true));
            CollectionAssert.AreEqual(original, File.ReadAllBytes(path));
        }
        finally { File.Delete(path); }
    }

    [TestMethod]
    public void SteamStartingBeforeReplacementPreservesOldFile()
    {
        var path = TempPath();
        try
        {
            const string original = "UserLocalConfigStore { keep old }";
            File.WriteAllText(path, original);
            int calls = 0;
            Assert.ThrowsExactly<InvalidOperationException>(() => LaunchOptionsManager.Write(path, "-new", () => ++calls == 2));
            Assert.AreEqual(original, File.ReadAllText(path));
            Assert.AreEqual(0, Directory.GetFiles(Path.GetDirectoryName(path)!, Path.GetFileName(path) + ".*.tmp").Length);
        }
        finally { File.Delete(path); }
    }

    [TestMethod]
    public void InvalidVdfCannotBeReplaced()
    {
        var path = TempPath();
        try
        {
            const string original = "UserLocalConfigStore { broken }";
            File.WriteAllText(path, original);
            Assert.ThrowsExactly<FormatException>(() => LaunchOptionsManager.Write(path, "-new", () => false));
            Assert.AreEqual(original, File.ReadAllText(path));
        }
        finally { File.Delete(path); }
    }

    [TestMethod]
    public void Utf16EncodingIsPreserved()
    {
        var path = TempPath();
        try
        {
            File.WriteAllText(path, "UserLocalConfigStore { keep \"русский\" }", Encoding.Unicode);
            LaunchOptionsManager.Write(path, "-new", () => false);
            CollectionAssert.AreEqual(new byte[] { 0xFF, 0xFE }, File.ReadAllBytes(path)[..2]);
            Assert.AreEqual("-new", LaunchOptionsManager.Read(path));
            Assert.AreEqual("русский", VdfDocument.Parse(File.ReadAllText(path)).Get("UserLocalConfigStore", "keep"));
        }
        finally { File.Delete(path); }
    }

    [TestMethod]
    public void StaleWriteDoesNotOverwriteConcurrentChanges()
    {
        var path = TempPath();
        try
        {
            File.WriteAllText(path, "root { keep original }");
            int calls = 0;
            Assert.ThrowsExactly<IOException>(() => LaunchOptionsManager.Write(path, "new", () =>
            {
                if (++calls == 2) File.WriteAllText(path, "root { keep concurrent }");
                return false;
            }));
            Assert.AreEqual("root { keep concurrent }", File.ReadAllText(path));
            Assert.AreEqual(0, Directory.GetFiles(Path.GetDirectoryName(path)!, Path.GetFileName(path) + ".*.tmp").Length);
        }
        finally { File.Delete(path); }
    }

    [TestMethod]
    public void RestoreRejectsEditedWrapperAndPreservesSafelyAddedFlags()
    {
        var managed = LaunchOptionsManager.Managed(@"C:\Users\Name\ASA-RU-Fix.exe");
        Assert.AreEqual("\"C:\\Users\\Name\\ASA-RU-Fix.exe\" --steam-launch -- %command%", managed);
        Assert.IsNull(LaunchOptionsManager.Restore(managed, managed, null));
        Assert.AreEqual(" -high  ", LaunchOptionsManager.Restore(managed, managed, " -high  "));
        Assert.AreEqual("-old -new", LaunchOptionsManager.Restore(managed + " -new", managed, "-old"));
        Assert.ThrowsExactly<InvalidOperationException>(() => LaunchOptionsManager.Restore(managed.Replace("--steam-launch", "--other"), managed, "-old"));
    }

    private static string TempPath() => Path.Combine(Path.GetTempPath(), "asa-vdf-" + Guid.NewGuid().ToString("N") + ".vdf");
}
