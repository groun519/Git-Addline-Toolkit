Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
curDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = curDir & "\run_line_tracker.bat"

If Not fso.FileExists(launcher) Then
    MsgBox "Line Tracker launcher not found:" & vbCrLf & launcher, 16, "Line Tracker"
    WScript.Quit 1
End If

shell.Run """" & launcher & """", 0, False
