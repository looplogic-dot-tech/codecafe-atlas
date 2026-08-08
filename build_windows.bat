@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -m venv .venv
if errorlevel 1 goto :error
".venv\Scripts\python.exe" validate_before_build.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" validate_public_identity.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :error
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name "CodeCafe-Atlas" --add-data "modules;modules" --add-data "assets;assets" --icon "assets\codecafe_atlas_icon.ico" main.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onefile --name "CodeCafe-Atlas-Updater" --add-data "assets;assets" --icon "assets\codecafe_atlas_icon.ico" codecafe_atlas_updater.py
if errorlevel 1 goto :error
copy /y "dist\CodeCafe-Atlas-Updater.exe" "dist\CodeCafe-Atlas\CodeCafe-Atlas-Updater.exe" >nul
if errorlevel 1 goto :error
if not exist "dist\CodeCafe-Atlas\data" mkdir "dist\CodeCafe-Atlas\data"
if not exist "dist\CodeCafe-Atlas\backups" mkdir "dist\CodeCafe-Atlas\backups"
copy /y "CODECAFE_ATLAS_IDENTITY.json" "dist\CodeCafe-Atlas\CODECAFE_ATLAS_IDENTITY.json" >nul
if errorlevel 1 goto :error
del /q "dist\CodeCafe-Atlas-Updater.exe" 2>nul
if not exist "dist\CodeCafe-Atlas\CodeCafe-Atlas.exe" goto :error
if not exist "dist\CodeCafe-Atlas\CodeCafe-Atlas-Updater.exe" goto :error
echo Compilacion v1.0.24.15 terminada y validada.
echo .venv\Scripts\python.exe make_update_package.py --dist dist\CodeCafe-Atlas --version 1.0.24.15 --platform windows --architecture x86_64
pause
exit /b 0
:error
echo La compilacion fallo o la estructura final es incorrecta.
pause
exit /b 1
