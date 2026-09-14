#Requires -Version 5.1
<#
.SYNOPSIS
    一键启动本地开发环境：FastAPI 后端 + Go 认证网关。

.DESCRIPTION
    本地完整开发需要两个服务，本脚本把它们的启动、前置检查和健康检查都收敛成一条命令。
    两个服务各自开一个窗口，日志互不干扰；关窗口即停对应服务。

    ┌─ 浏览器 → Go 网关(:8080) → FastAPI(:8001)
    │              └─ 校验 JWT、注入 X-User-ID
    └─ MySQL(:3306) 只给网关用，FastAPI 不连它

.PARAMETER BackendPort
    FastAPI 端口，默认 8001（与 vite 代理一致）。

.PARAMETER GatewayPort
    Go 网关端口，默认 8080。

.PARAMETER SkipAuth
    跳过 JWT 校验，网关会注入固定用户 local_dev(id=1)。
    只想调前端、不想每次登录时用；要测真实登录流程就不要加。

.PARAMETER JwtSecret
    签发/校验 JWT 的密钥。两个进程必须一致，否则 token 验不过。
    本地开发用默认值即可；生产必须改。

.EXAMPLE
    .\start-dev.ps1
    启动 FastAPI:8001 + 网关:8080（默认开启真实认证）

.EXAMPLE
    .\start-dev.ps1 -SkipAuth
    启动两个服务，但网关跳过认证（固定用户 local_dev）
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8001,
    [int]$GatewayPort = 8080,
    [switch]$SkipAuth,
    [string]$JwtSecret = 'local-dev-secret'
)

$ErrorActionPreference = 'Stop'

$BackendDir = $PSScriptRoot
$AuthDir    = Join-Path $BackendDir 'auth'
$ExePath    = Join-Path $AuthDir 'auth.exe'

# ─────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────
function Write-Step($msg) { Write-Host "  $msg" -ForegroundColor Gray }
function Write-Ok($msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err2($msg) { Write-Host "  [ERR]  $msg" -ForegroundColor Red }

function Test-PortInUse([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

function Wait-Port([int]$Port, [int]$TimeoutSec = 40) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $c = New-Object System.Net.Sockets.TcpClient
            $c.Connect('127.0.0.1', $Port)
            $c.Close()
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

function Wait-HttpOk([string]$Url, [int]$TimeoutSec = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($r.StatusCode -eq 200) { return $true }
        } catch {
            # 401/连接被拒都算「还没就绪」，继续等
        }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

# ─────────────────────────────────────────────────────────────
Write-Host ''
Write-Host 'Quantum Agent Platform — 本地开发环境' -ForegroundColor Cyan
Write-Host '──────────────────────────────────────' -ForegroundColor DarkGray

# ① 前置检查
Write-Host "`n[1/4] 前置检查" -ForegroundColor White

if (-not (Test-Path (Join-Path $BackendDir 'app\main.py'))) {
    Write-Err2 "找不到 $BackendDir\app\main.py，请从 backend 目录运行本脚本"
    exit 1
}
Write-Ok "FastAPI 项目目录: $BackendDir"

if (-not (Test-Path $ExePath)) {
    Write-Warn2 "auth.exe 不存在，开始编译 Go 网关…"
    Push-Location $AuthDir
    try {
        & go build -o auth.exe .
        if ($LASTEXITCODE -ne 0) { throw "go build 返回 $LASTEXITCODE" }
    } catch {
        Write-Err2 "编译失败: $_"
        Write-Err2 "请确认已安装 Go（go version）"
        Pop-Location
        exit 1
    } finally {
        Pop-Location
    }
    if (-not (Test-Path $ExePath)) { Write-Err2 "编译后仍未找到 auth.exe"; exit 1 }
    Write-Ok "Go 网关编译完成"
} else {
    Write-Ok "Go 网关已编译: auth.exe"
}

# MySQL 只被网关使用；连不上不阻断（SKIP_AUTH 时可能用不到），但值得提醒
$mysqlUp = Wait-Port 3306 3
if ($mysqlUp) {
    Write-Ok "MySQL(3306) 可连接"
} else {
    Write-Warn2 "MySQL(3306) 连不上 —— 网关会启动失败。启动 MySQL 后重试，或确认服务已开"
}

# ② 端口检查
#
# 端口已被占用一律视为「那个服务已经在跑」，只补启动缺的那个 —— 而不是整体退出。
# 这样 FastAPI 开着时也能单独把网关补起来（最常见的场景：网关挂了但后端还活着）。
Write-Host "`n[2/4] 端口检查" -ForegroundColor White

$startApi = -not (Test-PortInUse $BackendPort)
$startGw  = -not (Test-PortInUse $GatewayPort)

if ($startApi) { Write-Ok "FastAPI 端口 $BackendPort 空闲，将启动" }
else           { Write-Warn2 "FastAPI 端口 $BackendPort 已被占用 —— 认为它已在运行，跳过启动" }

if ($startGw)  { Write-Ok " 网关  端口 $GatewayPort 空闲，将启动" }
else           { Write-Warn2 " 网关  端口 $GatewayPort 已被占用 —— 认为它已在运行，跳过启动" }

# ③ 启动
Write-Host "`n[3/4] 启动服务" -ForegroundColor White

if (-not $startApi -and -not $startGw) {
    Write-Ok "两个服务都已在运行，无需启动"
} else {
    if ($startApi) {
        # FastAPI —— 工作目录必须是 backend/（大量相对路径依赖它）
        $apiCmd = "`$Host.UI.RawUI.WindowTitle = 'QAP FastAPI :$BackendPort'; " +
                  "python -m uvicorn app.main:app --reload --host 0.0.0.0 --port $BackendPort"
        Start-Process powershell.exe -ArgumentList '-NoExit', '-Command', $apiCmd -WorkingDirectory $BackendDir
        Write-Ok "FastAPI 已启动（新窗口）"
    }

    if ($startGw) {
        # Go 网关 —— BACKEND_URL 不设会默认指向 8000，必须显式传
        $skipVal = if ($SkipAuth) { 'true' } else { 'false' }
        $gwCmd = "`$Host.UI.RawUI.WindowTitle = 'QAP Gateway :$GatewayPort'; " +
                 "`$env:BACKEND_URL = 'http://127.0.0.1:$BackendPort'; " +
                 "`$env:SKIP_AUTH = '$skipVal'; " +
                 "`$env:JWT_SECRET = '$JwtSecret'; " +
                 "& '.\auth.exe'"
        Start-Process powershell.exe -ArgumentList '-NoExit', '-Command', $gwCmd -WorkingDirectory $AuthDir
        Write-Ok "Go 网关已启动（新窗口）"
    }
}

# ④ 健康检查
Write-Host "`n[4/4] 等待就绪…" -ForegroundColor White

$apiOk = Wait-HttpOk "http://127.0.0.1:$BackendPort/api/health/server"
$gwOk  = Wait-Port $GatewayPort 20

if ($apiOk) { Write-Ok "FastAPI  :$BackendPort 就绪" } else { Write-Err2 "FastAPI  :$BackendPort 超时未就绪（看它的窗口）" }
if ($gwOk)  { Write-Ok "Go 网关  :$GatewayPort 就绪" } else { Write-Err2 "Go 网关  :$GatewayPort 超时未就绪（看它的窗口）" }

# ─────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '──────────────────────────────────────' -ForegroundColor DarkGray
if ($apiOk -and $gwOk) {
    Write-Host ' 本地开发环境已就绪' -ForegroundColor Green
} else {
    Write-Host ' 部分服务未就绪，请查看对应窗口的报错' -ForegroundColor Yellow
}
Write-Host ''
Write-Host "   FastAPI      http://127.0.0.1:$BackendPort" -ForegroundColor Cyan
Write-Host "     API 文档   http://127.0.0.1:$BackendPort/docs" -ForegroundColor DarkGray
Write-Host "   Go 网关      http://127.0.0.1:$GatewayPort" -ForegroundColor Cyan
Write-Host "   认证模式     $(if ($SkipAuth) { 'SKIP_AUTH=true（固定用户 local_dev，不用登录）' } else { '真实 JWT（可用 admin / 或注册新账号）' })" -ForegroundColor DarkGray
Write-Host ''
Write-Host '   停止服务：    关闭本脚本新开的那两个窗口即可' -ForegroundColor DarkGray
Write-Host ''
Write-Host '   链路：浏览器 → vite(5173) → 网关(8080) → FastAPI(8001)' -ForegroundColor DarkGray
Write-Host '         认证接口由网关直接处理；其余 /api 由网关校验 JWT 并注入 X-User-ID 后转发' -ForegroundColor DarkGray
Write-Host ''
Write-Host '   下一步：前端另开一个终端跑  cd frontend; npm run dev' -ForegroundColor Cyan
Write-Host '   （vite 代理已全量指向网关，无需再改配置）' -ForegroundColor DarkGray
Write-Host ''
