import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from faixalab import pages_gateway, pipeline, storage
from faixalab.app import app
from faixalab.youtube_support import COOKIE_SECRET


class GoogleAccessTest(unittest.TestCase):
    def test_google_accounts_share_processing_but_not_projects_or_import_cache(self):
        origin = 'https://studio.github.io'
        key = 'session-key-for-tests'
        video = 'https://www.youtube.com/watch?v=abcdefghijk'
        with TemporaryDirectory() as folder:
            root = Path(folder)
            projects = root / 'projects'
            projects.mkdir()
            settings = {'FAIXALAB_PAGES_KEY': key, 'FAIXALAB_API_KEY': 'relay-only',
                        'CODESPACES': 'true', COOKIE_SECRET: 'dedicated-service-session'}
            with patch.multiple(storage, ROOT=root, PROJECTS=projects), patch.dict(os.environ, settings), \
                    patch.object(pipeline, 'submit') as submit:
                owner = storage.new_project('Projeto antigo', {}, {})
                gateway = pages_gateway.create_app('http://faixalab', origin + '/FaixaLab/', key,
                                                   'relay-only', 'web-client.apps.googleusercontent.com')
                with TestClient(gateway, headers={'Origin': origin}) as client:
                    gateway.state.backend = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                                              base_url='http://faixalab')

                    def sign_in(subject):
                        config = client.get('/auth/google/config').json()
                        nonce = config['nonce']
                        payload = {'credential': 'test-id-token', 'nonce': nonce}
                        with patch.object(pages_gateway, 'verify_google_identity',
                                          return_value={'sub': subject, 'nonce': nonce}) as verify:
                            result = client.post('/auth/google/session', json=payload)
                            self.assertEqual(result.status_code, 200)
                            verify.assert_called_once_with('test-id-token', config['client_id'])
                            self.assertEqual(client.post('/auth/google/session', json=payload).status_code, 401)
                        session = result.json()
                        return {'Authorization': 'Bearer ' + session['api']}, session['media']

                    alice, alice_media = sign_in('alice')
                    bob, bob_media = sign_in('bob')
                    self.assertEqual(client.get('/api/projects', headers=alice).json(), [])
                    self.assertEqual(client.get('/api/projects/' + owner['id'], headers=alice).status_code, 404)
                    self.assertEqual(client.get('/api/projects', headers={pages_gateway.SESSION_HEADER: alice['Authorization'][7:]}).status_code, 401)

                    def upload(headers):
                        return client.post('/api/import/file', headers=headers,
                                           files={'file': ('same.wav', b'test audio', 'audio/wav')},
                                           data={'youtube_url': video})

                    first = upload(alice)
                    second = upload(bob)
                    self.assertEqual((first.status_code, second.status_code), (202, 202))
                    alice_id, bob_id = first.json()['id'], second.json()['id']
                    self.assertNotEqual(alice_id, bob_id)
                    self.assertEqual(upload(alice).json()['id'], alice_id)
                    self.assertEqual([p['id'] for p in client.get('/api/projects', headers=bob).json()], [bob_id])
                    self.assertEqual(client.post(f'/api/projects/{alice_id}/cancel', headers=bob).status_code, 404)
                    self.assertEqual(client.post('/api/import/youtube', headers=bob, json={'url': video}).json()['id'], bob_id)
                    self.assertEqual(client.post('/api/import/youtube', headers=alice, json={'url': video}).json()['id'], alice_id)

                    (projects / alice_id / 'original.wav').write_bytes(b'audio data')
                    audio = f'/api/projects/{alice_id}/audio/original'
                    self.assertEqual(client.get(audio, params={'access': alice_media}, headers={'Range': 'bytes=0-4'}).status_code, 206)
                    self.assertEqual(client.get(audio, params={'access': bob_media}).status_code, 404)
                    self.assertEqual(client.get('/api/projects', params={'access': alice_media}).status_code, 401)

                    direct = client.post('/api/import/youtube', headers=bob,
                                         json={'url': 'https://www.youtube.com/watch?v=lmnopqrstuv'})
                    self.assertEqual(direct.status_code, 202)
                    self.assertEqual(direct.json()['source']['type'], 'youtube')
                    direct_id = direct.json()['id']
                    submit.assert_called_with(direct_id)
                    attempt = f'/api/projects/{direct_id}'
                    self.assertEqual(client.delete(attempt, headers=bob).status_code, 409)
                    storage.update_project(direct_id, status='failed')
                    self.assertEqual(client.delete(attempt, headers=alice).status_code, 404)
                    listed = client.get('/api/projects', headers=bob).json()
                    self.assertTrue(next(p for p in listed if p['id'] == direct_id)['can_delete_import'])
                    self.assertEqual(client.delete(attempt, headers=bob).json(), {'deleted': True})
                    self.assertFalse((projects / direct_id).exists())
                    self.assertEqual(client.get(attempt, headers=bob).status_code, 404)
                    self.assertEqual([p['id'] for p in client.get('/api/projects', headers=bob).json()], [bob_id])
                    recreated = client.post('/api/import/youtube', headers=bob,
                                            json={'url': 'https://www.youtube.com/watch?v=lmnopqrstuv'})
                    self.assertEqual(recreated.status_code, 202)
                    self.assertNotEqual(recreated.json()['id'], direct_id)

                    owner_token = pages_gateway.issue_token(key, 'api', int(pages_gateway.time.time()) + 60)
                    legacy = client.get('/api/projects', headers={'Authorization': 'Bearer ' + owner_token})
                    self.assertEqual([p['id'] for p in legacy.json()], [owner['id']])


if __name__ == '__main__':
    unittest.main()
