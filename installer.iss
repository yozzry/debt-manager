; Debt Manager - Inno Setup installer script
; Build: "C:\Users\YUZZRY\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss

#define MyAppName "DebtManager"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Debt Manager"
#define MyAppExeName "DebtManager.exe"
#define MyAppId "8A5F3C9B-7D2E-4A61-9C3D-E5B7F1A0C2D4"
#define SrcDir "dist\DebtManager"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userappdata}\DebtManager
DefaultGroupName=DebtManager
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=DebtManagerSetup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
AlwaysShowDirOnReadyPage=yes
AppendDefaultDirName=yes
UsePreviousAppDir=yes
RestartApplications=no
CloseApplications=no
MinVersion=10.0
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Debt Manager
LanguageDetectionMethod=locale

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SrcDir}\DebtManager.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\install_baileys.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\start_baileys.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\stop.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#SrcDir}\baileys_service\*"; DestDir: "{app}\baileys_service"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "auth_session\*"

[Icons]
Name: "{autoprograms}\DebtManager"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\DebtManager"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,DebtManager}"; Flags: nowait postinstall skipifsilent

[Code]
function IsNodeInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('where.exe', 'node', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function IsGitInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('where.exe', 'git', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Msg: string;
  ProcessID: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not IsNodeInstalled() then
    begin
      Msg := 'تم تثبيت DebtManager بنجاح.' + #13#10 + #13#10 +
             'تنبيه: ميزة إرسال رسائل WhatsApp تحتاج إلى Node.js.' + #13#10 +
             'البرنامج الرئيسي (إدارة الديون والفواتير) يعمل بدونها.' + #13#10 + #13#10 +
             'هل تريد فتح صفحة تحميل Node.js الآن؟';
      if MsgBox(Msg, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        ShellExec('open', 'https://nodejs.org/', '', '', SW_SHOWNORMAL, ewNoWait, ProcessID);
    end;
    if not IsGitInstalled() then
    begin
      Msg := 'ملاحظة: لم يتم العثور على Git.' + #13#10 +
             'Git مطلوب فقط عند إعادة تثبيت اعتماديات WhatsApp (نادراً ما تحتاجه).' + #13#10 +
             'يمكنك تحميله من https://git-scm.com/';
      MsgBox(Msg, mbInformation, MB_OK);
    end;
  end;
end;
