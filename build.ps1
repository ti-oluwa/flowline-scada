param(
    [string]$Name  = 'FlowlineSCADA.exe',
    [string]$Entry = 'main.py'
)

$ErrorActionPreference = 'Stop'

function Write-Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Write-Warn($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }

Write-Info "Starting build helper for FlowlineSCADA"

# Move to repo root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Info "Using entry point: $Entry"

# Locate nicegui-pack
try {
    $ngPack = Get-Command nicegui-pack
} catch {
    Write-Err "'nicegui-pack' not found in PATH. Activate the correct virtualenv."
    exit 1
}

if (Test-Path $Name) {
    Write-Warn "Removing existing artifact: $Name"
    Remove-Item -Force $Name
}

$iconPath = Join-Path $scriptDir 'assets\pipeline.ico'

$argString = @(
    '--onefile'
    '--windowed'
    '--icon "' + $iconPath + '"'
    '--name "' + $Name + '"'
    $Entry
) -join ' '

Write-Info "Running nicegui-pack..."
Write-Info "$($ngPack.Path) $argString"

$p = Start-Process `
    -FilePath $ngPack.Path `
    -ArgumentList $argString `
    -Wait `
    -PassThru `
    -NoNewWindow:$false

if ($p.ExitCode -eq 0) {
    Write-Info "Build completed successfully"
    exit 0
} else {
    Write-Err "Build failed with exit code $($p.ExitCode)"
    exit $p.ExitCode
}
