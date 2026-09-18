param([int]$Tail = 50)

$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $ProjectDir 'logs\monitor.log'

if (-not (Test-Path -LiteralPath $LogFile)) {
    throw '尚未找到监控日志。请先运行 .\run.ps1 启动监控。'
}

Write-Host '正在实时查看监控日志；按 Ctrl+C 退出查看（不会停止监控）。' -ForegroundColor Cyan
Get-Content -LiteralPath $LogFile -Encoding UTF8 -Tail $Tail -Wait
