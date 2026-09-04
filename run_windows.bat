@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py bootstrap_dependencies.py
) else (
    python bootstrap_dependencies.py
)
if errorlevel 1 goto :error

".venv\Scripts\python.exe" main.py
exit /b %errorlevel%

:error
echo.
echo No fue posible iniciar CodeCafe Atlas.
pause
exit /b 1
