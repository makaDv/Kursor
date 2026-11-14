; Inno Setup script for the Kursor Windows installer.
; Build: packaging/windows/build.ps1 (needs Inno Setup 6: winget install JRSoftware.InnoSetup)
;
; Per-user install (no administrator rights): Kursor never runs elevated.
; On first launch Windows asks for permission through the firewall: allow PRIVATE networks only.

#define AppVersion "1.0.0"

[Setup]
AppId={{7B6E3C2A-9D41-4E8B-A1F5-2C7D9E0B4F13}
AppName=Kursor
AppVersion={#AppVersion}
AppPublisher=Kursor
DefaultDirName={localappdata}\Programs\Kursor
DefaultGroupName=Kursor
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Kursor-Setup-{#AppVersion}
SetupIconFile=..\..\server\kursor\assets\kursor.ico
UninstallDisplayIcon={app}\Kursor.exe
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
Name: "autostart"; Description: "Avvia Kursor all'accesso a Windows"; Flags: unchecked

[Files]
Source: "..\..\dist\Kursor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Kursor"; Filename: "{app}\Kursor.exe"
Name: "{group}\Disinstalla Kursor"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Kursor"; Filename: "{app}\Kursor.exe"; Tasks: desktopicon

[Registry]
; Same key the app's "Avvia all'accesso" checkbox manages; removed on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Kursor"; ValueData: """{app}\Kursor.exe"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Kursor.exe"; Description: "{cm:LaunchProgram,Kursor}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM Kursor.exe /F"; Flags: runhidden; RunOnceId: "StopKursor"

[UninstallDelete]
; Remove the autostart entry even if it was enabled from inside the app.
Type: files; Name: "{app}\*.log"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Kursor');
    if MsgBox('Eliminare anche i dati di Kursor (dispositivi associati, certificati, registro accessi)?',
              mbConfirmation, MB_YESNO) = IDYES then
      DelTree(ExpandConstant('{%USERPROFILE}\.kursor'), True, True, True);
  end;
end;
