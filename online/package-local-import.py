"""Package the import-only desktop and Android clients."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
NAME = 'FaixaLab_Importador'
CLIENT_FILES = ['faixalab/media.py', 'faixalab/local_import.py',
                'faixalab/youtube_support.py', 'prepare_youtube.py', 'TERCEIROS.md']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with ZipFile(args.output, 'w', ZIP_DEFLATED) as package:
        for path in sorted((ROOT / 'online' / 'local-import').iterdir()):
            if path.is_file():
                package.write(path, f'{NAME}/{path.name}')
        for path in CLIENT_FILES:
            package.write(ROOT / 'app' / path, f'{NAME}/{path}')
        package.writestr(f'{NAME}/faixalab/__init__.py', '"""FaixaLab import client."""\n')


if __name__ == '__main__':
    main()
