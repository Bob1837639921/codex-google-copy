Set WshShell = CreateObject("WScript.Shell")
pyExe = Chr(34) & "C:\Users\86159\AppData\Local\Programs\Python\Python311\pythonw.exe" & Chr(34)
scriptPath = "F:\codex-google-copy\server_live.py"
WshShell.Run pyExe & " " & scriptPath, 0, False
