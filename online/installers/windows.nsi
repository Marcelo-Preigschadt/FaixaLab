Unicode true
ManifestDPIAware true
RequestExecutionLevel user
Name "Importador FaixaLab"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\FaixaLab Importador"
ShowInstDetails show
SetCompressor /SOLID lzma

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_TITLE "Importador FaixaLab instalado"
!define MUI_FINISHPAGE_TEXT "Volte à aba do FaixaLab e selecione Importar neste aparelho."
!define MUI_FINISHPAGE_LINK "Abrir FaixaLab"
!define MUI_FINISHPAGE_LINK_LOCATION "https://marcelo-preigschadt.github.io/FaixaLab/"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

!define APPKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaixaLabImportador"
!define RUNKEY "Software\Microsoft\Windows\CurrentVersion\Run"

Section
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*"
  IfFileExists "$INSTDIR\.venv\Scripts\pythonw.exe" 0 prepare
  IfFileExists "$INSTDIR\.runtime\ready" done
prepare:
  DetailPrint "Preparando o importador. O primeiro uso baixa os componentes de áudio."
  nsExec::ExecToLog '"$SYSDIR\cmd.exe" /d /c INSTALAR.bat /quiet'
  Pop $0
  IfFileExists "$INSTDIR\.venv\Scripts\pythonw.exe" 0 failed
  StrCmp $0 "0" done failed
failed:
  MessageBox MB_OK|MB_ICONSTOP "Não foi possível preparar o importador. Confira sua conexão e execute o instalador novamente."
  Abort
done:
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  WriteRegStr HKCU "${APPKEY}" "DisplayName" "Importador FaixaLab"
  WriteRegStr HKCU "${APPKEY}" "UninstallString" '$\"$INSTDIR\Desinstalar.exe$\"'
  WriteRegDWORD HKCU "${APPKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APPKEY}" "NoRepair" 1
  WriteRegStr HKCU "${RUNKEY}" "FaixaLabImportador" '$\"$INSTDIR\.venv\Scripts\pythonw.exe$\" $\"$INSTDIR\importador.pyw$\"'
  CreateShortcut "$SMPROGRAMS\Importador FaixaLab.lnk" "$INSTDIR\.venv\Scripts\pythonw.exe" '$\"$INSTDIR\importador.pyw$\"'
  Exec '$\"$INSTDIR\.venv\Scripts\pythonw.exe$\" $\"$INSTDIR\importador.pyw$\"'
SectionEnd

Section "Uninstall"
  DeleteRegValue HKCU "${RUNKEY}" "FaixaLabImportador"
  DeleteRegKey HKCU "${APPKEY}"
  Delete "$SMPROGRAMS\Importador FaixaLab.lnk"
  SetOutPath "$TEMP"
  System::Call 'Kernel32::SetEnvironmentVariable(t "FAIXALAB_INSTALL_DIRECTORY", t "$INSTDIR")'
  nsExec::ExecToLog `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -Command "$$launcher = Join-Path $$env:FAIXALAB_INSTALL_DIRECTORY 'importador.pyw'; Get-CimInstance Win32_Process | Where-Object { $$_.Name -eq 'pythonw.exe' -and $$_.CommandLine -and $$_.CommandLine.IndexOf($$launcher, [StringComparison]::OrdinalIgnoreCase) -ge 0 } | Stop-Process -ErrorAction SilentlyContinue"`
  Pop $0
  RMDir /r "$INSTDIR"
SectionEnd
