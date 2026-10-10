; ============================================================================
;  幽灵阅读器 (Ghost Reader) —— Windows 7 兼容版安装包
;
;  编译:  ISCC.exe installer_win7.iss
;  产物:  installer_out\GhostReader-Setup-Win7-v1.0.1.exe
;
;  说明:  依赖 dist_w7\幽灵阅读器-Win7.exe
;         由 Python 3.8.20 + PySide2 5.15.2.1 + PyInstaller 5.13.2 打包
;         适用于 Windows 7 SP1 / 8 / 8.1 / 10 / 11 (64 位)
; ============================================================================

#define MyAppName        "幽灵阅读器"
#define MyAppNameEn      "Ghost Reader"
#define MyAppVersion     "1.0.1"
#define MyAppPublisher   "Li Hanyu"
#define MyAppExeName     "幽灵阅读器-Win7.exe"
#define MyAppSrcDir      "dist_w7"
#define MyAppUrl         "https://github.com/lihanyu-six/ghost-reader"

[Setup]
AppId={{7E4C2A91-3F5B-4D8E-9A21-6B0C8D7E4F13}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}/issues
AppUpdatesURL={#MyAppUrl}/releases
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} - Windows 7 Compatible Edition
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
AllowNoIcons=yes
LicenseFile=LICENSE_CN.txt
OutputDir=installer_out
OutputBaseFilename=GhostReader-Setup-Win7-v{#MyAppVersion}
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
MinVersion=6.1sp1

[Languages]
Name: "chinese"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
Source: "{#MyAppSrcDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md";                       DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE";                         DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE_CN.txt";                  DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY_LICENSES.md";         DestDir: "{app}"; Flags: ignoreversion
Source: "Win7-说明.txt";                    DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";           Filename: "{app}\{#MyAppExeName}"
Name: "{group}\使用说明（README）";      Filename: "{app}\README.md"
Name: "{group}\Win7 使用注意";           Filename: "{app}\Win7-说明.txt"
Name: "{group}\卸载 {#MyAppName}";       Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";     Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
{ ---------------------------------------------------------------------------
  检测 VC++ 2015-2022 Redistributable (x64)
  Win7 上 api-ms-win-crt-*.dll 由该组件提供，缺失则程序无法启动
  --------------------------------------------------------------------------- }
function VCRedistInstalled(): Boolean;
var
  Version: String;
  Names: TArrayOfString;
  I: Integer;
begin
  Result := False;
  { VC++ 2015-2022 x64 卸载项名称 }
  Names := ['VC_REDIST_X64', 'vc_redist.x64'];
  for I := 0 to GetArrayLength(Names) - 1 do
  begin
    if RegValueExists(HKLM64, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\' + Names[I], 'DisplayName') then
    begin
      Result := True;
      Exit;
    end;
  end;

  { 按 GUID 查（不同版本 GUID 兼容性最好的是 v14 系列）}
  if RegKeyExists(HKLM64, 'SOFTWARE\Classes\Installer\Products') then
  begin
    { 退避方案：直接检查系统目录里是否存在 ucrtbase.dll + vcruntime140.dll }
    if FileExists(ExpandConstant('{sys}\vcruntime140.dll')) and
       FileExists(ExpandConstant('{sys}\ucrtbase.dll')) then
      Result := True;
  end;

  { 最后退避：检查 SysWOW64（即使装的是 32 位版本，也有助）}
  if (not Result) and FileExists(ExpandConstant('{sys}\vcruntime140.dll')) then
    Result := True;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { 安装文件写完后做一次运行库检查，缺失则提示 }
  if CurStep = ssPostInstall then
  begin
    if not VCRedistInstalled() then
    begin
      MsgBox(
        '检测到本机可能未安装「Microsoft Visual C++ 2015-2022 运行库 (64位)」。' + #13#10 + #13#10 +
        'Windows 7 上，程序依赖该运行库提供的 api-ms-win-crt-*.dll 系列文件。' + #13#10 +
        '如果程序启动时报「缺少 api-ms-win-crt-*.dll」或「0xc000007b」，' + #13#10 +
        '请安装该运行库后重试。' + #13#10 + #13#10 +
        '下载地址（微软官方）:' + #13#10 +
        'https://aka.ms/vs/17/release/vc_redist.x64.exe' + #13#10 + #13#10 +
        '（Win7 系统还需确保已安装 SP1 及 KB2533623 / KB2999226 补丁）',
        mbInformation, MB_OK);
    end;
  end;
end;
