; Inno Setup 安装脚本 —— 离线英汉互译 OfflineTranslator
; 生成：OfflineTranslator-Setup-1.0.0.exe
; 行为：可选择安装目录、创建桌面快捷方式、创建开始菜单项、可卸载。

#define MyAppName "离线英汉互译"
#define MyAppNameEn "OfflineTranslator"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "本地离线软件"
#define MyAppExeName "OfflineTranslator.exe"

[Setup]
AppId={{7E2E1F4B-9C3A-4D51-9E7B-1A2C3D4E5F60}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayName={#MyAppName} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist_installer
OutputBaseFilename=OfflineTranslator-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\assets\LICENSE-THIRD-PARTY.md
InfoBeforeFile=..\assets\PRIVACY.txt
AllowNoIcons=yes
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}

[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce
Name: "quicklaunchicon"; Description: "创建快速启动栏图标"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
; 打包后的整个程序目录（含自带离线模型 models\packages）
Source: "..\dist\OfflineTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时询问是否保留历史记录；选择"否"则连同用户数据一起清理
Type: filesandordirs; Name: "{userappdata}\{#MyAppNameEn}\logs"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#MyAppNameEn}');
    if DirExists(DataDir) then
    begin
      if MsgBox('是否同时删除本机保存的历史记录、设置和日志？' + #13#10 +
                '（位置：' + DataDir + '）' + #13#10#13#10 +
                '选择"是"将彻底删除本软件留下的全部数据；选择"否"则保留，便于以后重装继续使用。',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
