using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public class CleanupTests
{
    [TestMethod]
    public async Task HiddenReaperRetriesLockedFileAndHandlesSpecialPathCharacters()
    {
        var root = Path.Combine(Path.GetTempPath(), "ASA test & %literal% " + Guid.NewGuid());
        Directory.CreateDirectory(root);
        var executable = Path.Combine(root, "ASA-RU-Fix.exe");
        await File.WriteAllTextAsync(executable, "fixture");
        try
        {
            using var held = new FileStream(executable, FileMode.Open, FileAccess.Read, FileShare.None);
            using var reaper = SelfDeletion.Start(executable);
            await Task.Delay(300);
            Assert.IsTrue(File.Exists(executable), "Reaper must not delete a running/locked helper");
            held.Dispose();
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            await reaper.WaitForExitAsync(deadline.Token);
            Assert.IsFalse(File.Exists(executable));
            Assert.IsFalse(Directory.Exists(root));
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }
}
