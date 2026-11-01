# 一键打包脚本：生成 dist\OfflineTranslator\OfflineTranslator.exe
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
Write-Host "项目目录: $ProjectRoot"

if (-not $Python) {
    foreach ($candidate in @("$ProjectRoot\venv2\Scripts\python.exe", "$ProjectRoot\venv\Scripts\python.exe")) {
        if (Test-Path $candidate) { $Python = $candidate; break }
    }
}
if (-not $Python -or -not (Test-Path $Python)) { throw '未找到虚拟环境 Python，请先创建 venv 并安装 requirements.txt' }
Write-Host "使用 Python: $Python"

# 清理旧产物
foreach ($p in @("$ProjectRoot\build\OfflineTranslator", "$ProjectRoot\dist\OfflineTranslator")) {
    if (Test-Path $p) { Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue }
}
New-Item -ItemType Directory -Force -Path "$ProjectRoot\dist" | Out-Null

$env:OFFLINETRANSLATOR_ROOT = $ProjectRoot
Push-Location "$ProjectRoot\build_tools"
try {
    & $Python -m PyInstaller --noconfirm --clean `
        --distpath "$ProjectRoot\dist" `
        --workpath "$ProjectRoot\build\pyinstaller" `
        "$ProjectRoot\build_tools\OfflineTranslator.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败（退出码 $LASTEXITCODE）" }
} finally {
    Pop-Location
}

$exe = "$ProjectRoot\dist\OfflineTranslator\OfflineTranslator.exe"
if (-not (Test-Path $exe)) { throw "未生成 $exe" }
$size = (Get-ChildItem "$ProjectRoot\dist\OfflineTranslator" -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("打包完成: $exe")
Write-Host ("产物大小: {0:N1} MB" -f ($size / 1MB))
