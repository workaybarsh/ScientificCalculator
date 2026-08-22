#define MyAppName "Scientific Calculator"
#define MyAppVersion "1.0"
#define MyAppPublisher "workaybarsh"
#define MyAppURL "https://github.com/workaybarsh/ScientificCalculator"
#define MyAppExeName "ScientificCalculator.exe"

[Setup]
AppId={{6F26D01C-28F8-4C93-8AE1-C24A9418D30B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion=1.0.0.0

DefaultDirName={localappdata}\Programs\Scientific Calculator
DefaultGroupName={#MyAppName}
LicenseFile=..\..\LICENSE

OutputDir=..\..\dist
OutputBaseFilename=ScientificCalculator_Setup

SetupIconFile=..\..\assets\icons\app.ico
WizardImageFile=..\..\assets\installer\wizard_side.bmp
WizardSmallImageFile=..\..\assets\installer\wizard_small.bmp

UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\app.ico

WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes

DisableWelcomePage=no
DisableProgramGroupPage=yes
DisableReadyMemo=no

CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=no
Uninstallable=yes
CreateUninstallRegKey=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupWindowTitle=Scientific Calculator Setup Wizard
WelcomeLabel1=Welcome to Scientific Calculator
WelcomeLabel2=Install Scientific Calculator on your computer.
SelectDirDesc=Choose the folder where Scientific Calculator will be installed.
FinishedHeadingLabel=Completing the Scientific Calculator Setup Wizard
FinishedLabelNoIcons=Scientific Calculator has been successfully installed on your computer.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\..\dist\ScientificCalculator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\assets\icons\app.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Scientific Calculator"; Filename: "{app}\ScientificCalculator.exe"; IconFilename: "{app}\app.ico"
Name: "{autodesktop}\Scientific Calculator"; Filename: "{app}\ScientificCalculator.exe"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\ScientificCalculator.exe"; Description: "Launch Scientific Calculator"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; This is the application's fixed, app-controlled data directory.  Remove it
; completely so a reinstall cannot retain settings, history, SQLite sidecars,
; or diagnostic logs.
Type: filesandordirs; Name: "{localappdata}\ScientificCalculator"
; The user may have chosen an existing installation folder containing unrelated
; files, so it must never be recursively deleted.
Type: dirifempty; Name: "{app}"

[Code]
procedure InitializeWizard;
var
  NL: String;
begin
  NL := Chr(13) + Chr(10);

  WizardForm.WelcomeLabel1.Caption :=
    'Welcome to Scientific Calculator';

  WizardForm.WelcomeLabel1.Font.Size := 18;
  WizardForm.WelcomeLabel1.Font.Style := [fsBold];
  WizardForm.WelcomeLabel1.AutoSize := False;
  WizardForm.WelcomeLabel1.Top := ScaleY(22);
  WizardForm.WelcomeLabel1.Height := ScaleY(62);

  WizardForm.WelcomeLabel2.Caption :=
    'Install Scientific Calculator on your computer.' +
    NL + NL +
    'Fast, offline, and designed for scientific calculations.' +
    NL +
    'Includes calculus, equations, matrices, statistics and more.' +
    NL + NL +
    'To continue, click Next.';

  WizardForm.WelcomeLabel2.Font.Size := 10;
  WizardForm.WelcomeLabel2.AutoSize := False;
  WizardForm.WelcomeLabel2.Top := ScaleY(112);
  WizardForm.WelcomeLabel2.Height := ScaleY(135);
end;
