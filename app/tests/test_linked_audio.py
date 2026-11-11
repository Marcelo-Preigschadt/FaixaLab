import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

from fastapi.testclient import TestClient
import httpx

from faixalab import pipeline, stemsplit, storage
from faixalab.app import app, codespace_status


VIDEO_URL = 'https://www.youtube.com/watch?v=u_ix058WpVo'


class LinkedAudioChecks(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        projects = directory / 'projects'
        projects.mkdir()
        self.enterContext(patch.multiple(storage, ROOT=directory, PROJECTS=projects))
        self.enterContext(patch.dict('os.environ', {'CODESPACES': 'false', 'CODESPACE_NAME': '',
                                                   'FAIXALAB_REMOTE': '1', 'FAIXALAB_API_KEY': 'test-key',
                                                   'STEMSPLIT_API_KEY': ''}))
        self.submit = self.enterContext(patch.object(pipeline, 'submit'))
        self.client = self.enterContext(TestClient(app, headers={'X-FaixaLab-Key': 'test-key'}))
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\x01\x00' * 4000)
        self.audio = output.getvalue()

    def test_cloud_requires_a_file_once_then_reuses_it_for_the_video(self):
        response = self.client.post('/api/import/youtube', json={'url': VIDEO_URL})
        self.assertEqual(response.status_code, 503)
        self.submit.assert_not_called()

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
        with patch.dict('os.environ', {'STEMSPLIT_API_KEY': 'provider-test-key'}):
            response = self.client.post('/api/import/youtube', json={'url': VIDEO_URL})
        self.assertEqual(response.status_code, 202, response.text)
        project = response.json()
        self.assertEqual(project['source']['provider'], 'stemsplit')
        self.assertEqual(project['source']['url'], VIDEO_URL)
        self.submit.assert_called_once_with(project['id'])

    def test_provider_downloads_complete_audio_and_reuses_it_without_another_job(self):
        requests = []

        def handle(request):
            requests.append(request)
            if request.method == 'POST':
                self.assertEqual(json.loads(request.content), {'youtubeUrl': VIDEO_URL})
                return httpx.Response(201, json={'id': 'job-123', 'videoTitle': 'Faixa de teste'})
            if request.url.host == 'stemsplit.io':
                return httpx.Response(200, json={'status': 'COMPLETED', 'outputs': {
                    'fullAudio': {'url': 'https://media.example/full.mp3?sig=test'}}})
            return httpx.Response(200, content=self.audio, headers={'Content-Type': 'audio/mpeg'})

        client = httpx.Client(transport=httpx.MockTransport(handle))
        with patch.dict('os.environ', {'STEMSPLIT_API_KEY': 'provider-test-key'}):
            with patch.object(stemsplit.httpx, 'Client', return_value=client):
                path, title = stemsplit.download_audio(VIDEO_URL, threading.Event(), lambda *args: None)
                self.assertEqual(stemsplit.download_audio(VIDEO_URL, threading.Event(), lambda *args: None), (path, title))
        self.assertEqual(path.read_bytes(), self.audio)
        self.assertEqual(title, 'Faixa de teste')
        self.assertEqual(len(requests), 3)
        self.assertEqual(requests[0].headers['authorization'], 'Bearer provider-test-key')
        self.assertNotIn('authorization', requests[2].headers)


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
