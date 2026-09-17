param([int]$Seconds = 120)
$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir
& .\.runtime\Python312\python.exe -m wx_trade_alert probe --seconds $Seconds
