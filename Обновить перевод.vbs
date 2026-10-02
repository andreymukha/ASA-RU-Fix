Option Explicit

Dim shell, fileSystem, projectRoot, powershellPath, scriptPath, command, noMessageBox, exitCode
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

projectRoot = fileSystem.GetParentFolderName(WScript.ScriptFullName)
scriptPath = fileSystem.BuildPath(projectRoot, "update.ps1")
powershellPath = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"

noMessageBox = ""
If WScript.Arguments.Named.Exists("NoMessageBox") Then noMessageBox = " -NoMessageBox"

command = Chr(34) & powershellPath & Chr(34) & _
    " -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File " & _
    Chr(34) & scriptPath & Chr(34) & noMessageBox

On Error Resume Next
exitCode = shell.Run(command, 0, True)
If Err.Number <> 0 Then
    MsgBox "Не удалось пересобрать или установить перевод." & vbCrLf & vbCrLf & _
        "Подробности:" & vbCrLf & fileSystem.BuildPath(projectRoot, "work\update.log"), _
        vbCritical, "ASA-RU-Fix — ошибка"
    WScript.Quit 1
End If
On Error GoTo 0

WScript.Quit exitCode
