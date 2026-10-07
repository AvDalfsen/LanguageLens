@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Language Lens Launcher

if not exist "%~dp0scripts\launcher.ps1" (
    echo ERROR: Launcher files are missing. Keep this batch file in the LanguageLens project folder.
    pause
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher.ps1"
if errorlevel 1 (
    echo.
    echo Language Lens did not start. See the explanation above.
    pause
    exit /b 1
)
exit /b 0
