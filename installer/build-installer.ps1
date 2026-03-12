param(
    [Parameter(Mandatory = $false)]
    [string]$AppVersion = "0.1.0",

    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$specPath = Join-Path $repoRoot "subvela.spec"
$distDir = Join-Path $repoRoot "dist\SubVela"
$issPath = Join-Path $PSScriptRoot "subvela.iss"

$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

$isccPath = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $isccPath) {
    throw "Inno Setup 6 was not found. Install it and rerun this script."
}

if (-not (Test-Path $pythonExe)) {
    throw "Project virtual environment not found at $pythonExe"
}

if (-not $SkipPyInstaller) {
    Remove-Item -LiteralPath (Join-Path $repoRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $repoRoot "dist") -Recurse -Force -ErrorAction SilentlyContinue
    & $pythonExe -m PyInstaller --clean -y $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }
}

if (-not (Test-Path $distDir)) {
    throw "Expected PyInstaller output folder not found: $distDir"
}

& $isccPath "/DAppVersion=$AppVersion" $issPath
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed."
}

Write-Host "Installer created in dist\installer" -ForegroundColor Green