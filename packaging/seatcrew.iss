; Inno Setup script - Windows installer with Start-menu + optional desktop shortcut.
;   pyinstaller packaging\seatcrew.spec --noconfirm   then   iscc /DMyVersion=0.4.0 packaging\seatcrew.iss
#ifndef MyVersion
  #define MyVersion "0.4.1"
#endif
[Setup]
AppId={{6B0E2F3C-5EA7-4C2E-9A1D-5EA7C2E00001}
AppName=SeatCrew
AppVersion={#MyVersion}
AppPublisher=SeatCrew contributors
DefaultDirName={localappdata}\Programs\SeatCrew
DefaultGroupName=SeatCrew
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SeatCrew-{#MyVersion}-windows-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\SeatCrew.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
[Files]
Source: "..\dist\SeatCrew\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
[Icons]
Name: "{group}\SeatCrew"; Filename: "{app}\SeatCrew.exe"
Name: "{group}\Uninstall SeatCrew"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SeatCrew"; Filename: "{app}\SeatCrew.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\SeatCrew.exe"; Description: "{cm:LaunchProgram,SeatCrew}"; Flags: nowait postinstall skipifsilent
