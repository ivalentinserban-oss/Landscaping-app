$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $Root "landscaping_app"

if (-not (Test-Path $AppDir)) {
    Write-Error "Could not find app directory: $AppDir"
    exit 1
}

Set-Location $AppDir
& ".\run.ps1"
