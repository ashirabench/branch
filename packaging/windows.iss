; Inno Setup script for "BRANCH for openLCA" (built by .github/workflows/installers.yml).
#define Name "BRANCH for openLCA"
#define Version "0.1.2"

[Setup]
AppId={{6B1C2F4E-8D2A-4C55-9B7E-BRANCHOLCA01}
AppName={#Name}
AppVersion={#Version}
AppPublisher=Ashira Benchimol
DefaultDirName={autopf}\{#Name}
DefaultGroupName={#Name}
PrivilegesRequired=lowest
OutputBaseFilename=BRANCH-for-openLCA-setup
Compression=lzma2
SolidCompression=yes
LicenseFile=..\LICENSE
WizardStyle=modern

[Files]
Source: "..\dist\{#Name}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#Name}"; Filename: "{app}\{#Name}.exe"
Name: "{autodesktop}\{#Name}"; Filename: "{app}\{#Name}.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Run]
Filename: "{app}\{#Name}.exe"; Description: "Open BRANCH for openLCA now"; Flags: nowait postinstall skipifsilent
