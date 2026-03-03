[Setup]
AppName=Line Tracker
AppVersion=0.1.0
DefaultDirName={autopf}\LineTracker
DefaultGroupName=Line Tracker
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=LineTrackerSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
AppId={{D1E6F5A2-3A8C-4A9F-8D6D-3B2B8F7E6A1D}

[Files]
Source: "dist\LineTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app\setup\setup_check.bat"; DestDir: "{app}\setup"; Flags: ignoreversion

[Icons]
Name: "{group}\Line Tracker"; Filename: "{app}\LineTracker.exe"
Name: "{group}\Setup Check"; Filename: "{app}\setup\setup_check.bat"
Name: "{userdesktop}\Line Tracker"; Filename: "{app}\LineTracker.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; Flags: unchecked

[Run]
Filename: "{app}\LineTracker.exe"; Description: "Launch Line Tracker"; Flags: nowait postinstall skipifsilent
