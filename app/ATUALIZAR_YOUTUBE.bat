@echo off
setlocal
cd /d "%~dp0"
if not exist ".runtime\ready" call "%~dp0INSTALAR.bat"
if errorlevel 1 exit /b 1
".runtime\uv.exe" pip install --python ".venv\Scripts\python.exe" --upgrade "yt-dlp[default]"
if errorlevel 1 (
  echo Nao foi possivel atualizar o suporte ao YouTube.
) else (
  echo Suporte ao YouTube atualizado. Feche e abra o FaixaLab.
)
pause
