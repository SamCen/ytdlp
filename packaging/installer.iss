#define AppName "yt-dlp Desktop"
#define AppVersion "0.1.0"
#define AppExe "ytdlp-desktop.exe"

[Setup]
AppId={{A7E3C1D2-4B55-4E0A-9C11-2F6B8D0E1A44}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\ytdlp-desktop
DefaultGroupName=yt-dlp Desktop
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=ytdlp-desktop-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

[Files]
Source: "..\dist\ytdlp-desktop\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\yt-dlp 下载器"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\yt-dlp 下载器"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "启动 yt-dlp 下载器"; Flags: nowait postinstall skipifsilent
