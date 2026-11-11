import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from faixalab.app import app
from faixalab.remote_access import validate_server_settings


class RemoteAccessChecks(unittest.TestCase):
    def test_desktop_keeps_working_without_a_server_key(self):
        with patch.dict(os.environ, {'FAIXALAB_REMOTE':'0','FAIXALAB_API_KEY':''}), TestClient(app) as client:
            self.assertEqual(client.get('/api/projects').status_code,200)

    def test_online_server_requires_the_gateway_key(self):
        with patch.dict(os.environ, {'FAIXALAB_REMOTE':'1','FAIXALAB_API_KEY':'only-the-server-knows'}), TestClient(app) as client:
            for path in ('/api/projects','/api/connection','/api/projects/not-a-project/audio/original'):
                self.assertEqual(client.get(path).status_code,401)
                self.assertEqual(client.get(path,headers={'X-FaixaLab-Key':'wrong'}).status_code,401)
            self.assertEqual(client.get('/api/projects',headers={'X-FaixaLab-Key':'only-the-server-knows'}).status_code,200)
            self.assertEqual(client.get('/api/connection',headers={'X-FaixaLab-Key':'only-the-server-knows'}).status_code,200)
            self.assertEqual(client.get('/api/health').json()['processing'],'cloud')

    def test_remote_mode_does_not_start_unprotected(self):
        with patch.dict(os.environ, {'FAIXALAB_REMOTE':'1','FAIXALAB_API_KEY':''}):
            with self.assertRaisesRegex(RuntimeError,'FAIXALAB_API_KEY'):
                validate_server_settings()

    def test_codespaces_accepts_the_proxy_rewrite_for_same_origin_imports(self):
        public_origin = 'https://faixalab-test-7860.app.github.dev'
        environment = {'CODESPACES': 'true', 'CODESPACE_NAME': 'faixalab-test', 'PORT': '7860',
                       'GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN': 'app.github.dev',
                       'FAIXALAB_REMOTE': '0', 'FAIXALAB_API_KEY': '', 'FAIXALAB_ORIGIN': ''}
        cases = (
            ({'Origin': public_origin}, 422),
            ({'Origin': 'http://localhost:7860', 'Sec-Fetch-Site': 'same-origin'}, 422),
            ({'Origin': 'http://127.0.0.1:7860', 'Referer': public_origin + '/'}, 422),
            ({'Origin': 'http://localhost:7860'}, 403),
            ({'Origin': 'http://localhost:7860', 'Sec-Fetch-Site': 'cross-site', 'Referer': public_origin + '/'}, 403),
            ({'Origin': 'http://localhost:7861', 'Sec-Fetch-Site': 'same-origin'}, 403),
            ({'Origin': 'https://other-7860.app.github.dev', 'Sec-Fetch-Site': 'same-site'}, 403),
        )
        with patch.dict(os.environ, environment), TestClient(app, base_url=public_origin) as client:
            for headers, status in cases:
                with self.subTest(headers=headers):
                    response = client.post('/api/import/youtube', json={'url': 'inválido'}, headers=headers)
                    self.assertEqual(response.status_code, status, response.text)
                    if status == 403:
                        self.assertEqual(response.json()['detail'], 'Origem não autorizada.')
            with patch.dict(os.environ, {'FAIXALAB_ORIGIN': 'https://configured.example'}):
                response = client.post('/api/import/youtube', json={'url': 'inválido'}, headers=cases[1][0])
                self.assertEqual(response.status_code, 403)
