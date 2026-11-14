#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
if [[ -z "${TERMUX_VERSION:-}" ]]; then
  echo 'Execute este instalador no Termux para Android.'
  exit 1
fi

install_dir="$HOME/.local/share/FaixaLab"
mkdir -p "$install_dir" "$PREFIX/bin"
workspace="$(mktemp -d)"
trap 'rm -rf -- "$workspace"' EXIT
pkg install -y curl unzip
curl -fL --retry 2 --max-time 120 https://marcelo-preigschadt.github.io/FaixaLab/FaixaLab_Importador.zip -o "$workspace/client.zip"
unzip -oq "$workspace/client.zip" -d "$install_dir"
cat > "$PREFIX/bin/faixalab" <<'LAUNCHER'
#!/data/data/com.termux/files/usr/bin/bash
exec bash "$HOME/.local/share/FaixaLab/FaixaLab_Importador/iniciar-android.sh" "$@"
LAUNCHER
chmod 755 "$PREFIX/bin/faixalab"
echo 'Da próxima vez, abra o Termux e execute faixalab.'
faixalab
