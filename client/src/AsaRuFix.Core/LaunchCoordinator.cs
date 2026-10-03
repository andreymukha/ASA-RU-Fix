using System.Diagnostics;

namespace AsaRuFix.Core;

public sealed class LaunchCoordinator
{
    public async Task<int> RunAsync(string[] gameArgs, string original, Func<CancellationToken, Task> update,
        CancellationToken cancellationToken, Func<Task>? background = null)
    {
        var command = GameCommandBuilder.Build(gameArgs, original);
        try { await update(cancellationToken).ConfigureAwait(false); }
        catch (Exception) { /* Translation failures must never prevent the original game command. */ }
        using var process = Process.Start(new ProcessStartInfo(command.FileName, command.Arguments) { UseShellExecute = false })
            ?? throw new IOException("Не удалось запустить исходную команду игры.");
        var backgroundTask = RunBackground();
        await process.WaitForExitAsync().ConfigureAwait(false);
        await backgroundTask.ConfigureAwait(false);
        return process.ExitCode;

        async Task RunBackground()
        {
            try { if (background is not null) await background().ConfigureAwait(false); }
            catch (Exception) { /* Self-update is independent of the game process exit status. */ }
        }
    }
}
