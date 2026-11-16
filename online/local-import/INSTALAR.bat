@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title Preparando Importador FaixaLab
echo Preparando Python, FFmpeg e suporte ao YouTube.
if not exist ".runtime" mkdir ".runtime"
if not exist ".runtime\uv.exe" (
  powershell.exe -NoProfile -NonInteractive -Command "& ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path (Get-Location) 'prepare-runtime.ps1'))))"
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
