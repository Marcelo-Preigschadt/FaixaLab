import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from faixalab.pages_gateway import create_app, token_account
from faixalab.wake_session import WakeSession
from online.wake_service import dispatch_restore, make_app

SITE = 'https://marcelo-preigschadt.github.io'
REPO = 'Marcelo-Preigschadt/mvlab'
DISPATCH_TOKEN = 'test-dispatch-token'
ACCOUNT = 'a' * 64
SIGNER = WakeSession.from_dispatch_token(DISPATCH_TOKEN)
EXPIRES = int(time.time()) + 3600
HEADERS = {'Origin': SITE, 'Authorization': 'Bearer ' + SIGNER.issue('api', EXPIRES, ACCOUNT)}


def test_wake_requires_the_site_and_a_valid_session_and_coalesces_requests():
    app = make_app(SITE + '/FaixaLab/', 'google-client', DISPATCH_TOKEN, REPO)
    with TestClient(app) as browser, patch('online.wake_service.dispatch_restore', new_callable=AsyncMock) as dispatch:
        assert browser.post('/wake', headers={'Origin': SITE}).status_code == 401
        assert browser.post('/wake', headers={**HEADERS, 'Origin': 'https://example.com'}).status_code == 403
        assert browser.get('/api/projects', headers=HEADERS).status_code == 404
        assert browser.get('/auth/google/config', headers={'Origin': SITE}).json()['client_id'] == 'google-client'
        key = browser.get('/wake/public-key').json()['key']
        assert WakeSession.from_public_key(key).verify(HEADERS['Authorization'][7:], 'api') == ACCOUNT
        assert browser.post('/wake', headers=HEADERS).status_code == 202
        assert browser.post('/wake', headers=HEADERS).status_code == 202
        dispatch.assert_awaited_once()
        assert dispatch.await_args.args[1] == REPO


def test_missing_dispatch_token_is_an_explicit_blocker():
    with TestClient(make_app(SITE + '/FaixaLab/', 'google-client', '', REPO)) as browser:
        assert browser.get('/wake/health').json()['configured'] is False
        assert browser.post('/wake', headers=HEADERS).status_code == 503


def test_dispatch_targets_only_the_existing_restore_workflow():
    async def verify():
        def respond(request):
            assert request.url.path == f'/repos/{REPO}/actions/workflows/faixalab-codespace.yml/dispatches'
            assert request.method == 'POST' and b'"ref":"main"' in request.content
            return httpx.Response(200, json={'workflow_run_id': 123})

        async with httpx.AsyncClient(base_url='https://api.github.com', transport=httpx.MockTransport(respond)) as client:
            await dispatch_restore(client, REPO)

    asyncio.run(verify())


def test_gateway_keeps_account_isolation_when_verifying_portal_sessions():
    def respond(request):
        token = request.headers['x-faixalab-pages-session']
        assert token_account(token, 'codespace-signing-key', 'api') == ACCOUNT
        return httpx.Response(200, stream=httpx.ByteStream(b'{"status":"ok"}'))

    gateway = create_app('http://upstream', SITE + '/FaixaLab/', 'codespace-signing-key',
                         verify_portal_session=SIGNER.verify)
    upstream = httpx.AsyncClient(base_url='http://upstream', transport=httpx.MockTransport(respond))
    with patch('faixalab.pages_gateway.httpx.AsyncClient', return_value=upstream), TestClient(gateway) as browser:
        assert browser.get('/api/health', headers=HEADERS).status_code == 200
        wrong_scope = SIGNER.issue('media', EXPIRES, ACCOUNT)
        assert browser.get('/api/health', headers={**HEADERS, 'Authorization': 'Bearer ' + wrong_scope}).status_code == 401
