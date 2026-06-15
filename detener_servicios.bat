@echo off
echo Deteniendo servidores de OCR ...

:: Detener Servidor Web en el puerto 5000 (Python Flask)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5000" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a
)

echo Servidores detenidos correctamente.
pause
