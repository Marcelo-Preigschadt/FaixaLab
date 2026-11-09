"""YouTube prerequisites, independent of the launcher and current directory."""
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


APP_ROOT = Path(__file__).resolve().parents[1]
MIN_YTDLP = (2026, 10, 26)
MIN_RUNTIMES = {'deno': (2, 3, 0), 'node': (22, 0, 0)}
REPAIR = ('Feche o FaixaLab e execute ATUALIZAR_YOUTUBE.bat na pasta do aplicativo '
          '(Linux: bash cloud/atualizar_youtube.sh).')


class YouTubeSupportError(RuntimeError):
    pass


def clean_message(value):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', str(value))
    return ''.join(c for c in text if c >= ' ' or c in '\n\t').strip()[-1500:]


def _version(value):
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', value)
    return tuple(map(int, match.groups())) if match else (0, 0, 0)


def runtime_info(kind, path):
    if not path or not Path(path).is_file():
        return None
    try:
        result = subprocess.run([str(path), '--version'], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=5,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = _version(result.stdout.splitlines()[0] if result.stdout else '')
    if result.returncode or version < MIN_RUNTIMES[kind]:
        return None
    return {'name': kind, 'path': str(Path(path).resolve()),
            'version': '.'.join(map(str, version))}


def find_runtime(app_root=None):
    root = Path(app_root) if app_root is not None else APP_ROOT
    executable = 'deno.exe' if os.name == 'nt' else 'deno'
    # A global, outdated Deno must not shadow the private supported runtime.
    candidates = [('deno', os.environ.get('FAIXALAB_DENO')),
                  ('deno', root / '.runtime' / executable),
                  ('deno', shutil.which('deno')),
                  ('node', os.environ.get('FAIXALAB_NODE')),
                  ('node', shutil.which('node'))]
    seen = set()
    for kind, path in candidates:
        key = str(path)
        if not path or key in seen:
            continue
        seen.add(key)
        info = runtime_info(kind, path)
        if info:
            return info
    return None


def distribution_versions():
    versions = {}
    for name in ('yt-dlp', 'yt-dlp-ejs'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def check_support(app_root=None):
    versions = distribution_versions()
    if _version(versions['yt-dlp'] or '') < MIN_YTDLP:
        raise YouTubeSupportError('O suporte ao YouTube está ausente ou desatualizado. ' + REPAIR)
    if not versions['yt-dlp-ejs']:
        raise YouTubeSupportError('O componente JavaScript do YouTube (EJS) não está instalado. ' + REPAIR)
    # pip's default extra pins the matching EJS version. Detect environments
    # that were subsequently modified without updating that companion package.
    for requirement in importlib.metadata.requires('yt-dlp') or []:
        match = re.match(r'yt-dlp-ejs\s*==\s*([^;\s]+)', requirement)
        if match and versions['yt-dlp-ejs'] != match[1]:
            raise YouTubeSupportError('Os componentes yt-dlp e EJS estão incompatíveis. ' + REPAIR)
    runtime = find_runtime(app_root)
    if runtime is None:
        raise YouTubeSupportError('Falta um runtime JavaScript compatível para importar do YouTube '
                                  '(Deno 2.3+ ou Node 22+). ' + REPAIR)
    return {**versions, 'runtime': runtime}


class DownloadLog:
    def __init__(self):
        self.messages = []

    def debug(self, message):
        pass

    def warning(self, message):
        self.messages.append(clean_message(message))
        del self.messages[:-10]

    error = warning


def save_diagnostic(folder, identifier, support, messages, error=None):
    report = {'video_id': identifier, **support, 'messages': messages,
              'error': clean_message(error) if error else None}
    try:
        (Path(folder) / 'youtube-diagnostico.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        pass  # A diagnostic must never mask the original download failure.


def download_error(error):
    detail = clean_message(error)
    if any(reason in detail.lower() for reason in ('private video', 'video has been removed',
                                                  'sign in', 'age-restricted', 'not available in your country')):
        return 'O YouTube restringiu o acesso a este vídeo. Detalhe: ' + detail
    if 'This video is not available' in detail or 'Video unavailable' in detail:
        explanation = ('Essa resposta pode indicar incompatibilidade do extrator ou restrição '
                       'de acesso; ela não confirma que o vídeo foi removido. ')
    else:
        explanation = ''
    return 'Não foi possível importar o áudio do YouTube. ' + explanation + REPAIR + ' Detalhe: ' + detail
