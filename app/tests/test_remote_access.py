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
