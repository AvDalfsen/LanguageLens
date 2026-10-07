param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot), [int]$StartupTimeoutSeconds = 30)
$ErrorActionPreference = "Stop"
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "The local environment is missing. Run 'Start Language Lens.bat' to recover it."
}

$StartupRoot = Join-Path $env:LOCALAPPDATA "LanguageLens"
New-Item -ItemType Directory -Path $StartupRoot -Force | Out-Null
$StartupFile = Join-Path $StartupRoot ("startup-" + [Guid]::NewGuid().ToString("N") + ".json")
$PreviousStartupFile = $env:LANGUAGE_LENS_STARTUP_FILE
$Process = $null
try {
    $env:LANGUAGE_LENS_STARTUP_FILE = $StartupFile
    $Process = Start-Process -FilePath $PythonPath -ArgumentList "-m", "language_lens" -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    $Deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        if (Test-Path -LiteralPath $StartupFile) {
            $Status = Get-Content -LiteralPath $StartupFile -Raw | ConvertFrom-Json
            if ($Status.status -eq "ready") { return }
            if (-not $Process.HasExited) { $Process.Kill() }
            throw $Status.message
        }
        if ($Process.HasExited) { throw "Language Lens exited before opening (code $($Process.ExitCode)). Check '$StartupRoot\logs', then run 'Start Language Lens.bat' again." }
        Start-Sleep -Milliseconds 100
    }
    if (-not $Process.HasExited) { $Process.Kill() }
    throw "Language Lens did not finish starting within $StartupTimeoutSeconds seconds. Check '$StartupRoot\logs' and retry."
} finally {
    $env:LANGUAGE_LENS_STARTUP_FILE = $PreviousStartupFile
    if (Test-Path -LiteralPath $StartupFile) { Remove-Item -LiteralPath $StartupFile }
    if ($Process) { $Process.Dispose() }
}

