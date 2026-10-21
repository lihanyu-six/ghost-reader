; ============================================================================
;  幽灵阅读器 (Ghost Reader) —— Inno Setup 6 安装包脚本
;
;  编译:  ISCC.exe installer.iss
;  产物:  installer_out\幽灵阅读器_Setup_v1.0.0.exe
;
;  说明:  依赖 dist_v5\幽灵阅读器.exe（由 PyInstaller 生成）
; ============================================================================

#define MyAppName        "幽灵阅读器"
#define MyAppNameEn      "Ghost Reader"
#define MyAppVersion     "1.0.2"
#define MyAppPublisher   "Li Hanyu"
#define MyAppExeName     "幽灵阅读器.exe"
#define MyAppSrcDir      "dist_fix"

[Setup]
AppId={{7E4C2A91-3F5B-4D8E-9A21-6B0C8D7E4F13}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
AllowNoIcons=yes
LicenseFile=LICENSE_CN.txt
OutputDir=installer_out
OutputBaseFilename=GhostReader-Setup-v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=app.ico
ShowLanguageDialog=no

[Languages]
Name: "chinese"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
Source: "{#MyAppSrcDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md";                DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE";                  DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE_CN.txt";           DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY_LICENSES.md";  DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";           Filename: "{app}\{#MyAppExeName}"
Name: "{group}\使用说明（README）";      Filename: "{app}\README.md"
Name: "{group}\卸载 {#MyAppName}";       Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";     Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
