Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
scriptPath = Replace(WScript.ScriptFullName, WScript.ScriptName, "")
pythonw = scriptPath & "venv\Scripts\pythonw.exe"
appPy = scriptPath & "debt_manager.pyw"
If FSO.FileExists(pythonw) Then
    WshShell.Run chr(34) & pythonw & chr(34) & " " & chr(34) & appPy & chr(34), 0, False
Else
    exePath = scriptPath & "dist\DebtManager\DebtManager.exe"
    If FSO.FileExists(exePath) Then
        WshShell.Run chr(34) & exePath & chr(34), 0, False
    Else
        MsgBox "لم يتم العثور على DebtManager.exe أو pythonw.exe", 16, "خطأ"
    End If
End If
