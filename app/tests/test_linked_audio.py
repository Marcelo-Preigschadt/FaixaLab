import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

from fastapi.testclient import TestClient
import httpx
import uvicorn

from faixalab import pipeline, source_api, source_client, storage
from faixalab.app import app, codespace_status
from faixalab.youtube_support import COOKIE_SECRET


VIDEO_URL = 'https://www.youtube.com/watch?v=u_ix058WpVo'


class LinkedAudioChecks(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        projects = directory / 'projects'
        projects.mkdir()
        self.enterContext(patch.multiple(storage, ROOT=directory, PROJECTS=projects))
        self.enterContext(patch.dict('os.environ', {'CODESPACES': 'false', 'CODESPACE_NAME': '',
                                                   'FAIXALAB_REMOTE': '1', 'FAIXALAB_API_KEY': 'test-key',
                                                   COOKIE_SECRET: '',
                                                   'FAIXALAB_AUDIO_SOURCE_URL': '',
                                                   'FAIXALAB_AUDIO_SOURCE_KEY': ''}))
        self.submit = self.enterContext(patch.object(pipeline, 'submit'))
        self.client = self.enterContext(TestClient(app, headers={'X-FaixaLab-Key': 'test-key'}))
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\x01\x00' * 4000)
        self.audio = output.getvalue()

    def test_cloud_reuses_the_file_linked_to_a_video(self):
        response = self.client.post('/api/import/file', data={'youtube_url': VIDEO_URL},
                                    files={'file': ('faixa.wav', self.audio, 'audio/wav')})
        self.assertEqual(response.status_code, 202, response.text)
        first = response.json()
        self.assertEqual(first['source']['url'], VIDEO_URL)
        self.submit.assert_called_once_with(first['id'])

        response = self.client.post('/api/import/youtube', json={'url': 'https://youtu.be/u_ix058WpVo'})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['id'], first['id'])
        self.assertTrue(response.json()['reused'])
        self.submit.assert_called_once()

        storage.update_project(first['id'], status='interrupted')
        response = self.client.post('/api/import/youtube', json={'url': VIDEO_URL, 'options': {'stems': 4}})
        self.assertEqual(response.status_code, 202, response.text)
        second = response.json()
        self.assertNotEqual(second['id'], first['id'])
        self.assertEqual(second['source']['type'], 'file')
        self.assertEqual(second['options']['stems'], 4)
        self.assertEqual((storage.project_dir(second['id']) / second['source']['file']).read_bytes(), self.audio)
        self.assertEqual(self.submit.call_count, 2)

    def test_regular_upload_and_desktop_youtube_remain_available(self):
        response = self.client.post('/api/import/file', data={'options': json.dumps({'stems': 4})},
                                    files={'file': ('faixa.wav', self.audio, 'audio/wav')})
        self.assertEqual(response.status_code, 202)
        self.assertNotIn('youtube_id', response.json()['source'])
        with patch.dict('os.environ', {'FAIXALAB_REMOTE': '0', 'FAIXALAB_API_KEY': ''}):
            response = self.client.post('/api/import/youtube', json={'url': VIDEO_URL})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['source']['type'], 'youtube')

    def test_cloud_accepts_only_the_link_when_the_provider_is_configured(self):
        with patch.dict('os.environ', {'FAIXALAB_AUDIO_SOURCE_URL': 'http://127.0.0.1:7870',
                                      'FAIXALAB_AUDIO_SOURCE_KEY': 'provider-test-key'}):
            response = self.client.post('/api/import/youtube', json={'url': VIDEO_URL})
        self.assertEqual(response.status_code, 202, response.text)
        project = response.json()
        self.assertEqual(project['source']['provider'], 'faixalab-source')
        self.assertEqual(project['source']['url'], VIDEO_URL)
        self.submit.assert_called_once_with(project['id'])

    def test_codespace_queues_a_link_for_its_configured_session(self):
        with patch.dict('os.environ', {'CODESPACES': 'true'}):
            response = self.client.post('/api/import/youtube', json={'url': VIDEO_URL})
            self.assertEqual(response.status_code, 503, response.text)
            self.assertIn(COOKIE_SECRET, response.json()['detail'])
            self.submit.assert_not_called()
            with patch.dict('os.environ', {COOKIE_SECRET: 'fixture-session'}):
                response = self.client.post('/api/import/youtube', json={'url': VIDEO_URL})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()['source'], {'type': 'youtube', 'url': VIDEO_URL})
        self.submit.assert_called_once_with(response.json()['id'])

    def test_api_and_client_stream_the_original_audio_over_http(self):
        def extract(url, directory, cancel, progress):
            self.assertEqual(url, VIDEO_URL)
            output = directory / 'youtube.wav'
            output.write_bytes(self.audio)
            return output, 'Faixa de teste'

        fake_download = self.enterContext(patch.object(source_api, 'download_youtube', side_effect=extract))
        source_root = storage.ROOT / 'api-source'
        key = 'provider-test-key'
        source = source_api.create_app(source_root, key)
        sock = self.enterContext(socket.create_server(('127.0.0.1', 0)))
        address = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(source, log_level='error'))
        worker = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)

        def close_server():
            server.should_exit = True
            worker.join(timeout=5)

        worker.start()
        self.addCleanup(close_server)
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(server.started)
        self.assertEqual(httpx.get(address + '/v1/health', trust_env=False).status_code, 401)
        with patch.dict('os.environ', {'FAIXALAB_AUDIO_SOURCE_URL': address, 'FAIXALAB_AUDIO_SOURCE_KEY': key}):
            path, title = source_client.download_audio(VIDEO_URL, storage.ROOT, threading.Event(), lambda *args: None)
            self.assertEqual(source_client.download_audio(VIDEO_URL, storage.ROOT, threading.Event(), lambda *args: None), (path, title))
        self.assertEqual(path.read_bytes(), self.audio)
        self.assertEqual(title, 'Faixa de teste')
        fake_download.assert_called_once()
        with TestClient(source_api.create_app(source_root, key), headers={'Authorization': f'Bearer {key}'}) as restarted:
            response = restarted.post('/v1/youtube-jobs', json={'url': VIDEO_URL})
            self.assertEqual(response.json()['status'], 'ready')
            self.assertEqual(restarted.get('/v1/youtube-jobs/u_ix058WpVo/audio').content, self.audio)
        fake_download.assert_called_once()


class CodespaceStatusChecks(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_status_counts_active_projects_and_waits(self):
        projects = [{'status': 'queued'}, {'status': 'processing'}, {'status': 'ready'}]
        output = io.StringIO()
        with patch.object(storage, 'list_projects', return_value=projects), redirect_stdout(output):
            with patch('faixalab.app.asyncio.sleep', side_effect=asyncio.CancelledError) as sleep:
                with self.assertRaises(asyncio.CancelledError):
                    await codespace_status()
        self.assertIn('FaixaLab ativo | 1 na fila | 1 em processamento', output.getvalue())
        sleep.assert_awaited_once_with(180)
