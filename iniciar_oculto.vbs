Set WshShell = CreateObject("WScript.Shell")
' Obtener el directorio donde está el .vbs para construir rutas absolutas
Dim scriptDir
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Ejecutar el servidor Flask (que también sirve el frontend compilado) sin mostrar ventana
WshShell.Run "cmd /c """ & scriptDir & "\backend\.venv\Scripts\python.exe"" """ & scriptDir & "\backend\server.py""", 0, False
