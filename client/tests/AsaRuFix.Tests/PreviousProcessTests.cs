using System.Diagnostics;
using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public class PreviousProcessTests
{
    [TestMethod]
    public async Task ExitedProcessIsAcceptedButCurrentPidIsRejected()
    {
        await PreviousProcess.WaitAsync(int.MaxValue, "unused.exe", TimeSpan.FromSeconds(1));
        await Assert.ThrowsAsync<InvalidDataException>(() => PreviousProcess.WaitAsync(Environment.ProcessId, "unused.exe", TimeSpan.FromSeconds(1)));
    }
    [TestMethod]
    public async Task FixtureHelperWaitsForVerifiedChildAndHandlesAlreadyExitedChild()
    {
        var child = Environment.GetEnvironmentVariable("ASA_RU_FIX_CHILD_PROBE")!;
        var output = Path.Combine(Path.GetTempPath(), Guid.NewGuid() + ".json");
        try
        {
            var start = new ProcessStartInfo(child) { UseShellExecute = false };
            start.ArgumentList.Add(output); start.ArgumentList.Add("0");
            start.Environment["ASA_RU_FIX_FIXTURE_DELAY_MS"] = "300";
            using var process = Process.Start(start)!;
            await PreviousProcess.WaitAsync(process.Id, child, TimeSpan.FromSeconds(5));
            Assert.IsTrue(process.HasExited);
            await PreviousProcess.WaitAsync(process.Id, child, TimeSpan.FromSeconds(1));
        }
        finally { File.Delete(output); }
    }
}
