@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0INSTALAR.bat"
  if errorlevel 1 exit /b 1
)
echo Feche a janela do FaixaLab antes de atualizar o suporte ao YouTube.
".runtime\uv.exe" pip install --python ".venv\Scripts\python.exe" --upgrade "yt-dlp[default]>=2026.10.26"
if errorlevel 1 goto erro
".venv\Scripts\python.exe" prepare_youtube.py
if errorlevel 1 goto erro
rem The audio engine profile is unchanged between 0.10.0 and 0.10.1.
rem Mark this completed targeted update without reinstalling the audio models.
findstr /x /c:"0.10.0" /c:"0.10.1" ".runtime\ready" >nul 2>nul
if not errorlevel 1 >".runtime\ready" echo 0.10.1
echo Suporte ao YouTube atualizado e runtime validado. Abra o FaixaLab novamente.
pause
exit /b 0
:erro
echo Nao foi possivel atualizar o suporte ao YouTube. O erro aparece acima.
pause
exit /b 1
