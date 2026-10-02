$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "The local environment is missing. Run scripts\setup.ps1 first."
}

Start-Process -FilePath $PythonPath -ArgumentList "-m", "language_lens" `
    -WorkingDirectory $ProjectRoot -WindowStyle Hidden

