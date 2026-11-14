using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

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
            try { executable = GetExecutablePath(process); }
            catch (Exception error) when ((error is InvalidOperationException or Win32Exception) && process.HasExited) { return; }
            if (executable is null || !string.Equals(Path.GetFullPath(executable), Path.GetFullPath(expectedExe), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("PID не принадлежит установленному updater.");
            using var deadline = new CancellationTokenSource(timeout);
            try { await process.WaitForExitAsync(deadline.Token).ConfigureAwait(false); }
            catch (OperationCanceledException) { throw new TimeoutException("Предыдущий updater не завершился вовремя."); }
        }
    }

    private static string? GetExecutablePath(Process process)
    {
        if (!OperatingSystem.IsWindows()) return process.MainModule?.FileName;

        // MainModule can be null while a just-started process is still loading modules.
        var path = new StringBuilder(32768);
        int size = path.Capacity;
        if (!QueryFullProcessImageNameW(process.SafeHandle, 0, path, ref size))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        return path.ToString();
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryFullProcessImageNameW(SafeProcessHandle process, int flags, StringBuilder path, ref int size);
}
