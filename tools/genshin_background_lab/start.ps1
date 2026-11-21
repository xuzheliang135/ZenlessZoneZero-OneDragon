$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 uv。请先安装：https://docs.astral.sh/uv/"
}
uv run --python 3.11 --extra gamepad --extra wgc genshin-background-lab

