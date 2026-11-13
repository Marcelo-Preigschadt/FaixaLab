@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title Importador FaixaLab
if not exist ".runtime\ready" call INSTALAR.bat
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m faixalab.local_import
if errorlevel 1 pause
