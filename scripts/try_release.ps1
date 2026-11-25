<#
.SYNOPSIS
  Prova PadLink come un utente nuovo, senza toccare la tua installazione vera.

.DESCRIPTION
  Avvia il programma PC (dai sorgenti, quindi non bloccato da Smart App Control) con
  una cartella dati separata: %LOCALAPPDATA%\PadLink-trial. Vedrai il primo avvio
  completo: consenso, password obbligatoria, QR, sezione "Accesso fuori casa".
  I tuoi dati veri in %USERPROFILE%\.padlink restano intatti.

      powershell -ExecutionPolicy Bypass -File scripts\try_release.ps1          # avvia la prova
      powershell -ExecutionPolicy Bypass -File scripts\try_release.ps1 -Reset   # ricomincia da zero
      powershell -ExecutionPolicy Bypass -File scripts\try_release.ps1 -Remove  # cancella la prova

  Sul telefono: Altro (o il nome del PC in alto) > "Associa un altro PC" e inquadra il
  nuovo QR. Il PC di prova ha un certificato diverso, quindi l'app lo tratta come un PC nuovo.
  Chiudi PadLink vero prima della prova: usano la stessa porta (8443).
#>
param([switch]$Reset, [switch]$Remove)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$data = Join-Path $env:LOCALAPPDATA 'PadLink-trial'

if ($Remove -or $Reset) {
    if (Test-Path $data) { Remove-Item $data -Recurse -Force }
    Write-Host "Prova cancellata: $data"
    if ($Remove) { return }
}

$busy = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Error 'La porta 8443 è già in uso: chiudi PadLink (icona vicino all orologio > Esci) e riprova.'
}

$py = Join-Path $root 'server\.venv\Scripts\pythonw.exe'
if (-not (Test-Path $py)) { $py = Join-Path $root 'server\.venv\Scripts\python.exe' }
if (-not (Test-Path (Join-Path $root 'client\dist\index.html'))) {
    Push-Location (Join-Path $root 'client'); npm run build; Pop-Location
}
Start-Process -FilePath $py -ArgumentList @('-m', 'padlink', '--data-dir', $data, 'desktop') `
    -WorkingDirectory (Join-Path $root 'server')
Write-Host "PadLink di prova avviato (dati in $data)."
