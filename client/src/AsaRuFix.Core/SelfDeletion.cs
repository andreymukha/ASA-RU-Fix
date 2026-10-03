using System.Diagnostics;
using System.Runtime.Versioning;

namespace AsaRuFix.Core;

public static class SelfDeletion
{
    [SupportedOSPlatform("windows")]
    public static Process Start(string helper)
    {
        helper = Path.GetFullPath(helper);
        if (Path.GetFileName(helper) != "ASA-RU-Fix.exe") throw new ArgumentException("Неверное имя helper.");
        // timeout.exe fails without a console. Retry DEL after a loopback wait until the helper exits.
        // Paths are environment values, not shell source; CMD does not recursively expand their percent signs.
        var command = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe"))
        {
            Arguments = "/d /q /c \"for /l %i in (1,1,10) do (if exist \"%ASA_RU_FIX_DELETE_HELPER%\" (ping -n 2 127.0.0.1 >nul & del /q \"%ASA_RU_FIX_DELETE_HELPER%\" >nul 2>&1)) & rd \"%ASA_RU_FIX_HELPER_DIR%\"\"",
            UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden
        };
        command.Environment["ASA_RU_FIX_DELETE_HELPER"] = helper;
        command.Environment["ASA_RU_FIX_HELPER_DIR"] = Path.GetDirectoryName(helper)!;
        return Process.Start(command) ?? throw new IOException("Не удалось удалить временный helper.");
    }
}
