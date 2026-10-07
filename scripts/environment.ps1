$ErrorActionPreference = "Stop"

function Test-LensPython([string]$Executable, [switch]$RequirePip) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    $Check = "import sys, struct, platform; assert sys.version_info.major == 3 and 10 <= sys.version_info.minor <= 12; assert struct.calcsize('P') == 8 and platform.machine().lower() in ('amd64', 'x86_64')"
    if ($RequirePip) { $Check += "; import pip" }
    try {
        & $Executable -I -c $Check 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-LensPython([string]$ProjectRoot) {
    $Existing = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-LensPython $Existing) { return $Existing }
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($Launcher) {
        foreach ($Version in @("-3.12", "-3.11", "-3.10")) {
            try {
                $Candidate = & $Launcher.Source $Version -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $Candidate -and (Test-LensPython ([string]$Candidate))) { return [string]$Candidate }
            } catch { }
        }
    }
    foreach ($Name in @("python.exe", "python3.exe")) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Command -and $Command.Source -notlike "*\Microsoft\WindowsApps\*" -and (Test-LensPython $Command.Source)) {
            return $Command.Source
        }
    }
    throw "Install Python 3.10, 3.11, or 3.12 for Windows x64, then run 'Start Language Lens.bat' again. No compatible interpreter was found."
}

function Test-LensEnvironment([string]$ProjectRoot) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"))) { return $false }
    if (-not (Test-LensPython $Python -RequirePip)) { return $false }
    $Health = "import ctypes; ctypes.windll.kernel32.SetErrorMode(3); import language_lens, PySide6, rapidocr, onnxruntime, argostranslate, ctranslate2, regex, janome, jieba, filelock; from language_lens.services.voices import VOICES, voice_runtime_ready; assert all(voice_runtime_ready(v) for v in VOICES)"
    try {
        & $Python -I -c $Health 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Backup-LensEnvironment([string]$ProjectRoot) {
    $Root = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $Target = [IO.Path]::GetFullPath((Join-Path $Root ".venv"))
    if ([IO.Path]::GetDirectoryName($Target) -ne $Root -or [IO.Path]::GetFileName($Target) -ne ".venv") {
        throw "The environment path is outside the project; recovery was cancelled."
    }
    if (Test-Path -LiteralPath $Target) {
        $Item = Get-Item -LiteralPath $Target
        if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "The environment is a linked directory. Restore it manually before running setup." }
        $Backup = Join-Path $Root (".venv.backup-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [Guid]::NewGuid().ToString("N"))
        if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Backup)) -ne $Root) { throw "Invalid environment backup path." }
        Move-Item -LiteralPath $Target -Destination $Backup
        Write-Host "Previous environment preserved at: $Backup"
        return $Backup
    }
}
