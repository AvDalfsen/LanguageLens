param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "environment.ps1")
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$EnvironmentPath = Join-Path $ProjectRoot ".venv"
$PythonPath = Join-Path $EnvironmentPath "Scripts\python.exe"
if (-not (Test-LensEnvironment $ProjectRoot)) {
    $BootstrapPython = Find-LensPython $ProjectRoot
    if ($BootstrapPython -eq $PythonPath) {
        $BaseExecutable = & $BootstrapPython -I -c "import sys; print(sys._base_executable)"
        if (-not (Test-LensPython ([string]$BaseExecutable))) { throw "The base Python installation is unavailable. Reinstall a supported Python first." }
        $BootstrapPython = [string]$BaseExecutable
    }
    Backup-LensEnvironment $ProjectRoot | Out-Null
    & $BootstrapPython -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment. The previous environment remains in its backup folder." }
}
& $PythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip. Check the internet connection and available disk space." }
& $PythonPath -m pip install -e "$ProjectRoot[dev]"
if ($LASTEXITCODE -ne 0) { throw "Could not install Language Lens dependencies. Existing environment backups were retained." }
if (-not (Test-LensEnvironment $ProjectRoot)) { throw "Installed components did not pass the local checks. Close Lens if it is running, then retry setup." }

Write-Host "Setup complete."

