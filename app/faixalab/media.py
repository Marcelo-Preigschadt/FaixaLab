from pathlib import Path
from urllib.parse import urlparse, parse_qs
import os
import re
import shutil
import subprocess
import threading
import time
import numpy as np


class Cancelled(Exception):
    pass


def ffmpeg_executable():
    known = os.environ.get('FFMPEG_BINARY') or shutil.which('ffmpeg')
    if known:
        return known
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_process(args, cancel, on_line=None, env=None, cwd=None, on_tick=None):
    if cancel.is_set():
        raise Cancelled()
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace',
                               creationflags=flags, env=env, cwd=cwd)
    tail, callback_errors = [], []
    started = last_output = time.monotonic()

    def consume():
        nonlocal last_output
        for line in process.stdout:
            last_output = time.monotonic()
            tail.append(line.strip())
            del tail[:-25]
            if on_line and not callback_errors:
                try:
                    on_line(line)
                except BaseException as exc:
                    callback_errors.append(exc)

    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    try:
        last_tick = started - 1
        while process.poll() is None:
            if cancel.wait(.2):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise Cancelled()
            if callback_errors:
                raise callback_errors[0]
            now = time.monotonic()
            if on_tick and now - last_tick >= 1:
                on_tick({'elapsed_seconds': round(now - started, 1),
                         'last_output_seconds': round(now - last_output, 1)})
                last_tick = now
        reader.join(timeout=5)
        if callback_errors:
            raise callback_errors[0]
        if process.returncode:
            raise RuntimeError('\n'.join(tail)[-4000:] or 'O processo de áudio falhou.')
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        reader.join(timeout=1)
        process.stdout.close()


def youtube_id(url):
    p = urlparse(url.strip())
    host = (p.hostname or '').lower()
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Use um link HTTPS de um vídeo do YouTube.')
    if host in {'youtu.be', 'www.youtu.be'}:
        identifier = p.path.strip('/').split('/')[0]
    elif host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'}:
        if p.path == '/watch':
            identifier = parse_qs(p.query).get('v', [''])[0]
        elif p.path.startswith(('/shorts/', '/live/', '/embed/')):
            identifier = p.path.split('/')[2]
        else:
            identifier = ''
    else:
        identifier = ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier):
        raise ValueError('O link precisa apontar para um único vídeo do YouTube.')
    return identifier


def download_youtube(url, folder, cancel, progress):
    from yt_dlp import YoutubeDL
    identifier = youtube_id(url)

    def hook(data):
        if cancel.is_set():
            raise Cancelled()
        if data.get('status') == 'downloading':
            total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            if total:
                progress('Baixando áudio do YouTube', min(10, 2 + 8 * data.get('downloaded_bytes', 0) / total))

    opts = {'format': 'bestaudio[acodec=opus]/bestaudio[acodec^=mp4a]/best[acodec^=mp4a]',
            'ffmpeg_location': ffmpeg_executable(),
            'noplaylist': True, 'quiet': True,
            'no_warnings': True, 'outtmpl': str(folder / 'youtube.%(ext)s'),
            'socket_timeout': 20, 'retries': 2, 'fragment_retries': 2,
            'progress_hooks': [hook], 'cachedir': False,
            'compat_opts': {'no-certifi'},
            'max_filesize': 1024 ** 3}
    deno = shutil.which('deno') or (str(Path(os.environ['FAIXALAB_DENO'])) if os.environ.get('FAIXALAB_DENO') else None)
    node = shutil.which('node')
    if deno:
        opts['js_runtimes'] = {'deno': {'path': deno}}
    elif node:
        opts['js_runtimes'] = {'node': {'path': node}}
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info('https://www.youtube.com/watch?v=' + identifier, download=True)
            filename = Path(ydl.prepare_filename(info))
    except Cancelled:
        raise
    except Exception as exc:
        if cancel.is_set():
            raise Cancelled() from exc
        raise RuntimeError('Não foi possível obter o áudio deste vídeo. Verifique se o link é público e se o YouTube permite o acesso nesta conexão. Detalhe: ' + str(exc)[-1000:]) from exc
    if not filename.is_file() or filename.stat().st_size == 0:
        raise RuntimeError('O YouTube não retornou um arquivo de áudio utilizável.')
    with filename.open('rb') as downloaded:
        prefix = downloaded.read(512).lstrip().lower()
    if prefix.startswith((b'<html', b'<!doctype html')):
        filename.unlink(missing_ok=True)
        raise RuntimeError('Esta conexão retornou uma página de bloqueio no lugar do áudio do YouTube. Tente importar o MP3 ou usar outra conexão disponível.')
    return filename, info.get('title') or 'Música do YouTube'


def decode_audio(source, target, cancel):
    run_process([ffmpeg_executable(), '-v', 'error', '-nostdin', '-y',
                 '-protocol_whitelist', 'file,pipe', '-i', str(source), '-vn',
                 '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le', str(target)], cancel)
    import soundfile as sf
    info = sf.info(target)
    if info.duration < .2:
        raise ValueError('O arquivo não contém áudio suficiente para análise.')
    return info.duration


def waveform(path, count=900):
    import soundfile as sf
    data, _ = sf.read(path, dtype='float32', always_2d=True)
    mono = np.sqrt(np.mean(data * data, axis=1))
    chunks = np.array_split(mono, min(count, len(mono)))
    peak = max(float(np.max(np.abs(mono))), 1e-6)
    return [round(float(np.sqrt(np.mean(x * x))) / peak, 4) for x in chunks]
