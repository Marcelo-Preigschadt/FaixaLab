#!/bin/sh
set -eu
destination="${XDG_DATA_HOME:-$HOME/.local/share}/FaixaLab/Importador"
mkdir -p "$destination"
cp -R /usr/share/faixalab-importador/. "$destination/"
exec bash "$destination/iniciar.sh" "$@"
