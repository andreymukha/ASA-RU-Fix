using System.Diagnostics;

namespace AsaRuFix.Core;

public static class PreviousProcess
{
    public static async Task WaitAsync(int pid, string expectedExe, TimeSpan timeout)
    {
        if (pid <= 0 || pid == Environment.ProcessId) throw new InvalidDataException("Неверный PID предыдущего updater.");
        Process process;
        try { process = Process.GetProcessById(pid); }
        catch (ArgumentException) { return; }
        using (process)
        {
            if (process.HasExited) return;
            string? executable;
            try { executable = process.MainModule?.FileName; }
            catch (InvalidOperationException) when (process.HasExited) { return; }
            if (executable is null || !string.Equals(Path.GetFullPath(executable), Path.GetFullPath(expectedExe), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("PID не принадлежит установленному updater.");
            using var deadline = new CancellationTokenSource(timeout);
            try { await process.WaitForExitAsync(deadline.Token).ConfigureAwait(false); }
            catch (OperationCanceledException) { throw new TimeoutException("Предыдущий updater не завершился вовремя."); }
        }
    }
}
