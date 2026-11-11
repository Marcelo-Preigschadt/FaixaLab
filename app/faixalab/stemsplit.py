"""Download the complete mix returned by StemSplit's YouTube job API."""
import json
import ipaddress
import os
import re
import time
from urllib.parse import urlsplit

import httpx

from . import storage
from .media import Cancelled, youtube_id

JOBS_URL = 'https://stemsplit.io/api/v1/youtube-jobs'
MAX_AUDIO_BYTES = 1024 ** 3


def configured():
    return bool(os.environ.get('STEMSPLIT_API_KEY', '').strip())


def _job_response(response):
    if response.status_code == 402:
        raise RuntimeError('A conta StemSplit não tem créditos suficientes para este vídeo.')
    if response.status_code in (401, 403):
        raise RuntimeError('A StemSplit recusou a chave do servidor. Confira a configuração da conta.')
    if not response.is_success:
        raise RuntimeError(f'A StemSplit recusou a importação (HTTP {response.status_code}).')
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError('A StemSplit retornou uma resposta inválida.') from None
    if not isinstance(payload, dict):
        raise RuntimeError('A StemSplit retornou uma resposta inválida.')
    return payload


def _save_audio(client, url, target, cancel):
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == 'https' and parsed.hostname and '.' in parsed.hostname
                 and not parsed.username and not parsed.password and parsed.port in (None, 443))
        if valid:
            try:
                ipaddress.ip_address(parsed.hostname)
            except ValueError:
                pass
            else:
                valid = False
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise RuntimeError('A StemSplit não retornou um endereço HTTPS válido para o áudio completo.')

    temporary = target.with_suffix('.part')
    try:
        with client.stream('GET', url) as response, temporary.open('wb') as output:
            if not response.is_success:
                raise RuntimeError(f'A StemSplit não conseguiu entregar o áudio completo (HTTP {response.status_code}).')
            if response.headers.get('content-type', '').startswith(('text/', 'application/json')):
                raise RuntimeError('A StemSplit retornou uma página no lugar do áudio.')
            size = 0
            for chunk in response.iter_bytes(1024 * 1024):
                if cancel.is_set():
                    raise Cancelled()
                size += len(chunk)
                if size > MAX_AUDIO_BYTES:
                    raise RuntimeError('O áudio recebido excedeu 1 GB.')
                output.write(chunk)
            if not size:
                raise RuntimeError('A StemSplit retornou um arquivo de áudio vazio.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def download_audio(url, cancel, progress):
    video_id = youtube_id(url)
    folder = storage.ROOT / 'stemsplit' / video_id
    folder.mkdir(parents=True, exist_ok=True)
    job_path = folder / 'job.json'
    audio = folder / 'audio.mp3'
    job = json.loads(job_path.read_text('utf-8')) if job_path.is_file() else {}
    if audio.is_file() and audio.stat().st_size:
        progress('Reutilizando o áudio salvo para este vídeo', 10)
        return audio, job.get('title') or 'Música do YouTube'

    api_key = os.environ.get('STEMSPLIT_API_KEY', '').strip()
    if not api_key:
        raise RuntimeError('A chave StemSplit precisa ser configurada no servidor.')
    headers = {'Authorization': f'Bearer {api_key}'}
    if cancel.is_set():
        raise Cancelled()

    try:
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            if not job:
                progress('Solicitando o áudio do vídeo à StemSplit', 2)
                response = client.post(JOBS_URL, headers=headers, json={'youtubeUrl': url})
                result = _job_response(response)
                job_id = result.get('id')
                if not isinstance(job_id, str) or not re.fullmatch(r'[\w-]{1,128}', job_id, re.ASCII):
                    raise RuntimeError('A StemSplit não retornou o identificador do pedido.')
                job = {'id': job_id, 'title': result.get('videoTitle')}
                temporary = job_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(job, ensure_ascii=False), 'utf-8')
                temporary.replace(job_path)

            deadline = time.monotonic() + 900
            job_url = f"{JOBS_URL}/{job['id']}"
            while time.monotonic() < deadline:
                if cancel.is_set():
                    raise Cancelled()
                response = client.get(job_url, headers=headers)
                if response.status_code != 429 and response.status_code < 500:
                    result = _job_response(response)
                    status = result.get('status')
                    if status == 'COMPLETED':
                        outputs = result.get('outputs')
                        download = outputs.get('fullAudio') if isinstance(outputs, dict) else None
                        address = download.get('url') if isinstance(download, dict) else None
                        if not isinstance(address, str) or not address:
                            raise RuntimeError('A StemSplit concluiu o pedido sem entregar o áudio completo.')
                        progress('Recebendo o áudio completo do vídeo', 10)
                        _save_audio(client, address, audio, cancel)
                        return audio, result.get('videoTitle') or job.get('title') or 'Música do YouTube'
                    if status in {'FAILED', 'CANCELLED', 'CANCELED'}:
                        job_path.unlink(missing_ok=True)
                        raise RuntimeError('A StemSplit não conseguiu importar este vídeo.')
                    progress('Aguardando o áudio do vídeo na StemSplit', 5)
                if cancel.wait(4):
                    raise Cancelled()
    except httpx.HTTPError:
        raise RuntimeError('A comunicação com a StemSplit foi interrompida. Tente novamente.') from None
    raise RuntimeError('A StemSplit ainda não concluiu o pedido. Tente novamente para retomar a consulta.')
