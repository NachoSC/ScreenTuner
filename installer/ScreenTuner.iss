; ScreenTuner installer  -  Inno Setup 6
;
; Division of labour, so the wizard and the app never disagree:
;   Inno owns the files, the Start Menu entry and the Installed-apps entry.
;   The app owns its own registrations (run-at-login, tray-icon pin), and the
;   uninstaller calls "ScreenTuner.exe --cleanup" to have it remove them.
;
; Per-user install throughout: no admin prompt, nothing outside HKCU and
; %LOCALAPPDATA%, which also means no UAC dialog on an unsigned installer.
;
; Build with:  build-installer.bat

#define AppName        "ScreenTuner"
; Passed in by build-installer.bat as /DAppVersion=x.y.z, derived from
; screentuner.py so the version lives in exactly one place. The fallback
; exists only so the script still compiles if opened directly in the IDE.
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#define AppPublisher   "ScreenTuner"
#define AppURL         "https://github.com/NachoSC/ScreenTuner"
#define AppExe         "ScreenTuner.exe"

[Setup]
AppId={{8F2C4E11-6A3D-4B7E-9C05-3D1A7F62B48A}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}

; Per-user: installs without admin rights and raises no UAC prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes

LicenseFile=..\LICENSE.md
OutputDir=..\dist\installer
OutputBaseFilename=ScreenTuner-{#AppVersion}-setup
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "startup";  Description: "{cm:StartAtLogin}"; GroupDescription: "{cm:Extras}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:Extras}"; Flags: unchecked

[CustomMessages]
english.StartAtLogin=Start ScreenTuner when I sign in
english.Extras=Options:
english.CreateDesktopIcon=Create a desktop shortcut
english.LaunchApp=Run ScreenTuner now
english.NvidiaNote=Digital vibrance needs an NVIDIA GPU. Gamma, contrast and brightness work on any GPU.
spanish.StartAtLogin=Iniciar ScreenTuner al iniciar sesion
spanish.Extras=Opciones:
spanish.CreateDesktopIcon=Crear un acceso directo en el escritorio
spanish.LaunchApp=Ejecutar ScreenTuner ahora
spanish.NvidiaNote=La vibracion digital necesita una GPU NVIDIA. Gamma, contraste y brillo funcionan en cualquier GPU.

[Files]
; The whole --onedir tree: the exe is useless without the runtime beside it.
Source: "..\dist\ScreenTuner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";       Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} on GitHub"; Filename: "{#AppURL}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same key and value name the app's own "Start with Windows" toggle uses, so the
; two stay in agreement rather than each keeping their own idea of the setting.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "ScreenTuner"; ValueData: """{app}\{#AppExe}"""; \
    Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Let the app remove what only it knows how to find - notably the tray-icon pin,
; whose registry key is named by a hash of the executable path.
Filename: "{app}\{#AppExe}"; Parameters: "--cleanup"; Flags: runhidden; RunOnceId: "cleanup"

[UninstallDelete]
Type: files; Name: "{app}\screentuner.log"
Type: dirifempty; Name: "{app}"

[Code]
procedure InitializeWizard;
begin
  WizardForm.LicenseAcceptedRadio.Checked := False;
end;

// profiles.json is the user's own work, so leave it unless they say otherwise.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Cfg: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Cfg := ExpandConstant('{app}\profiles.json');
    // Never ask in silent mode: /SUPPRESSMSGBOXES would auto-answer Yes and
    // throw away the user's profiles without them ever seeing the question.
    if FileExists(Cfg) and (not UninstallSilent) then
      if MsgBox('Remove your saved profiles (profiles.json) as well?',
                mbConfirmation, MB_YESNO) = IDNO then
        Cfg := ''
      else
        DeleteFile(Cfg);
    RemoveDir(ExpandConstant('{app}'));
  end;
end;
