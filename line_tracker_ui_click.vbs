Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
curDir = fso.GetParentFolderName(WScript.ScriptFullName)

py = "pythonw"
rc = shell.Run("cmd /c where pythonw >nul 2>nul", 0, True)
If rc <> 0 Then
    py = "python"
End If

cmd = """" & py & """ """ & curDir & "\app\line_tracker_ui.pyw"""
shell.Run cmd, 0, False
