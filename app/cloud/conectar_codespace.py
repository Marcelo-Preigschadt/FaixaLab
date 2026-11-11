"""Serve audio from an existing FaixaLab installation through a private SSH tunnel."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
import time
from urllib.request import urlopen

SOURCE_API_URL = ('https://raw.githubusercontent.com/Marcelo-Preigschadt/FaixaLab/'
                  'a1dc7e1f0520bf32f96c5fc11c8910c8265b70cc/app/faixalab/source_api.py')
SOURCE_API_SHA256 = '7ea83af79e87cd4e6732571808591d9fcb30788b263536d284b7edfb59582ceb'
CODESPACE_REPOSITORY = 'Marcelo-Preigschadt/mvlab'

REGISTER_BRIDGE = r'''
set -eu
umask 077
IFS= read -r key
case "$key" in ''|*[!A-Za-z0-9_-]*) exit 1 ;; esac
[ "${#key}" -ge 32 ]
directory=/workspaces/.faixalab-data
mkdir -p "$directory"
state="$directory/audio-bridge.key"
temporary=$(mktemp "$directory/.audio-bridge.XXXXXXXX")
cleanup() {
  rm -f -- "$temporary"
  if [ "$(cat "$state" 2>/dev/null || true)" = "$key" ]; then rm -f -- "$state"; fi
}
trap cleanup EXIT
trap 'exit 0' HUP INT TERM
if ! printf 'Authorization: Bearer %s\n' "$key" |
  curl --noproxy 127.0.0.1 --max-time 8 -fsS -H @- http://127.0.0.1:7871/v1/health >/dev/null; then
  printf 'O Codespace não conseguiu acessar a API no Windows.\n' >&2
  exit 1
fi
printf '%s\n' "$key" > "$temporary"
mv -f -- "$temporary" "$state"
printf 'FaixaLab conectado. Cole o link na página online.\n'
while IFS= read -r -t 75 heartbeat; do
  [ "$heartbeat" = 'ok' ] && [ "$(cat "$state" 2>/dev/null || true)" = "$key" ] || exit 0
  touch "$state"
done
'''


def load_source_api(directory):
    with urlopen(SOURCE_API_URL, timeout=20) as response:
        code = response.read(100_000)
    if hashlib.sha256(code).hexdigest() != SOURCE_API_SHA256:
        raise RuntimeError('O código da API de áudio não passou na verificação de integridade.')
    path = directory / 'source_api.py'
    path.write_bytes(code)
    spec = importlib.util.spec_from_file_location('faixalab.source_api', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_codespace(gh):
    result = subprocess.run([gh, 'codespace', 'list', '-R', CODESPACE_REPOSITORY,
                             '--json', 'name,state'], capture_output=True, encoding='utf-8', timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'O GitHub CLI não conseguiu listar os Codespaces.')
    spaces = json.loads(result.stdout)
    active = [space['name'] for space in spaces if space['state'] == 'Available']
    if len(active) == 1:
        return active[0]
    if len(spaces) == 1:
        return spaces[0]['name']
    if not spaces:
        raise RuntimeError(f'Não há Codespaces de {CODESPACE_REPOSITORY} nesta conta.')
    raise RuntimeError('Informe --codespace com o nome de um dos Codespaces: ' + ', '.join(
        space['name'] for space in spaces))


def connect(gh, codespace, port, key, server):
    command = [gh, 'codespace', 'ssh', '-c', codespace, '--', '-T',
               '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=25',
               '-o', 'ServerAliveCountMax=2', '-R', f'127.0.0.1:7871:127.0.0.1:{port}',
               'bash -c ' + shlex.quote(REGISTER_BRIDGE)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        process.stdin.write((key + '\n').encode('ascii'))
        process.stdin.flush()
        while process.poll() is None and not server.should_exit:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                if not server.should_exit:
                    process.stdin.write(b'ok\n')
                    process.stdin.flush()
    except BrokenPipeError:
        pass
    finally:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait()
    if process.returncode:
        raise RuntimeError('A conexão SSH falhou. Confira o acesso do GitHub CLI ao Codespace.')


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description='Conecta a API de áudio local ao FaixaLab online.')
    parser.add_argument('--codespace')
    parser.add_argument('--app-dir', type=Path, default=Path.cwd())
    parser.add_argument('--port', type=int, default=7870)
    args = parser.parse_args()
    app_dir = args.app_dir.resolve()
    if not (app_dir / 'faixalab' / 'media.py').is_file():
        parser.error('Execute na pasta do FaixaLab ou informe --app-dir.')
    gh = shutil.which('gh')
    if not gh:
        parser.error('Instale o GitHub CLI em https://cli.github.com/ e execute gh auth login --web --scopes codespace.')
    if subprocess.run([gh, 'auth', 'status', '--hostname', 'github.com'], capture_output=True).returncode:
        parser.error('Execute gh auth login --web --scopes codespace com a conta do Codespace.')
    codespace = args.codespace or find_codespace(gh)

    sys.path.insert(0, str(app_dir))
    from faixalab.youtube_support import check_support

    check_support()
    key = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory() as temporary:
        module = load_source_api(Path(temporary))
        cache = Path.home() / '.faixalab-audio-source'
        server = uvicorn.Server(uvicorn.Config(module.create_app(cache, key), host='127.0.0.1', port=args.port,
                                               log_level='warning', access_log=False))
        worker = Thread(target=server.run, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + 8
            while not server.started and worker.is_alive() and time.monotonic() < deadline:
                time.sleep(.05)
            if not server.started:
                raise RuntimeError(f'A API de áudio local não iniciou na porta {args.port}.')
            print('Conectando a API de áudio local ao Codespace…', flush=True)
            connect(gh, codespace, args.port, key, server)
        except KeyboardInterrupt:
            print('\nConexão encerrada.', flush=True)
        finally:
            server.should_exit = True
            worker.join(timeout=15)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
