"""Launch the Windows import assistant without opening a console window."""
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from faixalab.local_import import main

if __name__ == '__main__':
    log = Path(__file__).resolve().parent / '.runtime' / 'importador.log'
    with log.open('w', encoding='utf-8') as handle:
        with redirect_stdout(handle), redirect_stderr(handle):
            raise SystemExit(main())
