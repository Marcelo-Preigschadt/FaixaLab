//go:build windows

package main

import (
    "os"
    "os/exec"
    "path/filepath"
    "syscall"
    "unsafe"
)

func main() {
    executable, err := os.Executable()
    if err != nil { return }
    root := filepath.Dir(executable)
    command := exec.Command("cmd.exe", "/c", "INICIAR_FAIXALAB.bat")
    command.Dir = root
    command.SysProcAttr = &syscall.SysProcAttr{CreationFlags: 0x00000010}
    if err = command.Run(); err != nil {
        title, _ := syscall.UTF16PtrFromString("FaixaLab")
        message, _ := syscall.UTF16PtrFromString("Nao foi possivel iniciar. Abra INICIAR_COM_DIAGNOSTICO.bat para ver o detalhe do erro.")
        syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(message)), uintptr(unsafe.Pointer(title)), 0x10)
    }
}
