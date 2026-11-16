import asyncio
import hashlib
import time
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from faixalab.pages_gateway import create_app, token_account
from online.wake_service import dispatch_restore, make_app

SITE = 'https://marcelo-preigschadt.github.io'
REPO = 'Marcelo-Preigschadt/mvlab'
IDENTITY = 'google-signed-id-token'
HEADERS = {'Origin': SITE, 'Authorization': 'Bearer ' + IDENTITY}
CLAIMS = {'sub': 'test-google-subject', 'exp': int(time.time()) + 3600}


def verify_identity(credential, audience):
    assert audience == 'google-client'
    if credential != IDENTITY:
        raise ValueError('Invalid identity')
    return CLAIMS


def test_wake_requires_google_identity_and_coalesces_requests():
    app = make_app(SITE + '/FaixaLab/', 'google-client', 'dispatch-token', REPO)
    with (TestClient(app) as browser,
          patch('faixalab.pages_gateway.verify_google_identity', side_effect=verify_identity),
          patch('online.wake_service.dispatch_restore', new_callable=AsyncMock) as dispatch):
        assert browser.post('/wake', headers={'Origin': SITE}).status_code == 401
        assert browser.post('/wake', headers={**HEADERS, 'Origin': 'https://example.com'}).status_code == 403
        assert browser.post('/wake', headers={**HEADERS, 'Authorization': 'Bearer dispatch-token'}).status_code == 401
        assert browser.get('/api/projects', headers=HEADERS).status_code == 404
        assert browser.get('/auth/google/config', headers={'Origin': SITE}).json()['client_id'] == 'google-client'
        assert browser.post('/wake', headers=HEADERS).status_code == 202
        assert browser.post('/wake', headers=HEADERS).status_code == 202
        dispatch.assert_awaited_once()
        assert dispatch.await_args.args[1] == REPO


def test_missing_dispatch_token_keeps_start_disabled():
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


def test_gateway_preserves_account_isolation_and_issues_fresh_sessions():
    gateway = create_app('http://upstream', SITE + '/FaixaLab/', 'codespace-signing-key',
                         google_client_id='google-client', google_portal=True)
    account = hashlib.sha256(('google:' + CLAIMS['sub']).encode()).hexdigest()
    with (TestClient(gateway) as browser,
          patch('faixalab.pages_gateway.verify_google_identity', side_effect=verify_identity)):
        route = '/auth/google/portal-session'
        assert browser.post(route, headers={'Origin': SITE}, json={'credential': 'dispatch-token'}).status_code == 401
        response = browser.post(route, headers={'Origin': SITE}, json={'credential': IDENTITY})
        assert response.status_code == 200
        assert token_account(response.json()['api'], 'codespace-signing-key', 'api') == account
        assert token_account(response.json()['media'], 'codespace-signing-key', 'media') == account
        assert token_account(response.json()['media'], 'codespace-signing-key', 'api') is None


def test_google_signin_does_not_need_the_codespace_running():
    with TestClient(make_app(SITE + '/FaixaLab/', 'google-client', 'dispatch-token', REPO)) as browser:
        nonce = browser.get('/auth/google/config', headers={'Origin': SITE}).json()['nonce']
        with patch('faixalab.pages_gateway.verify_google_identity', return_value={**CLAIMS, 'nonce': nonce}):
            body = {'credential': IDENTITY, 'nonce': nonce}
            reply = browser.post('/auth/google/session', headers={'Origin': SITE}, json=body)
            assert reply.json() == {'expires': CLAIMS['exp']}
            assert browser.post('/auth/google/session', headers={'Origin': SITE}, json=body).status_code == 401
