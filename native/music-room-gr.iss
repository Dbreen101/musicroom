; The Music Room GR for Windows: the installer people download.
;
; 26 Nov 2026: a fellow on Windows double-clicked "Music Room GR.exe" INSIDE the zip without
; unzipping it. Windows then takes out that one file alone, and the app cannot start ("Failed to
; load Python DLL ... python312.dll"): everything it needs is in the "_internal" folder beside it.
; So people get this instead: one file to open. It puts the app in its own folder in the person's
; account (no administrator needed), adds it to the Start menu and the desktop, and opens it.
;
; Made by .github/workflows/windows.yml on GitHub's Windows machines (Inno Setup):
;   ISCC /DAppVer=2026.11.25-5 /DNumVer=2026.11.25.5 /DSrcDir="dist\Music Room GR" music-room-gr.iss
;
; The app's own updater (app_update.py) still swaps the whole app folder from the release's zip, so:
;   - the uninstaller lives OUTSIDE the app folder (an update would otherwise throw it away);
;   - uninstalling removes the whole app folder, whatever an update put in it;
;   - the person's library and settings (%APPDATA%\Music Room GR) are never touched.

#ifndef AppVer
  #define AppVer "0"
#endif
#ifndef NumVer
  #define NumVer "0.0.0.0"
#endif
#ifndef SrcDir
  #define SrcDir "dist\Music Room GR"
#endif
#ifndef OutName
  #define OutName "Install Music Room GR (Windows)"
#endif

[Setup]
AppId={{62C48105-CDBF-4391-875A-AE026C96CA5A}
AppName=Music Room GR
AppVersion={#AppVer}
AppVerName=Music Room GR {#AppVer}
AppPublisher=Daithí Breen
AppPublisherURL=https://github.com/Dbreen101/musicroom
AppSupportURL=https://github.com/Dbreen101/musicroom/releases/latest
VersionInfoVersion={#NumVer}
VersionInfoProductName=Music Room GR
VersionInfoDescription=Music Room GR installer
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DefaultDirName={autopf}\Music Room GR
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableWelcomePage=yes
DisableFinishedPage=yes
UninstallFilesDir={localappdata}\Music Room GR\uninstall
UninstallDisplayName=Music Room GR
UninstallDisplayIcon={app}\Music Room GR.exe
SetupIconFile=AppIcon.ico
OutputDir=Output
OutputBaseFilename={#OutName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[InstallDelete]
; a fresh copy of the app's own parts each time (nothing left over from an older version)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Music Room GR"; Filename: "{app}\Music Room GR.exe"
Name: "{autodesktop}\Music Room GR"; Filename: "{app}\Music Room GR.exe"

[Run]
; open it straight away (also after a silent install)
Filename: "{app}\Music Room GR.exe"; Flags: nowait

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
