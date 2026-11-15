#define AppVersion "0.3.0"

[Setup]
AppId={{EA8E4B48-B797-44CC-82D5-58528688A109}
AppName=Vocal Studio
AppVersion={#AppVersion}
AppPublisher=Vocal Studio
DefaultDirName={localappdata}\Programs\Vocal Studio
DefaultGroupName=Vocal Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=VocalStudio-Setup-{#AppVersion}-windows-x64
SetupIconFile=..\assets\vocalstudio.ico
UninstallDisplayIcon={app}\VocalStudio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\VocalStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Vocal Studio"; Filename: "{app}\VocalStudio.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Vocal Studio"; Filename: "{app}\VocalStudio.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\VocalStudio.exe"; Description: "{cm:LaunchProgram,Vocal Studio}"; Flags: nowait postinstall skipifsilent
