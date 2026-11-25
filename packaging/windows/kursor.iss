; Inno Setup script for the PadLink Windows installer.
; Build: packaging/windows/build.ps1 (needs Inno Setup 6: winget install JRSoftware.InnoSetup)
;
; Per-user install (no administrator rights): PadLink never runs elevated.
; On first launch Windows asks for permission through the firewall: allow PRIVATE networks only.

#define AppVersion "1.1.1"

[Setup]
AppId={{7B6E3C2A-9D41-4E8B-A1F5-2C7D9E0B4F13}
AppName=PadLink
AppVersion={#AppVersion}
AppPublisher=PadLink
DefaultDirName={localappdata}\Programs\PadLink
DefaultGroupName=PadLink
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=PadLink-Setup-{#AppVersion}
SetupIconFile=..\..\server\kursor\assets\kursor.ico
UninstallDisplayIcon={app}\PadLink.exe
LicenseFile=..\..\docs\legal\TERMS.md
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Avvia PadLink all'accesso a Windows"; Flags: unchecked

[Files]
Source: "..\..\dist\PadLink\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PadLink"; Filename: "{app}\PadLink.exe"
Name: "{group}\Disinstalla PadLink"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PadLink"; Filename: "{app}\PadLink.exe"; Tasks: desktopicon

[Registry]
; Same key the app's "Avvia all'accesso" checkbox manages; removed on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PadLink"; ValueData: """{app}\PadLink.exe"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\PadLink.exe"; Description: "{cm:LaunchProgram,PadLink}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM PadLink.exe /F"; Flags: runhidden; RunOnceId: "StopKursor"

[UninstallDelete]
; Remove the autostart entry even if it was enabled from inside the app.
Type: files; Name: "{app}\*.log"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'PadLink');
    if MsgBox('Eliminare anche i dati di PadLink (dispositivi associati, certificati, registro accessi)?',
              mbConfirmation, MB_YESNO) = IDYES then
      DelTree(ExpandConstant('{%USERPROFILE}\.padlink'), True, True, True);
  end;
end;
