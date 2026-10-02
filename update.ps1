[CmdletBinding()]
param([switch]$NoMessageBox)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$WorkDirectory = Join-Path $ProjectRoot 'work'
$LogPath = Join-Path $WorkDirectory 'update.log'
$FailureExitCode = 1

function Show-UpdateMessage {
    param(
        [string]$Title,
        [string]$Message,
        [string]$Icon
    )

    if ($NoMessageBox) { return }
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show(
        $Message,
        $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Enum]::Parse([System.Windows.Forms.MessageBoxIcon], $Icon)
    )
}

function Add-ProcessOutputToLog {
    param(
        [string]$StreamName,
        [string]$Text
    )

    if ([string]::IsNullOrEmpty($Text)) { return }
    $content = "[$StreamName]`r`n$Text"
    if (-not $Text.EndsWith("`n")) { $content += "`r`n" }
    [System.IO.File]::AppendAllText($LogPath, $content, [System.Text.UTF8Encoding]::new($false))
}

try {
    New-Item -ItemType Directory -Path $WorkDirectory -Force | Out-Null
    [System.IO.File]::WriteAllText($LogPath, '', [System.Text.UTF8Encoding]::new($false))
}
catch {
    Show-UpdateMessage 'ASA-RU-Fix — ошибка' "Не удалось пересобрать или установить перевод.`r`n`r`nПодробности:`r`n$LogPath`r`n`r`nОшибка создания лога: $($_.Exception.Message)" 'Error'
    exit 1
}

try {
    Set-Location -LiteralPath $ProjectRoot
    Add-Content -LiteralPath $LogPath -Value "[$(Get-Date -Format o)] Запуск production build из $ProjectRoot" -Encoding UTF8

    $BuildExitCode = 1
    $PythonCommand = Get-Command -Name python -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $PythonStartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $PythonStartInfo.FileName = $PythonCommand.Source
    $PythonStartInfo.Arguments = 'build.py'
    $PythonStartInfo.WorkingDirectory = $ProjectRoot
    $PythonStartInfo.UseShellExecute = $false
    $PythonStartInfo.CreateNoWindow = $true
    $PythonStartInfo.RedirectStandardOutput = $true
    $PythonStartInfo.RedirectStandardError = $true
    $PythonStartInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $PythonStartInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $PythonStartInfo.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'

    $PythonProcess = New-Object System.Diagnostics.Process
    try {
        $PythonProcess.StartInfo = $PythonStartInfo
        [void]$PythonProcess.Start()
        $StdoutTask = $PythonProcess.StandardOutput.ReadToEndAsync()
        $StderrTask = $PythonProcess.StandardError.ReadToEndAsync()
        $PythonProcess.WaitForExit()
        $BuildExitCode = $PythonProcess.ExitCode
        Add-ProcessOutputToLog 'stdout' $StdoutTask.Result
        Add-ProcessOutputToLog 'stderr' $StderrTask.Result
    }
    finally {
        $PythonProcess.Dispose()
    }

    if ($BuildExitCode -ne 0) {
        $FailureExitCode = $BuildExitCode
        Add-Content -LiteralPath $LogPath -Value "[$(Get-Date -Format o)] Ошибка: python build.py завершился с кодом $BuildExitCode. install.ps1 не запускался." -Encoding UTF8
        throw "python build.py завершился с кодом $BuildExitCode."
    }

    Add-Content -LiteralPath $LogPath -Value "[$(Get-Date -Format o)] Сборка успешна; запуск install.ps1" -Encoding UTF8
    $LASTEXITCODE = 0
    & (Join-Path $ProjectRoot 'install.ps1') *>&1 | Out-File -LiteralPath $LogPath -Append -Encoding UTF8 -Width 4096
    $InstallExitCode = $LASTEXITCODE
    if ($InstallExitCode -ne 0) {
        $FailureExitCode = $InstallExitCode
        Add-Content -LiteralPath $LogPath -Value "[$(Get-Date -Format o)] Ошибка: install.ps1 завершился с кодом $InstallExitCode." -Encoding UTF8
        throw "install.ps1 завершился с кодом $InstallExitCode."
    }

    Add-Content -LiteralPath $LogPath -Value "[$(Get-Date -Format o)] Перевод успешно пересобран и установлен." -Encoding UTF8
    Show-UpdateMessage 'ASA-RU-Fix' "Перевод успешно пересобран и установлен.`r`n`r`nМожно запускать ARK." 'Information'
    exit 0
}
catch {
    $ErrorDetails = $_.Exception.Message
    try {
        Add-Content -LiteralPath $LogPath -Value "[$(Get-Date -Format o)] Ошибка: $ErrorDetails" -Encoding UTF8
    }
    catch { }

    Show-UpdateMessage 'ASA-RU-Fix — ошибка' "Не удалось пересобрать или установить перевод.`r`n`r`nПодробности:`r`n$LogPath" 'Error'
    exit $FailureExitCode
}
