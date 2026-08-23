@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo CodeCafe Atlas v1.0.24.25 - reproducible Windows build
echo ============================================================

rem Bootstrap first. This creates/reuses .venv and installs from packages\ cache.
rem Internet is used only if the persistent local cache is incomplete.
where py >nul 2>nul
if not errorlevel 1 (
    py bootstrap_dependencies.py
) else (
    python bootstrap_dependencies.py
)
if errorlevel 1 goto :error

rem All regression/identity gates run inside the controlled environment.
".venv\Scripts\python.exe" validate_public_identity.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" validate_full_functionality.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" validate_before_build.py
if errorlevel 1 goto :error

rem Build in LOCALAPPDATA, not directly inside OneDrive/synchronized source paths.
rem build_windows_release.py performs a real local-path startup smoke test,
rem then copies dist back and creates release\CodeCafe_Atlas_v1.0.24.25_Windows_x64.zip.
".venv\Scripts\python.exe" build_windows_release.py
if errorlevel 1 goto :error

echo.
echo Compilacion v1.0.24.25 terminada y validada.
echo Distro: dist\CodeCafe-Atlas
echo ZIP portable: release\CodeCafe_Atlas_v1.0.24.25_Windows_x64.zip
echo Paquete de actualizacion opcional:
echo .venv\Scripts\python.exe make_update_package.py --dist dist\CodeCafe-Atlas --version 1.0.24.25 --platform windows --architecture x86_64
pause
exit /b 0

:error
echo.
echo La compilacion fallo o una validacion no fue superada.
echo No se acepta esta compilacion como release.
pause
exit /b 1
