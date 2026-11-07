"""Real MP3 -> Demucs -> chords -> Whisper -> download test. No engine mocks."""
from pathlib import Path
import json
import subprocess
import sys
import time
import io
import zipfile
import threading
import urllib.request
import os
import numpy as np
import soundfile as sf
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = Path(os.environ.get('FAIXALAB_TEST_DATA_DIR', ROOT.parent / 'faixalab_test_data'))
DATA.mkdir(exist_ok=True)
if not (DATA / 'jfk.flac').exists():
    urllib.request.urlretrieve('https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/tests/data/jfk.flac', DATA / 'jfk.flac')
URL = 'http://127.0.0.1:8767'
os_environment = __import__('os').environ
os_environment['FAIXALAB_DATA_DIR'] = str(DATA)
os_environment['HF_HUB_DISABLE_XET'] = '1'
import uvicorn
from faixalab.app import app
server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8767, access_log=False, log_level='error'))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
for _ in range(100):
    if server.started:
        break
    time.sleep(.05)
speech, sr = sf.read(DATA / 'jfk.flac', dtype='float32', always_2d=True)
duration = len(speech) / sr
t = np.arange(len(speech)) / sr
guitar = np.zeros(len(speech))
for index, midis in enumerate([[48, 52, 55], [45, 48, 52], [41, 45, 48], [43, 47, 50]]):
    for onset in np.arange(index * duration / 4, (index + 1) * duration / 4, .5):
        elapsed = np.maximum(0, t - onset)
        envelope = np.where((t >= onset) & (t < onset + .9), np.exp(-elapsed * 5), 0)
        for midi in midis:
            f = 440 * 2 ** ((midi - 69) / 12)
            guitar += envelope * (np.sin(2*np.pi*f*t) + .3*np.sin(4*np.pi*f*t)) / 12
mixed = speech * .7 + guitar[:, None] * .27
mixed /= max(1, np.max(np.abs(mixed)) / .92)
sf.write(DATA / 'validation.wav', mixed, sr, subtype='PCM_16')
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(DATA / 'validation.wav'), '-codec:a', 'libmp3lame', '-q:a', '2', str(DATA / 'validation.mp3')], check=True)
client = httpx.Client(base_url=URL, timeout=120, trust_env=False)
assert client.get('/api/health').json()['status'] == 'ok'
if len(sys.argv) > 1:
    identifier = sys.argv[1]
    response = client.post(f'/api/projects/{identifier}/retry/lyrics')
    response.raise_for_status()
else:
    with (DATA / 'validation.mp3').open('rb') as f:
        response = client.post('/api/import/file', files={'file': ('validacao_musical.mp3', f, 'audio/mpeg')}, data={'options': json.dumps({'stems': 6, 'split_guitars': False, 'quality': 'quality', 'language': '', 'lyrics_model': 'small', 'lyrics': True})})
    response.raise_for_status()
    identifier = response.json()['id']
print('PROJECT', identifier, flush=True)
started = time.monotonic()
last = None
progress_events = []
while time.monotonic() - started < 600:
    p = client.get('/api/projects/' + identifier).json()
    marker = (p['stage'], p['progress'])
    if marker != last:
        print(p['status'], marker, flush=True)
        progress_events.append({'stage':p['stage'],'progress':p['progress']})
        last = marker
    if p['status'] not in {'queued', 'processing'}:
        break
    time.sleep(1)
assert p['status'] == 'ready', (p['status'], p.get('error'), p.get('warnings'))
assert len(p['stems']) == 6
assert p['chord_analysis']['engine'] == 'BTC + CQT + semi-Markov'
assert p['chord_analysis']['version'] == '0.3.0'
assert p['chords'], 'No audio chord events were returned'
assert len(' '.join(x['text'] for x in p['lyrics']).split()) >= 3, 'No real speech transcription'
audio_checks = []
for stem in p['stems']:
    r = client.get(f'/api/projects/{identifier}/audio/{stem["name"]}', headers={'Range': 'bytes=0-255'})
    assert r.status_code == 206 and len(r.content) == 256
    audio_checks.append(stem['name'])
export = client.get(f'/api/projects/{identifier}/export/zip')
export.raise_for_status()
with zipfile.ZipFile(io.BytesIO(export.content)) as z:
    assert z.testzip() is None
    assert len([n for n in z.namelist() if n.endswith('.wav')]) == 6
    assert z.read('letra.lrc').strip()
    assert z.read('cifra.txt').strip()
result = {'test': 'real MP3 end-to-end', 'project_id': identifier, 'seconds': round(time.monotonic()-started, 2),
          'timing_scope': 'lyrics_retry_and_export_only' if len(sys.argv)>1 else 'full_pipeline',
          'stems': audio_checks, 'chords': p['chords'], 'lyrics': p['lyrics'], 'key': p.get('key'), 'bpm': p.get('bpm'),
          'range_streaming': True, 'zip_verified': True, 'warnings': p['warnings'],
          'engine': p['engine'], 'chord_analysis': p['chord_analysis']}
result['observed_progress'] = progress_events
(DATA / 'integration_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
print(json.dumps(result, ensure_ascii=False), flush=True)
server.should_exit = True
thread.join(timeout=5)
