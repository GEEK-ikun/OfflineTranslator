# 生成的安装程序（PowerShell + 自解压）。当机器上没有 Inno Setup 时使用。
# 用法（由 build.ps1 自动调用）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File make_sfx_installer.ps1
#
# 产物：dist_installer\OfflineTranslator-Setup-1.0.0.exe
# 行为：解压到 %LOCALAPPDATA%\OfflineTranslator，创建桌面快捷方式与开始菜单项，
#       生成卸载程序（Uninstall-OfflineTranslator.cmd）。

param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$AppName = '离线英汉互译',
    [string]$AppNameEn = 'OfflineTranslator',
    [string]$Version = '1.0.0'
)

$ErrorActionPreference = 'Stop'
$dist     = Join-Path $ProjectRoot 'dist\OfflineTranslator'
$outDir   = Join-Path $ProjectRoot 'dist_installer'
$work     = Join-Path $ProjectRoot 'build_tmp'
$zipPath  = Join-Path $work 'payload.zip'
$sfxStub  = Join-Path $work 'sfx.exe'
$setupSrc = Join-Path $work 'setup.ps1'
$cfgPath  = Join-Path $work 'sfx-config.txt'
$outExe   = Join-Path $outDir "$AppNameEn-Setup-$Version.exe"

if (-not (Test-Path $dist)) { throw "找不到打包产物目录：$dist（请先运行 PyInstaller）" }
New-Item -ItemType Directory -Force -Path $outDir, $work | Out-Null

# --- 1) 找一个 7-Zip（用于制作自解压包） ---
$sevenZip = $null
foreach ($c in @(
    'C:\Program Files\7-Zip\7z.exe',
    'C:\Program Files (x86)\7-Zip\7z.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\7-Zip\7z.exe')
)) { if (Test-Path $c) { $sevenZip = $c; break } }
if (-not $sevenZip) {
    $cmd = Get-Command 7z -ErrorAction SilentlyContinue
    if ($cmd) { $sevenZip = $cmd.Source }
}
if (-not $sevenZip) { throw '未找到 7-Zip（7z.exe），无法生成自解压安装包。请改用 Inno Setup 方案。' }
Write-Host "使用 7-Zip: $sevenZip"

# --- 2) 写安装逻辑脚本（随自解压包一起释放并运行） ---
$setupBody = @'
param([string]$ExtractDir)
$ErrorActionPreference = 'Stop'
$AppName   = '__APPNAME__'
$AppNameEn = '__APPNAMEEN__'
$Version   = '__VERSION__'
$target    = Join-Path $env:LOCALAPPDATA $AppNameEn

Write-Host "正在安装 $AppName $Version 到 $target"
if (Test-Path $target) { Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item (Join-Path $ExtractDir '*') $target -Recurse -Force

$exe = Join-Path $target "$AppNameEn.exe"

# 桌面快捷方式
$desktop = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $desktop "$AppName.lnk"))
$lnk.TargetPath = $exe
$lnk.WorkingDirectory = $target
$lnk.IconLocation = "$exe,0"
$lnk.Description = $AppName
$lnk.Save()

# 开始菜单
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
$lnk2 = $ws.CreateShortcut((Join-Path $startMenu "$AppName.lnk"))
$lnk2.TargetPath = $exe
$lnk2.WorkingDirectory = $target
$lnk2.IconLocation = "$exe,0"
$lnk2.Save()

# 卸载程序
$uninst = Join-Path $target "Uninstall-$AppNameEn.cmd"
$uninstBody = @"
@echo off
chcp 65001 >nul
echo 正在卸载 $AppName ...
taskkill /IM $AppNameEn.exe /F >nul 2>nul
del "%USERPROFILE%\Desktop\$AppName.lnk" >nul 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\$AppName.lnk" >nul 2>nul
choice /c YN /n /m "是否同时删除本机保存的历史记录和设置？[Y/N] "
if errorlevel 2 goto keep
rmdir /s /q "%APPDATA%\$AppNameEn"
:keep
cd /d "%TEMP%"
rmdir /s /q "$target"
echo 卸载完成。
pause
"@
Set-Content -LiteralPath $uninst -Value $uninstBody -Encoding UTF8

Write-Host "安装完成：桌面已创建快捷方式「$AppName」"
Write-Host "安装目录：$target"
Start-Process -FilePath $exe -WorkingDirectory $target
'@
$setupBody = $setupBody.Replace('__APPNAME__', $AppName).Replace('__APPNAMEEN__', $AppNameEn).Replace('__VERSION__', $Version)
Set-Content -LiteralPath $setupSrc -Value $setupBody -Encoding UTF8

# --- 3) 打包 dist 目录 ---
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
& $sevenZip a -tzip -mx=5 "$zipPath" (Join-Path $dist '*') | Out-Null
if ($LASTEXITCODE -ne 0) { throw "7-Zip 打包失败（退出码 $LASTEXITCODE）" }
Write-Host ("载荷大小：{0:N1} MB" -f ((Get-Item $zipPath).Length / 1MB))

# --- 4) 生成自解压配置与 SFX ---
if (Test-Path $sfxStub) { Remove-Item $sfxStub -Force }
& $sevenZip a -tzip -mx=5 "$work\sfx-tmp.7z" | Out-Null
# 7-Zip 自解压模块：若安装目录带 7z.sfx 则使用
$sfxModule = Join-Path (Split-Path $sevenZip) '7z.sfx'
if (-not (Test-Path $sfxModule)) { $sfxModule = Join-Path (Split-Path $sevenZip) '7zCon.sfx' }
if (-not (Test-Path $sfxModule)) { throw '未找到 7-Zip 自解压模块 7z.sfx / 7zCon.sfx' }

$runCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"setup.ps1`" -ExtractDir `"%T%`""
@"
;!@Install@!UTF-8!
Title="离线英汉互译 安装程序"
BeginPrompt="是否安装 离线英汉互译？"
RunProgram="$runCmd"
GUIMode="2"
;!@InstallEnd@!
"@ | Set-Content -LiteralPath $cfgPath -Encoding UTF8

$zipStream = [IO.File]::ReadAllBytes($zipPath)
$cfgStream = [IO.File]::ReadAllBytes($cfgPath)
$sfxStream = [IO.File]::ReadAllBytes($sfxModule)
$out = New-Object System.Collections.Generic.List[byte]
$out.AddRange($sfxStream); $out.AddRange($cfgStream); $out.AddRange($zipStream)
[IO.File]::WriteAllBytes($outExe, $out.ToArray())
Write-Host ("已生成安装包：$outExe  （{0:N1} MB）" -f ((Get-Item $outExe).Length / 1MB))
