"""Start the desktop importer and wait until the browser can reach it."""

from http.client import HTTPConnection, HTTPException
from pathlib import Path
import subprocess
import sys
import time

from faixalab.local_import import ADDRESS, PORT, SITE


def importer_ready():
    connection = HTTPConnection(ADDRESS, PORT, timeout=0.5)
    try:
        connection.request('OPTIONS', '/import', headers={
            'Origin': SITE,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-faixalab-import',
        })
        with connection.getresponse() as response:
            return response.status == 204 and response.getheader('Access-Control-Allow-Origin') == SITE
    except (OSError, HTTPException):
        return False
    finally:
        connection.close()


def main():
    if importer_ready():
        return 0

    directory = Path(__file__).resolve().parent
    log = directory / '.runtime' / 'importador.log'
    command = [sys.executable, '-m', 'faixalab.local_import']
    if sys.platform == 'win32':
        command = [sys.executable, str(directory / 'importador.pyw')]
    with log.open('ab') as handle:
        process = subprocess.Popen(
            command, cwd=directory,
            stdin=subprocess.DEVNULL, stdout=handle, stderr=handle,
            start_new_session=True,
        )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if importer_ready():
            return 0
        if process.poll() is not None:
            break
        time.sleep(0.25)

    if process.poll() is None:
        process.kill()
        process.wait()
    print(f'Não foi possível ativar o importador. Consulte {log}.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
