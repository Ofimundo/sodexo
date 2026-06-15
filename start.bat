@echo off
echo Iniciando Sistema OCR - Web Dashboard...

:: Start Flask Backend (que también sirve el frontend)
echo Iniciando servidor web (Flask)...
start "Servidor Web OCR" cmd /c ".\backend\.venv\Scripts\python.exe backend\server.py"

echo Esperando a que el servidor se inicialice...
timeout /t 3 /nobreak >nul

echo Abriendo Dashboard en el navegador...
start http://localhost:5000

echo.
echo El sistema se esta ejecutando.
echo Puedes acceder en: http://localhost:5000
echo Para detener los servicios, ejecuta: detener_servicios.bat
echo.
pause
