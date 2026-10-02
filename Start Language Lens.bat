@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Language Lens Launcher

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
set "VENV_PYTHONW=%CD%\.venv\Scripts\pythonw.exe"
set "SETUP_SCRIPT=%CD%\scripts\setup.ps1"
set "RUN_SCRIPT=%CD%\scripts\run.ps1"
set "NEEDS_SETUP=0"

if not exist "%SETUP_SCRIPT%" goto :missing_files
if not exist "%RUN_SCRIPT%" goto :missing_files

if not exist "%VENV_PYTHON%" set "NEEDS_SETUP=1"
if not exist "%VENV_PYTHONW%" set "NEEDS_SETUP=1"

if "%NEEDS_SETUP%"=="0" (
    "%VENV_PYTHON%" -c "import language_lens, PySide6, rapidocr, onnxruntime, argostranslate, ctranslate2" >nul 2>&1
    if errorlevel 1 set "NEEDS_SETUP=1"
)

if "%NEEDS_SETUP%"=="1" (
    echo Language Lens needs first-time setup or repair.
    echo This may take several minutes and needs an internet connection.
    echo.

    where python >nul 2>&1
    if errorlevel 1 goto :missing_python

    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SETUP_SCRIPT%"
    if errorlevel 1 goto :setup_failed

    if not exist "%VENV_PYTHON%" goto :setup_failed
    "%VENV_PYTHON%" -c "import language_lens, PySide6, rapidocr, onnxruntime, argostranslate, ctranslate2" >nul 2>&1
    if errorlevel 1 goto :setup_failed
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%RUN_SCRIPT%"
if errorlevel 1 goto :launch_failed
exit /b 0

:missing_files
echo ERROR: Launcher files are missing from:
echo %CD%
echo.
echo Keep this batch file in the LanguageLens project folder.
goto :failure

:missing_python
echo ERROR: Python was not found.
echo Install Python 3.10, 3.11, or 3.12 and try again.
goto :failure

:setup_failed
echo.
echo ERROR: Language Lens setup did not complete successfully.
goto :failure

:launch_failed
echo.
echo ERROR: Language Lens could not be launched.
goto :failure

:failure
echo.
pause
exit /b 1
