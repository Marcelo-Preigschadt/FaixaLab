"""Client for a FaixaLab audio source hosted separately from the separator."""
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import httpx

from .media import Cancelled

LOOPBACK = {'localhost', '127.0.0.1', '::1'}


def settings():
    bridge = os.environ.get('FAIXALAB_AUDIO_BRIDGE_FILE')
    if bridge:
        state = Path(bridge)
        try:
            key = state.read_text('utf-8').strip()
            if time.time() - state.stat().st_mtime < 75 and re.fullmatch(r'[A-Za-z0-9_-]{32,128}', key):
                return 'http://127.0.0.1:7871', key
        except (OSError, ValueError):
            pass
        raise ValueError('Conecte o servidor de áudio do FaixaLab no Windows para importar o link.')

    address = os.environ.get('FAIXALAB_AUDIO_SOURCE_URL', '').strip().rstrip('/')
    if not address:
        return None
    key = os.environ.get('FAIXALAB_AUDIO_SOURCE_KEY', '').strip()
    if not key:
        raise ValueError('Configure FAIXALAB_AUDIO_SOURCE_KEY para conectar a API de áudio.')
    parsed = urlsplit(address)
    loopback = parsed.hostname in LOOPBACK
    if (not parsed.hostname or parsed.port == 0 or parsed.username is not None or parsed.password is not None or parsed.path or parsed.query
            or parsed.fragment or not (parsed.scheme == 'https' or parsed.scheme == 'http' and loopback)):
        raise ValueError('Configure a origem HTTPS da API de áudio. HTTP é aceito em localhost.')
    return address, key


def _job(response):
    if not response.is_success:
        raise RuntimeError(f'A API de áudio recusou a solicitação (HTTP {response.status_code}).')
    try:
        job = response.json()
    except ValueError:
        raise RuntimeError('A API de áudio retornou uma resposta inválida.') from None
    if not isinstance(job, dict):
        raise RuntimeError('A API de áudio retornou uma resposta inválida.')
    return job


def download_audio(url, folder, cancel, progress):
    configuration = settings()
    if not configuration:
        raise RuntimeError('Configure o endereço da API de áudio no servidor FaixaLab.')
    address, key = configuration
    if cancel.is_set():
        raise Cancelled()
    target = folder / 'youtube-source.audio'
    temporary = target.with_suffix('.part')
    try:
        with httpx.Client(base_url=address, headers={'Authorization': f'Bearer {key}'},
                          timeout=30, follow_redirects=False, trust_env=urlsplit(address).hostname not in LOOPBACK) as client:
            job = _job(client.post('/v1/youtube-jobs', json={'url': url}))
            identifier = job.get('id')
            if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier):
                raise RuntimeError('A API de áudio não retornou um identificador válido.')
            job_path = f'/v1/youtube-jobs/{identifier}'
            deadline = time.monotonic() + 900
            while job.get('status') in {'queued', 'processing'}:
                progress(job.get('stage') or 'Aguardando a API de áudio', 5)
                if cancel.wait(2):
                    raise Cancelled()
                if time.monotonic() >= deadline:
                    raise RuntimeError('A API de áudio ainda está processando o vídeo. Tente novamente para consultar o pedido.')
                job = _job(client.get(job_path))
            if job.get('status') != 'ready':
                raise RuntimeError(job.get('error') or 'A API de áudio não conseguiu importar o vídeo.')
            progress('Recebendo o áudio da API FaixaLab', 10)
            with client.stream('GET', job_path + '/audio') as response, temporary.open('wb') as output:
                if not response.is_success:
                    raise RuntimeError(f'A API de áudio não entregou o arquivo (HTTP {response.status_code}).')
                size = 0
                for chunk in response.iter_bytes(1024 * 1024):
                    if cancel.is_set():
                        raise Cancelled()
                    size += len(chunk)
                    if size > 1024 ** 3:
                        raise RuntimeError('O áudio recebido excedeu 1 GB.')
                    output.write(chunk)
                if not size:
                    raise RuntimeError('A API de áudio retornou um arquivo vazio.')
            temporary.replace(target)
            return target, job.get('title') or 'Música do YouTube'
    except httpx.HTTPError:
        raise RuntimeError('Não foi possível se comunicar com a API de áudio FaixaLab.') from None
    finally:
        temporary.unlink(missing_ok=True)
