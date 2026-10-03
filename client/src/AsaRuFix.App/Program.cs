using System.Diagnostics;
using AsaRuFix.Core;

namespace AsaRuFix.App;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        try
        {
            if (args.Length == 2 && args[0] == "--diagnose-json")
            { AppRuntime.DiagnoseAsync(args[1]).GetAwaiter().GetResult(); return 0; }
            if (args.Length >= 3 && args[0] == "--steam-launch" && args[1] == "--")
                return AppRuntime.SteamLaunchAsync(args[2..]).GetAwaiter().GetResult();
            if (args.Length >= 2 && args[0] == "--complete-self-update")
            { SelfUpdateHelper.CompleteAsync(int.Parse(args[1]), args.Contains("--restart")).GetAwaiter().GetResult(); return 0; }
            if (args.Length == 2 && args[0] == "--complete-uninstall")
            { UninstallHelper.CompleteAsync(int.Parse(args[1])).GetAwaiter().GetResult(); return 0; }
            if (args.Length > 0 && args[0] is not "--gui" and not "--uninstall") throw new ArgumentException("Неизвестные параметры запуска.");

            var installed = AppRuntime.Paths.Executable;
            var current = Environment.ProcessPath!;
            if (!string.Equals(current, installed, StringComparison.OrdinalIgnoreCase) && File.Exists(installed))
            {
                var existingVersion = FileVersionInfo.GetVersionInfo(installed).FileVersion;
                if (args.Contains("--uninstall") || existingVersion is not null && System.Version.Parse(existingVersion) >= System.Version.Parse(AppRuntime.Version))
                {
                    Process.Start(new ProcessStartInfo(installed, args.Contains("--uninstall") ? "--uninstall" : "--gui") { UseShellExecute = false });
                    return 0;
                }
            }
            try { SelfUpdateHelper.CleanupCompleted(); }
            catch (Exception error) { new LocalLogger(AppRuntime.Paths).Write("pending-cleanup-failed", error.GetType().Name); }
            Application.Run(new MainForm(args.Contains("--uninstall")));
            return 0;
        }
        catch (Exception error)
        {
            // Headless Steam mode must not leave a modal dialog in front of the game.
            if (!args.Contains("--steam-launch")) MessageBox.Show(error.Message, "ASA-RU-Fix — ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
