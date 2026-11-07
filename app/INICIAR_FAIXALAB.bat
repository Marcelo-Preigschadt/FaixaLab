@echo off
setlocal
cd /d "%~dp0"
findstr /x /c:"0.9.0" ".runtime\ready" >nul 2>nul
if errorlevel 1 (
  call "%~dp0INSTALAR.bat"
  if errorlevel 1 exit /b 1
)
if exist "%~dp0.runtime\deno.exe" set "FAIXALAB_DENO=%~dp0.runtime\deno.exe"
start "FaixaLab" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launcher.py"
