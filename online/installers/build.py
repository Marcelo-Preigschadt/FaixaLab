"""Build installers from the existing FaixaLab import-only package."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ONLINE = HERE.parent
ROOT = ONLINE.parent
NAME = 'FaixaLab_Importador'
VERSION = '1.2.0'


def stage_client(directory):
    archive = directory / (NAME + '.zip')
    subprocess.run([sys.executable, str(ONLINE / 'package-local-import.py'), str(archive)], check=True)
    with ZipFile(archive) as package:
        package.extractall(directory)
    client = directory / NAME
    for unused in ['iniciar-android.sh', 'LEIA_PRIMEIRO.txt']:
        (client / unused).unlink()
    return client


def windows(client, output):
    (client / 'iniciar.sh').unlink()
    switch = '/' if os.name == 'nt' else '-'
    subprocess.run([
        'makensis', f'{switch}WX', f'{switch}V3',
        f'{switch}DPAYLOAD={client}', f'{switch}DOUTPUT={output}',
        f'{switch}DLAUNCHER={HERE / "windows-launcher.pyw"}', str(HERE / 'windows.nsi'),
    ], check=True)


def windows_desktop(output):
    subprocess.run([
        'makensis', '-WX', '-V3', f'-DOUTPUT={output}', f'-DBOOTSTRAP={HERE / "windows-desktop.ps1"}',
        str(HERE / 'windows-desktop.nsi'),
    ], check=True)


def linux(client, output):
    for unused in ['INICIAR.bat', 'INSTALAR.bat', 'importador.pyw']:
        (client / unused).unlink()
    package = client.parent / 'deb'
    metadata = package / 'DEBIAN'
    metadata.mkdir(parents=True)
    (metadata / 'control').write_text(
        'Package: faixalab-importador\nVersion: ' + VERSION + '\nArchitecture: all\n'
        'Maintainer: FaixaLab <faixalablab@gmail.com>\n'
        'Depends: bash, python3 (>= 3.10), python3-venv, ffmpeg, zenity\n'
        'Section: sound\nPriority: optional\n'
        'Description: Importador de áudio local para o FaixaLab\n'
    )
    share = package / 'usr/share'
    share.mkdir(parents=True)
    shutil.copytree(client, share / 'faixalab-importador')
    bin_dir = package / 'usr/bin'
    bin_dir.mkdir()
    launcher = bin_dir / 'faixalab-importador'
    shutil.copyfile(HERE / 'linux-start.sh', launcher)
    launcher.chmod(0o755)
    applications = share / 'applications'
    applications.mkdir()
    shutil.copyfile(HERE / 'faixalab-importador.desktop', applications / 'faixalab-importador.desktop')
    icons = share / 'icons/hicolor/scalable/apps'
    icons.mkdir(parents=True)
    shutil.copyfile(ROOT / 'app/faixalab/web/icon.svg', icons / 'faixalab-importador.svg')
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(package), str(output)], check=True)


def macos(client, output):
    for unused in ['INICIAR.bat', 'INSTALAR.bat', 'importador.pyw', 'iniciar.sh']:
        (client / unused).unlink()
    payload = client.parent / 'macos'
    payload.mkdir()
    app = payload / 'Importador FaixaLab.app'
    subprocess.run(['osacompile', '-o', str(app), str(HERE / 'macos-launcher.applescript')], check=True)
    resources = app / 'Contents/Resources'
    launcher = resources / 'Preparar.sh'
    shutil.copyfile(HERE / 'macos-start.sh', launcher)
    launcher.chmod(0o755)
    shutil.copytree(client, resources / 'payload')
    subprocess.run([
        'pkgbuild', '--root', str(payload), '--install-location', '/Applications',
        '--identifier', 'io.github.marcelo-preigschadt.faixalab-importador',
        '--version', VERSION, str(output),
    ], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('target', choices=['windows', 'windows-desktop', 'linux', 'macos'])
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.target == 'windows-desktop':
        windows_desktop(output)
        return
    with tempfile.TemporaryDirectory(prefix='faixalab-package-') as directory:
        client = stage_client(Path(directory))
        globals()[args.target](client, output)


if __name__ == '__main__':
    main()
