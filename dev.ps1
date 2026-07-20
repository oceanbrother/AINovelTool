# 开发环境一键启动：数据库 / 后端 / 前端 各占一个终端窗口。
#
#   .\dev.ps1
#
# 前提：Docker Desktop 必须已手动启动（脚本会检查并提醒，不会代开——
# 本机的 Docker Desktop 冷启动偶发 stale socket 崩溃，见 README 故障排查）。

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# ---- 0. Docker 检查（只提醒，不代开）---------------------------------------
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  [!] Docker 引擎未运行。" -ForegroundColor Red
    Write-Host "      请先手动打开 Docker Desktop，等托盘图标变绿后重新运行 .\dev.ps1" -ForegroundColor Yellow
    Write-Host "      （若启动时报 'removing stale socket' 崩溃：把" -ForegroundColor DarkGray
    Write-Host "        %LOCALAPPDATA%\Docker\run 目录改名后再启动即可）" -ForegroundColor DarkGray
    Write-Host ""
    exit 1
}
Write-Host "  [ok] Docker 引擎在线" -ForegroundColor Green

# ---- 1. 数据库终端 ----------------------------------------------------------
# 前台 attach 运行，日志直接可见；关窗即停容器。
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'DB · pgvector :5433'; " +
    "Set-Location '$root'; docker compose up db"
)

# ---- 2. 后端终端 ------------------------------------------------------------
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'API · uvicorn :8000'; " +
    "Set-Location '$root\backend'; " +
    ".\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
)

# ---- 3. 前端终端 ------------------------------------------------------------
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'WEB · vite :5173'; " +
    "Set-Location '$root\frontend'; npm run dev"
)

Write-Host "  [ok] 已拉起三个终端：DB(5433) / API(8000) / WEB(5173)" -ForegroundColor Green
Write-Host "       写字台地址： http://localhost:5173" -ForegroundColor Cyan
