@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title Preparando Importador FaixaLab
echo Preparando Python, FFmpeg e suporte ao YouTube.
if not exist ".runtime" mkdir ".runtime"
if not exist ".runtime\uv.exe" (
  powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; $r=Invoke-RestMethod 'https://api.github.com/repos/astral-sh/uv/releases/latest'; $arch=if($env:PROCESSOR_ARCHITECTURE -eq 'ARM64'){'aarch64'}else{'x86_64'}; $a=$r.assets|Where-Object name -eq ('uv-'+$arch+'-pc-windows-msvc.zip')|Select-Object -First 1; if(!$a){throw 'Pacote uv indisponivel'}; $z=Join-Path (Get-Location) '.runtime\uv.zip'; Invoke-WebRequest -UseBasicParsing $a.browser_download_url -OutFile $z; if($a.digest -and $a.digest.StartsWith('sha256:')){if((Get-FileHash $z -Algorithm SHA256).Hash.ToLower() -ne $a.digest.Substring(7)){throw 'Falha na verificacao do uv'}}; Expand-Archive $z '.runtime' -Force; $p=Get-ChildItem '.runtime' -Filter uv.exe -Recurse|Select-Object -First 1; $d=Join-Path (Get-Location) '.runtime\uv.exe'; if($p.FullName -ne $d){Copy-Item $p.FullName $d}; Remove-Item $z"
  if errorlevel 1 goto erro
)
set "UV_PYTHON_INSTALL_DIR=%~dp0.runtime\python"
".runtime\uv.exe" python install 3.12
if errorlevel 1 goto erro
if not exist ".venv\Scripts\python.exe" ".runtime\uv.exe" venv --python 3.12 .venv
if errorlevel 1 goto erro
".runtime\uv.exe" pip install --python ".venv\Scripts\python.exe" --upgrade "yt-dlp[default]>=2026.10.26" imageio-ffmpeg
if errorlevel 1 goto erro
".venv\Scripts\python.exe" prepare_youtube.py
if errorlevel 1 goto erro
>".runtime\ready" echo 1
exit /b 0
:erro
echo Falha na instalacao. Execute INSTALAR.bat para tentar novamente.
if /I not "%~1"=="/quiet" pause
exit /b 1
