"""Loopback-only audio import for the FaixaLab website."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from urllib.parse import quote

from .media import Cancelled, download_youtube, ffmpeg_executable, youtube_id
from .youtube_support import COOKIE_SECRET, check_support

ADDRESS = '127.0.0.1'
PORT = 17861
SITE = 'https://marcelo-preigschadt.github.io'
VERSION = '1'
MAX_BODY = 8192
MAX_AUDIO = 128 * 1024 ** 2
IMPORT_TIMEOUT = 180
AUDIO_TYPES = {
    '.webm': 'audio/webm', '.m4a': 'audio/mp4', '.mp4': 'video/mp4',
    '.opus': 'audio/opus', '.ogg': 'audio/ogg', '.aac': 'audio/aac',
    '.mp3': 'audio/mpeg', '.flac': 'audio/flac', '.wav': 'audio/wav',
}


class ImportRequest(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(20)
        super().setup()

    def allowed(self):
        return (self.headers.get_all('Host') == [f'{ADDRESS}:{self.server.server_port}']
                and self.headers.get_all('Origin') == [SITE])

    def respond(self, status, media_type, length, **headers):
        self.send_response(status)
        if self.allowed():
            self.send_header('Access-Control-Allow-Origin', SITE)
            self.send_header('Access-Control-Expose-Headers', 'X-FaixaLab-Filename')
        self.send_header('Content-Type', media_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Vary', 'Origin')
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()

    def json(self, status, **data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.respond(status, 'application/json; charset=utf-8', len(body))
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not self.allowed() or self.path != '/import':
            self.json(403, detail='Origem não autorizada.')
            return
        if self.headers.get('Access-Control-Request-Method') != 'POST':
            self.json(405, detail='Método não permitido.')
            return
        self.respond(204, 'text/plain', 0, **{
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type, X-FaixaLab-Import',
            'Access-Control-Allow-Private-Network': 'true',
        })

    def do_POST(self):
        if not self.allowed() or self.headers.get_all('X-FaixaLab-Import') != [VERSION]:
            self.json(403, detail='Origem ou versão do importador não autorizada.')
            return
        if self.path != '/import':
            self.json(404, detail='Rota desconhecida.')
            return
        if self.headers.get_content_type() != 'application/json':
            self.json(415, detail='Envie a solicitação no formato JSON.')
            return
        lengths = self.headers.get_all('Content-Length', [])
        if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()
                or len(lengths[0]) > 4 or int(lengths[0]) > MAX_BODY
                or self.headers.get_all('Transfer-Encoding')):
            self.json(413, detail='Solicitação inválida ou grande demais.')
            return
        try:
            data = json.loads(self.rfile.read(int(lengths[0])))
            url = data.get('url') if isinstance(data, dict) else None
            if not isinstance(url, str) or len(url) > 2000:
                raise ValueError('Cole um link válido do YouTube.')
            identifier = youtube_id(url)
        except (TimeoutError, UnicodeError, json.JSONDecodeError):
            self.json(400, detail='Não foi possível ler o link enviado.')
            return
        except ValueError as exc:
            self.json(422, detail=str(exc))
            return
        if not self.server.import_lock.acquire(blocking=False):
            self.json(429, detail='Este aparelho já está importando outro vídeo.')
            return
        try:
            self.import_audio(identifier)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            self.server.import_lock.release()

    def log_message(self, format, *args):
        # Event logs must not echo arbitrary requests or local paths.
        return

    def import_audio(self, identifier):
        with tempfile.TemporaryDirectory(prefix='FaixaLab-import-') as temporary:
            cancel = threading.Event()
            timer = threading.Timer(IMPORT_TIMEOUT, cancel.set)
            timer.daemon = True
            timer.start()
            try:
                source, title = download_youtube(
                    f'https://www.youtube.com/watch?v={identifier}', Path(temporary),
                    cancel, lambda *_: None, max_bytes=MAX_AUDIO, max_duration=1800,
                )
                if cancel.is_set():
                    raise Cancelled()
                suffix = source.suffix.lower()
                size = source.stat().st_size
                if suffix not in AUDIO_TYPES or not 0 < size <= MAX_AUDIO:
                    self.json(422, detail='O áudio recebido excede 128 MiB ou está em formato incompatível.')
                    return
                subprocess.run([
                    ffmpeg_executable(), '-v', 'error', '-xerror', '-nostdin',
                    '-protocol_whitelist', 'file,pipe', '-i', str(source),
                    '-map', '0:a:0', '-f', 'null', '-',
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=60, check=True)
            except (Cancelled, subprocess.TimeoutExpired):
                self.json(504, detail='A importação neste aparelho excedeu o tempo limite.')
                return
            except subprocess.CalledProcessError:
                self.json(422, detail='O arquivo recebido não contém áudio decodificável.')
                return
            except RuntimeError as exc:
                self.json(502, detail=str(exc))
                return
            except OSError:
                self.json(500, detail='Falha ao abrir o arquivo temporário ou executar o FFmpeg.')
                return
            finally:
                timer.cancel()
            filename = ''.join(c for c in title if c >= ' ' and c not in '/\\:*?"<>|')[:140].strip()
            self.respond(200, AUDIO_TYPES[suffix], size,
                         **{'X-FaixaLab-Filename': quote((filename or identifier) + suffix, safe='')})
            with source.open('rb') as handle:
                shutil.copyfileobj(handle, self.wfile)


class ImportServer(ThreadingHTTPServer):
    def __init__(self, address=(ADDRESS, PORT)):
        self.import_lock = threading.Lock()
        super().__init__(address, ImportRequest)


def main():
    os.environ.pop(COOKIE_SECRET, None)
    try:
        check_support()
        ffmpeg_executable()
        with ImportServer() as server:
            print('Importador FaixaLab pronto. Volte ao site e mantenha esta janela aberta.', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, OSError, ImportError) as exc:
        print(f'Não foi possível iniciar o Importador FaixaLab. {exc}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
