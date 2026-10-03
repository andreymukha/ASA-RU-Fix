using System.Text.Json;
using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public class LaunchTests
{
    [TestMethod]
    public async Task TranslationFailureStillStartsChildAndReturnsItsExitCode()
    {
        var helper = Environment.GetEnvironmentVariable("ASA_RU_FIX_CHILD_PROBE")
            ?? Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../../client/tests/ChildProbe/bin/Release/net10.0/ChildProbe.exe"));
        Assert.IsTrue(File.Exists(helper), "Build ChildProbe and set ASA_RU_FIX_CHILD_PROBE");
        var output = Path.Combine(Path.GetTempPath(), Guid.NewGuid() + ".json");
        try
        {
            var coordinator = new LaunchCoordinator();
            var result = await coordinator.RunAsync([helper, output, "37", "с пробелом", "", "a\"b", "--flag"], "-high",
                ct => throw new HttpRequestException("offline"), CancellationToken.None);
            Assert.AreEqual(37, result);
            CollectionAssert.AreEqual(new[] { "с пробелом", "", "a\"b", "--flag", "-high" }, JsonSerializer.Deserialize<string[]>(File.ReadAllText(output))!);
        }
        finally { File.Delete(output); }
    }

    [TestMethod]
    public void NamedMutexBoundsWaitingAndReleasesForNextOperation()
    {
        var name = "Local\\ASA-RU-Fix-fixture-" + Guid.NewGuid();
        using (var first = UserMutex.TryAcquire(name, TimeSpan.FromSeconds(1)))
        {
            Assert.IsNotNull(first);
            using var second = UserMutex.TryAcquire(name, TimeSpan.FromMilliseconds(50));
            Assert.IsNull(second);
        }
        using var next = UserMutex.TryAcquire(name, TimeSpan.FromSeconds(1));
        Assert.IsNotNull(next);
    }

    [TestMethod]
    public async Task SelfUpdateStageFailureDoesNotChangeChildExit()
    {
        var helper = Environment.GetEnvironmentVariable("ASA_RU_FIX_CHILD_PROBE")!;
        Assert.IsTrue(File.Exists(helper));
        var output = Path.Combine(Path.GetTempPath(), Guid.NewGuid() + ".json");
        try
        {
            var result = await new LaunchCoordinator().RunAsync([helper, output, "7"], "",
                ct => Task.CompletedTask, CancellationToken.None, background: () => throw new IOException("self update failed"));
            Assert.AreEqual(7, result);
        }
        finally { File.Delete(output); }
    }
}
