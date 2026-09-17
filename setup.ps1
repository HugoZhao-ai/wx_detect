$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

$RuntimeDir = Join-Path $ProjectDir '.runtime\Python312'
$RuntimePython = Join-Path $RuntimeDir 'python.exe'
$RuntimeZip = Join-Path $ProjectDir 'python-3.12.10-embed-amd64.zip'
$GetPip = Join-Path $ProjectDir 'get-pip.py'

if (-not (Test-Path -LiteralPath $RuntimePython)) {
    Write-Host '下载官方 Python 3.12.10 便携运行时…'
    Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -OutFile $RuntimeZip
    $ActualMd5 = (Get-FileHash -LiteralPath $RuntimeZip -Algorithm MD5).Hash.ToLowerInvariant()
    if ($ActualMd5 -ne 'fe8ef205f2e9c3ba44d0cf9954e1abd3') {
        throw "Python 运行时校验失败：$ActualMd5"
    }
    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    Expand-Archive -LiteralPath $RuntimeZip -DestinationPath $RuntimeDir -Force
    Copy-Item -LiteralPath (Join-Path $ProjectDir 'python312._pth.template') -Destination (Join-Path $RuntimeDir 'python312._pth') -Force
    Remove-Item -LiteralPath $RuntimeZip
}

if (-not (& $RuntimePython -m pip --version 2>$null)) {
    Write-Host '安装 pip…'
    Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $GetPip
    & $RuntimePython $GetPip
    if ($LASTEXITCODE -ne 0) { throw 'pip 安装失败' }
    Remove-Item -LiteralPath $GetPip
}

& $RuntimePython -m pip install setuptools wheel
if ($LASTEXITCODE -ne 0) { throw '构建工具安装失败' }
& $RuntimePython -m pip install --no-build-isolation -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '项目依赖安装失败' }

if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
    Write-Host '已创建 .env，请填入新的 DEEPSEEK_API_KEY。' -ForegroundColor Yellow
}

Write-Host '安装完成。下一步：.\doctor.ps1' -ForegroundColor Green
