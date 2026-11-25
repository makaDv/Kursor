# Builds dist\PadLink\PadLink.exe and (if Inno Setup is installed) dist\PadLink-Setup-<ver>.exe
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1 [-Msix] [-TestSign] [-Release]
#     -Msix      also build dist\PadLink-<ver>.msix for the Microsoft Store (needs the Windows SDK)
#     -TestSign  sign the .msix with a local self-signed certificate, to install it on this PC
#     -Release   stop unless scripts\release_check.py passes (placeholders, versions, audits)
# Authenticode signing of the website installer: set PADLINK_SIGN_PFX and PADLINK_SIGN_PASSWORD.
param([switch]$Msix, [switch]$TestSign, [switch]$Release)
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
# Release builds use exact, tested versions (server\requirements.lock, refresh with pip freeze).
# zeroconf without compiled extensions: unsigned .pyd files are blocked by Smart App Control.
$env:SKIP_CYTHON = '1'
if (Test-Path server\requirements.lock) { & $py -m pip install --no-binary zeroconf -r server\requirements.lock }
else { & $py -m pip install --no-binary zeroconf -r server\requirements.txt -r server\requirements-desktop.txt }

if ($Release) {
    Write-Host '== release check'
    & $py scripts\release_check.py
    if ($LASTEXITCODE -ne 0) { throw 'release_check failed: fix the items above' }
}

Write-Host '== licenses'
& $py scripts\collect_licenses.py

Write-Host '== icons'
& $py scripts\make_icons.py

Write-Host '== PyInstaller'
& $py -m PyInstaller packaging\windows\padlink.spec --noconfirm --clean --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    Write-Host '== installer'
    & $iscc packaging\windows\padlink.iss
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
} else {
    Write-Warning 'Inno Setup 6 not found: only dist\PadLink\ was produced (winget install JRSoftware.InnoSetup)'
}

$version = (Get-Content client\package.json -Raw | ConvertFrom-Json).version
$sdk = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64" -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName 'makeappx.exe') } | Sort-Object Name -Descending | Select-Object -First 1
$signtool = if ($sdk) { Join-Path $sdk.FullName 'signtool.exe' } else { $null }

# Authenticode for the website installer (Microsoft Store packages are signed by the Store).
if ($env:PADLINK_SIGN_PFX -and $signtool) {
    Write-Host '== code signing'
    $targets = @('dist\PadLink\PadLink.exe') + (Get-ChildItem "dist\PadLink-Setup-$version.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName)
    & $signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /f $env:PADLINK_SIGN_PFX /p $env:PADLINK_SIGN_PASSWORD @targets
    if ($LASTEXITCODE -ne 0) { throw 'signtool failed' }
} elseif (-not $Msix) {
    Write-Warning 'Installer NOT signed: Smart App Control / SmartScreen will block or warn (set PADLINK_SIGN_PFX).'
}

if ($Msix) {
    if (-not $sdk) { throw 'Windows SDK not found (makeappx.exe): winget install Microsoft.WindowsSDK.10.0.26100' }
    Write-Host '== MSIX'
    $rel = Get-Content release.json -Raw | ConvertFrom-Json
    $identity = $rel.ms_store_identity_name; $publisher = $rel.ms_store_publisher; $pubName = $rel.ms_store_publisher_display_name
    if ($TestSign -or "$identity".StartsWith('[')) {
        # Local test values: the Store upload needs the real ones from Partner Center (release.json).
        $identity = 'PadLink.Test'; $publisher = 'CN=PadLink Test'; $pubName = 'PadLink (test)'
        if (-not $TestSign) { Write-Warning 'release.json has no Partner Center identity: built with TEST identity (not uploadable).' }
    }
    $stage = 'build\msix'
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    New-Item -ItemType Directory $stage | Out-Null
    Copy-Item dist\PadLink -Destination (Join-Path $stage 'PadLink') -Recurse
    Copy-Item packaging\windows\msix\Assets -Destination (Join-Path $stage 'Assets') -Recurse
    (Get-Content packaging\windows\msix\AppxManifest.xml -Raw).
        Replace('{{IDENTITY_NAME}}', $identity).Replace('{{PUBLISHER}}', $publisher).
        Replace('{{PUBLISHER_DISPLAY_NAME}}', $pubName).Replace('{{VERSION}}', $version) |
        Set-Content (Join-Path $stage 'AppxManifest.xml') -Encoding UTF8
    $out = "dist\PadLink-$version.msix"
    & (Join-Path $sdk.FullName 'makeappx.exe') pack /o /d $stage /p $out
    if ($LASTEXITCODE -ne 0) { throw 'makeappx failed' }
    if ($TestSign) {
        $cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object Subject -eq $publisher | Select-Object -First 1
        if (-not $cert) {
            $cert = New-SelfSignedCertificate -Type Custom -Subject $publisher -KeyUsage DigitalSignature `
                -CertStoreLocation Cert:\CurrentUser\My -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3', '2.5.29.19={text}')
        }
        & $signtool sign /fd sha256 /sha1 $cert.Thumbprint $out
        if ($LASTEXITCODE -ne 0) { throw 'signtool (test) failed' }
        Write-Host "Test-signed. To install: trust the certificate '$publisher' (Trusted People, admin) then Add-AppxPackage $out"
    }
    Write-Host "MSIX: $out"
}
Write-Host 'Done.'
