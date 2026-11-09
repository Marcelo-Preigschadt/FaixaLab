"""Prepare a private JavaScript runtime; never runs during an audio import."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import tempfile
import urllib.request
import zipfile

from faixalab.youtube_support import APP_ROOT, check_support, find_runtime, runtime_info


def read_url(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'FaixaLab-YouTube-setup'})
    return urllib.request.urlopen(request, timeout=30)


def install_deno(app_root):
    machine = platform.machine().lower()
    architecture = {'amd64': 'x86_64', 'x86_64': 'x86_64',
                    'arm64': 'aarch64', 'aarch64': 'aarch64'}.get(machine)
    target = {'Windows': 'pc-windows-msvc', 'Linux': 'unknown-linux-gnu',
              'Darwin': 'apple-darwin'}.get(platform.system())
    if not target or not architecture:
        raise RuntimeError('Plataforma sem pacote Deno automático. Instale Deno 2.3+ ou Node 22+.')
    name = f'deno-{architecture}-{target}.zip'
    with read_url('https://api.github.com/repos/denoland/deno/releases/latest') as response:
        release = json.load(response)
    asset = next((a for a in release.get('assets', []) if a['name'] == name), None)
    if not asset:
        raise RuntimeError('Pacote Deno não encontrado para esta plataforma: ' + name)
    directory = Path(app_root) / '.runtime'
    directory.mkdir(parents=True, exist_ok=True)
    executable = 'deno.exe' if platform.system() == 'Windows' else 'deno'
    with tempfile.TemporaryDirectory(prefix='deno-setup-', dir=directory) as temporary:
        archive = Path(temporary) / name
        digest = hashlib.sha256()
        total = 0
        with read_url(asset['browser_download_url']) as response, archive.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 200 * 1024 * 1024:
                    raise RuntimeError('O pacote Deno excedeu o tamanho esperado.')
                digest.update(chunk)
                output.write(chunk)
        if total != asset['size']:
            raise RuntimeError('O download do Deno ficou incompleto.')
        expected = asset.get('digest')
        if expected and expected != 'sha256:' + digest.hexdigest():
            raise RuntimeError('Falha na verificação SHA-256 do Deno.')
        binary = Path(temporary) / executable
        with zipfile.ZipFile(archive) as package, package.open(executable) as source, binary.open('wb') as output:
            shutil.copyfileobj(source, output)
        binary.chmod(0o700)
        if runtime_info('deno', binary) is None:
            raise RuntimeError('O Deno baixado não executa nesta máquina ou é incompatível.')
        os.replace(binary, directory / executable)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Somente validar; não baixar runtime')
    args = parser.parse_args()
    try:
        if not args.check and find_runtime() is None:
            print('Preparando o runtime JavaScript do YouTube...', flush=True)
            install_deno(APP_ROOT)
        support = check_support()
        print(json.dumps(support, ensure_ascii=False, indent=2))
    except Exception as exc:
        print('Falha ao preparar o YouTube: ' + str(exc), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
