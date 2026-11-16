#!/usr/bin/env bash
set -euo pipefail
umask 077

destination="${XDG_DATA_HOME:-$HOME/.local/share}/FaixaLab/Importador"
mkdir -p "$destination/.runtime"
log="$destination/.runtime/instalacao.log"

if {
    flock 9 || exit 1
    if cp -R /usr/share/faixalab-importador/. "$destination/" >>"$log" 2>&1 &&
       bash "$destination/iniciar.sh" --prepare "${1:-}" >>"$log" 2>&1 &&
       "$destination/.venv/bin/python" "$destination/activate.py" >>"$log" 2>&1; then
        printf '100\n'
    else
        exit 1
    fi
} 9>"$destination/.runtime/instalacao.lock" | zenity --progress --pulsate --no-cancel --auto-close --title='Importador FaixaLab' \
    --text='Preparando e iniciando o importador de áudio…'; then
    zenity --info --title='Importador FaixaLab ativo' \
        --text='Importador ativo. Volte ao FaixaLab e cole o link do YouTube.'
else
    zenity --error --title='Importador FaixaLab' \
        --text="Falha ao iniciar. O diagnóstico foi salvo em $log."
    exit 1
fi
