# Builds dist\Kursor\Kursor.exe and (if Inno Setup is installed) dist\Kursor-Setup-<ver>.exe
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $root

Write-Host '== web client'
Push-Location client
npm ci
npm run build
Pop-Location

Write-Host '== python deps'
$py = Join-Path $root 'server\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { python -m venv server\.venv }
& $py -m pip install --upgrade pip
& $py -m pip install -r server\requirements.txt -r server\requirements-desktop.txt

Write-Host '== icons'
& $py scripts\make_icons.py

Write-Host '== PyInstaller'
& $py -m PyInstaller packaging\windows\kursor.spec --noconfirm --clean --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    Write-Host '== installer'
    & $iscc packaging\windows\kursor.iss
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
} else {
    Write-Warning 'Inno Setup 6 not found: only dist\Kursor\ was produced (winget install JRSoftware.InnoSetup)'
}

# Code signing (strongly recommended, avoids SmartScreen warnings):
#   signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /a dist\Kursor\Kursor.exe dist\Kursor-Setup-*.exe
Write-Host 'Done.'
