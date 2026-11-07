@echo off
setlocal
cd /d "%~dp0"
title Preparando FaixaLab
echo.
echo  FAIXALAB - Preparacao inicial
echo  Este processo baixa Python, os motores de audio e o suporte ao YouTube.
echo  Nao e necessario instalar Python manualmente. Aguarde esta janela terminar.
echo.
if not exist ".runtime" mkdir ".runtime"
if not exist ".runtime\uv.exe" (
  powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; $r=Invoke-RestMethod 'https://api.github.com/repos/astral-sh/uv/releases/latest'; $a=$r.assets|Where-Object name -eq 'uv-x86_64-pc-windows-msvc.zip'|Select-Object -First 1; if(!$a){throw 'Pacote uv indisponivel'}; $z=Join-Path (Get-Location) '.runtime\uv.zip'; Invoke-WebRequest -UseBasicParsing $a.browser_download_url -OutFile $z; if($a.digest -and $a.digest.StartsWith('sha256:')){if((Get-FileHash $z -Algorithm SHA256).Hash.ToLower() -ne $a.digest.Substring(7)){throw 'Falha na verificacao do uv'}}; Expand-Archive $z '.runtime' -Force; $p=Get-ChildItem '.runtime' -Filter uv.exe -Recurse|Select-Object -First 1; $d=Join-Path (Get-Location) '.runtime\uv.exe'; if($p.FullName -ne $d){Copy-Item $p.FullName $d}; Remove-Item $z"
  if errorlevel 1 goto erro
)
set "UV_PYTHON_INSTALL_DIR=%~dp0.runtime\python"
".runtime\uv.exe" python install 3.12
if errorlevel 1 goto erro
if not exist ".venv\Scripts\python.exe" ".runtime\uv.exe" venv --python 3.12 .venv
if errorlevel 1 goto erro
".runtime\uv.exe" pip install --python ".venv\Scripts\python.exe" torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto erro
".runtime\uv.exe" pip install --python ".venv\Scripts\python.exe" -r requirements.txt
if errorlevel 1 goto erro
if not exist ".runtime\deno.exe" (
  powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; $r=Invoke-RestMethod 'https://api.github.com/repos/denoland/deno/releases/latest'; $a=$r.assets|Where-Object name -eq 'deno-x86_64-pc-windows-msvc.zip'|Select-Object -First 1; if(!$a){throw 'Pacote Deno indisponivel'}; $z=Join-Path (Get-Location) '.runtime\deno.zip'; Invoke-WebRequest -UseBasicParsing $a.browser_download_url -OutFile $z; if($a.digest -and $a.digest.StartsWith('sha256:')){if((Get-FileHash $z -Algorithm SHA256).Hash.ToLower() -ne $a.digest.Substring(7)){throw 'Falha na verificacao do Deno'}}; Expand-Archive $z '.runtime' -Force; Remove-Item $z"
  if errorlevel 1 goto erro
)
echo.
echo  FaixaLab preparado. Os modelos de IA serao baixados ao processar a primeira musica.
echo 0.9.0>".runtime\ready"
exit /b 0
:erro
echo.
echo  A preparacao encontrou um erro. Verifique a conexao com a internet.
echo  Voce pode executar INSTALAR.bat novamente para retomar.
pause
exit /b 1
