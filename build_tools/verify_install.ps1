# 安装包全流程验证脚本（安装 -> 检查 -> 离线自检 -> 界面冒烟 -> 卸载）
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File verify_install.ps1 [-KeepInstalled]
#
# 说明：安装包会被复制到一个纯 ASCII 临时路径下再执行，
#       以避免某些启动方式对含中文/空格路径的处理问题（与安装包本身无关）。
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Setup = '',
    [switch]$KeepInstalled
)

$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
if (-not $Setup) { $Setup = Join-Path $ProjectRoot 'dist_installer\OfflineTranslator-Setup-1.0.0.exe' }
$AppName    = '离线英汉互译'
$AppNameEn  = 'OfflineTranslator'
$InstallDir = Join-Path $env:LOCALAPPDATA $AppNameEn
$Desktop    = [Environment]::GetFolderPath('Desktop')
$Shortcut   = Join-Path $Desktop "$AppName.lnk"
$StartMenu  = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName\$AppName.lnk"
$report = New-Object System.Collections.Generic.List[string]

function Say($msg) { Write-Host $msg; $report.Add([string]$msg) | Out-Null }
function Mark($ok) { if ($ok) { 'OK' } else { 'MISSING' } }

Say "===== 1) 安装包信息 ====="
if (-not (Test-Path $Setup)) { Say "FAIL: 找不到安装包 $Setup"; exit 1 }
$setupInfo = Get-Item $Setup
Say ("安装包 : {0}" -f $setupInfo.FullName)
Say ("大小   : {0:N1} MB" -f ($setupInfo.Length / 1MB))
Say ("产品   : {0} {1}" -f $setupInfo.VersionInfo.ProductName, $setupInfo.VersionInfo.ProductVersion)

Say ""
Say "===== 2) 复制到 ASCII 临时路径并静默安装 ====="
$stage = Join-Path $env:TEMP 'otsetup'
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$setupCopy = Join-Path $stage 'OfflineTranslator-Setup-1.0.0.exe'
Copy-Item $Setup $setupCopy -Force
if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue }
$log = Join-Path $stage 'inno-install.log'
Remove-Item $log -Force -ErrorAction SilentlyContinue
Say "安装目录: $InstallDir"
$proc = Start-Process -FilePath $setupCopy -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCANCEL', "/LOG=$log" -Wait -PassThru
Say "安装程序退出码: $($proc.ExitCode)  (0 = 成功)"

Say ""
Say "===== 3) 检查安装结果 ====="
$exe    = Join-Path $InstallDir "$AppNameEn.exe"
$uninst = Join-Path $InstallDir 'unins000.exe'
Say ("主程序            : {0}" -f (Mark (Test-Path $exe)))
Say ("桌面快捷方式      : {0}" -f (Mark (Test-Path $Shortcut)))
Say ("开始菜单项        : {0}" -f (Mark (Test-Path $StartMenu)))
Say ("卸载程序          : {0}" -f (Mark (Test-Path $uninst)))
foreach ($rel in @("_internal\models\packages\translate-en_zh-1_9\model\model.bin",
                   "_internal\models\packages\translate-zh_en-1_9\model\model.bin",
                   "_internal\assets\PRIVACY.txt",
                   "_internal\assets\LICENSE-THIRD-PARTY.md",
                   "_internal\assets\icon.ico")) {
    Say ("随附文件          : {0} -> {1}" -f $rel, (Mark (Test-Path (Join-Path $InstallDir $rel))))
}
$totalMB = 0
if (Test-Path $InstallDir) {
    $totalMB = (Get-ChildItem $InstallDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB
}
Say ("安装体积          : {0:N1} MB" -f $totalMB)
if (Test-Path $Shortcut) {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($Shortcut)
    Say ("快捷方式指向      : {0}" -f $lnk.TargetPath)
    Say ("快捷方式图标      : {0}" -f $lnk.IconLocation)
}

Say ""
Say "===== 4) 从安装目录运行离线自检（程序内部硬阻断网络，等价断网环境） ====="
if (Test-Path $exe) {
    $dataDir = Join-Path $stage 'selftest-data'
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    $env:OFFLINETRANSLATOR_DATA_DIR = $dataDir
    $outFile = Join-Path $stage 'selftest-out.txt'
    $p2 = Start-Process -FilePath $exe -ArgumentList '--selftest' -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $outFile -RedirectStandardError (Join-Path $stage 'selftest-err.txt')
    Get-Content $outFile -ErrorAction SilentlyContinue | ForEach-Object { Say ("    " + $_) }
    Say "自检退出码: $($p2.ExitCode)  (0 = 通过)"
} else {
    Say "SKIP: 主程序不存在"
}

Say ""
Say "===== 5) 图形界面冒烟测试（启动 6 秒后检查进程与网络连接） ====="
if (Test-Path $exe) {
    $gui = Start-Process -FilePath $exe -PassThru
    Start-Sleep -Seconds 6
    $alive = Get-Process -Id $gui.Id -ErrorAction SilentlyContinue
    if ($alive) {
        $alive.Refresh()
        Say ("GUI 进程      : 存活，内存 {0:N0} MB" -f ($alive.WorkingSet64 / 1MB))
        Say ("窗口标题      : '{0}'" -f $alive.MainWindowTitle)
        $conns = @(Get-NetTCPConnection -OwningProcess $gui.Id -ErrorAction SilentlyContinue)
        Say ("网络连接数    : {0} （离线要求为 0）" -f $conns.Count)
        if ($conns.Count -gt 0) {
            $conns | Select-Object RemoteAddress, RemotePort, State | Format-Table -AutoSize | Out-String | ForEach-Object { Say $_ }
        }
    } else {
        Say "GUI 进程      : FAIL（进程已退出）"
    }
    Stop-Process -Id $gui.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
} else {
    Say "SKIP: 主程序不存在"
}

if (-not $KeepInstalled) {
    Say ""
    Say "===== 6) 卸载并检查清理情况 ====="
    if (Test-Path $uninst) {
        $u = Start-Process -FilePath $uninst -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
        Say "卸载程序退出码: $($u.ExitCode)"
        Start-Sleep -Seconds 3
        Say ("安装目录已清理    : {0}" -f (Mark (-not (Test-Path $exe))))
        Say ("桌面快捷方式已清理: {0}" -f (Mark (-not (Test-Path $Shortcut))))
        Say ("开始菜单项已清理  : {0}" -f (Mark (-not (Test-Path $StartMenu))))
    } else {
        Say "SKIP: 未找到卸载程序"
    }
} else {
    Say ""
    Say "（-KeepInstalled：保留已安装的软件与桌面快捷方式，未执行卸载）"
}

# 报告写到系统临时目录：不落在仓库里，避免把验证产物（可能含本机路径）提交上去
$reportPath = Join-Path ([System.IO.Path]::GetTempPath()) 'offlinetranslator-install-verify.txt'
New-Item -ItemType Directory -Force -Path (Split-Path $reportPath) | Out-Null
$report | Set-Content -LiteralPath $reportPath -Encoding UTF8
Say ""
Say "报告已保存: $reportPath"
