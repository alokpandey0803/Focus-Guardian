; Inno Setup script — turns dist\FocusGuardian.exe into a proper installer
; that asks the user about a desktop shortcut, a Start Menu shortcut, and
; offers to launch the app once setup finishes.
;
; HOW TO USE:
;   1. Run build_exe.bat first (produces dist\FocusGuardian.exe).
;   2. Install Inno Setup (free): https://jrsoftware.org/isdl.php
;   3. Open this file in the Inno Setup Compiler and click Compile
;      (or run it from the command line: iscc FocusGuardian.iss).
;   4. The finished installer appears at: installer_output\FocusGuardianSetup.exe
;      That's the single file you hand to someone — running it installs
;      the app, offers a desktop icon, and can launch it when done.
;
; NOTE on the taskbar: Windows (10 and especially 11) doesn't allow any
; installer to silently pin an app to the taskbar for you — Microsoft
; blocked that some years back to stop installers doing it without asking.
; The desktop/Start Menu shortcuts below ARE created automatically; taskbar
; pinning is one extra right-click ("Pin to taskbar") the user does once
; after their first launch, same as it works for every other Windows app.

#define MyAppName "FocusGuardian"
#define MyAppVersion "1.0"
#define MyAppExeName "FocusGuardian.exe"

[Setup]
AppId={{8F2C6B8E-6B2E-4E9A-9E7B-3F3B7D6C9E10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Alok Pandey
AppPublisherURL=https://github.com/alokpandey0803
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=FocusGuardianSetup
Compression=lzma
SolidCompression=yes
SetupIconFile=icon.ico
WizardStyle=modern
; Runs per-user by default — no admin prompt needed to install or use it.
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Ticked by default, like most installers — the user can untick either.
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "startmenu"; Description: "Create a &Start Menu shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenu
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Standard Inno "Launch after install" checkbox, shown on the final wizard
; page and ticked by default — exactly the "run after setup" behavior asked for.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; The app registers its own "run at Windows startup" entry at runtime
; (HKCU Run key) when the user turns that option on inside the app — the
; installer never created it, so it wouldn't otherwise know to remove it.
; Without this, uninstalling would leave a dead startup entry pointing at
; the now-deleted exe. RunOnceId dedupes so this doesn't re-run needlessly.
Filename: "{sys}\reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v {#MyAppName} /f"; Flags: runhidden; RunOnceId: "RemoveStartupEntry"
