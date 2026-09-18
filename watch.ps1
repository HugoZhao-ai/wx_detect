param([int]$Tail = 50)

$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $ProjectDir 'logs\monitor.log'

if (-not (Test-Path -LiteralPath $LogFile)) {
    throw 'Monitor log not found. Run .\run.ps1 first.'
}

Write-Host 'Watching monitor log. Press Ctrl+C to exit; monitoring will continue.' -ForegroundColor Cyan
Get-Content -LiteralPath $LogFile -Encoding UTF8 -Tail $Tail -Wait
