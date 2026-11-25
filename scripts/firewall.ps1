<#
.SYNOPSIS
  Windows Firewall rules for PadLink: LAN (private networks) and Tailscale only.

.DESCRIPTION
  Run once from an elevated PowerShell (Run as administrator):
      powershell -ExecutionPolicy Bypass -File scripts\firewall.ps1 [-Port 8443]
  Creates two inbound allow rules for TCP <Port>:
    - "PadLink (LAN)":       Private profile only, remote address LocalSubnet.
    - "PadLink (Tailscale)": any profile (the Tailscale adapter is often "Public"),
                             remote address 100.64.0.0/10 only.
  Nothing is opened to the Internet. Existing rules with the same names are replaced.
  Pass -Remove to delete them. Other rules that allow python.exe or PadLink.exe on
  every profile (created by the Windows prompt) are listed so you can review them.
#>
param(
    [int]$Port = 8443,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error 'Run this script from PowerShell started as administrator.'
}

$names = 'PadLink (LAN)', 'PadLink (Tailscale)'
foreach ($n in $names) {
    Get-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}
if ($Remove) {
    Write-Host 'PadLink firewall rules removed.'
    return
}

New-NetFirewallRule -DisplayName 'PadLink (LAN)' -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort $Port -Profile Private -RemoteAddress LocalSubnet `
    -Description 'PadLink: phones on the same private network' | Out-Null
New-NetFirewallRule -DisplayName 'PadLink (Tailscale)' -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort $Port -Profile Any -RemoteAddress 100.64.0.0/10 `
    -Description 'PadLink: phones in your Tailscale network' | Out-Null
Write-Host "Rules created for TCP $Port (LAN on Private networks + Tailscale 100.64.0.0/10)."

# Rules created by the Windows prompt can be broader (e.g. Public networks, any address).
$broad = Get-NetFirewallRule -Direction Inbound -Enabled True -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -match 'python|padlink|padlink' -and $names -notcontains $_.DisplayName }
if ($broad) {
    Write-Host ''
    Write-Host 'Review these other rules (a Block rule overrides the Tailscale rule; an Allow rule on Public is broader than needed):'
    $broad | Select-Object DisplayName, Profile, Action | Format-Table -AutoSize
}
