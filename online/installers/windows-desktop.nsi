Unicode true
ManifestDPIAware true
RequestExecutionLevel user
Name "FaixaLab para Windows"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\FaixaLab"
ShowInstDetails show

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_TITLE "FaixaLab instalado"
!define MUI_FINISHPAGE_TEXT "Cole o link do YouTube no aplicativo para separar as faixas neste computador."
!define MUI_FINISHPAGE_RUN "$INSTDIR\FaixaLab.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir FaixaLab"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

!define APPKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\FaixaLabDesktop"
!define PROTOCOL "Software\Classes\faixalab-local"

Section
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File "${BOOTSTRAP}"
  SetOutPath "$INSTDIR"
  System::Call 'Kernel32::SetEnvironmentVariable(t "FAIXALAB_SETUP_SCRIPT", t "$PLUGINSDIR\windows-desktop.ps1")'
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -Command "& ([scriptblock]::Create([IO.File]::ReadAllText($$env:FAIXALAB_SETUP_SCRIPT)))"'
  Pop $0
  StrCmp $0 "0" installed
  MessageBox MB_OK|MB_ICONSTOP "Não foi possível preparar o FaixaLab. Confira a mensagem acima e execute o instalador novamente."
  Abort

installed:
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  WriteRegStr HKCU "${APPKEY}" "DisplayName" "FaixaLab para Windows"
  WriteRegStr HKCU "${APPKEY}" "UninstallString" '$\"$INSTDIR\Desinstalar.exe$\"'
  WriteRegDWORD HKCU "${APPKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APPKEY}" "NoRepair" 1
  WriteRegStr HKCU "${PROTOCOL}" "" "URL:FaixaLab para Windows"
  WriteRegStr HKCU "${PROTOCOL}" "URL Protocol" ""
  WriteRegStr HKCU "${PROTOCOL}\shell\open\command" "" '$\"$INSTDIR\FaixaLab.exe$\"'
  CreateShortcut "$SMPROGRAMS\FaixaLab.lnk" "$INSTDIR\FaixaLab.exe"
SectionEnd

Section "Uninstall"
  DeleteRegKey HKCU "${APPKEY}"
  DeleteRegKey HKCU "${PROTOCOL}"
  Delete "$SMPROGRAMS\FaixaLab.lnk"
  SetOutPath "$TEMP"
  RMDir /r "$INSTDIR"
SectionEnd
