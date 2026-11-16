"""Authenticated Codespace start and Google sign-in while the audio server sleeps."""
import asyncio
from base64 import b64decode
import os
import re
from time import monotonic

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from faixalab.pages_gateway import create_app, pages_origin, token_account


async def start_codespace(client, codespace, repository_id):
    endpoint = f'/user/codespaces/{codespace}'
    try:
        response = await client.get(endpoint)
        response.raise_for_status()
        current = response.json()
        if current.get('repository', {}).get('id') != repository_id:
            raise ValueError('Unexpected repository')
        if current.get('state') != 'Shutdown':
            return
        response = await client.post(endpoint + '/start')
        # A second start request can race with a manual start in GitHub.
        if response.status_code == 409:
            return
        if response.status_code == 403:
            raise HTTPException(503, 'O GitHub recusou a retomada. Confira a cota do Codespaces.')
        response.raise_for_status()
    except (httpx.HTTPError, ValueError, AttributeError):
        raise HTTPException(503, 'O GitHub não confirmou a retomada do servidor.') from None


def make_app(pages_url, signing_key, google_client_id, github_token, codespace, repository_id):
    if not github_token or not signing_key or not google_client_id or not re.fullmatch(r'[a-z0-9-]+', codespace):
        raise ValueError('Configuração incompleta para a retomada do FaixaLab')
    origin = pages_origin(pages_url)
    app = create_app(None, pages_url, signing_key, google_client_id=google_client_id, relay_enabled=False)
    lock = asyncio.Lock()
    next_request = 0.0

    @app.post('/wake', status_code=202)
    async def wake(request: Request):
        if request.headers.get('origin') != origin:
            raise HTTPException(403, 'Origem não autorizada.')
        authorization = request.headers.get('authorization', '')
        if not authorization.startswith('Bearer ') or token_account(authorization[7:], signing_key, 'api') is None:
            raise HTTPException(401, 'Entre com Google para iniciar a separação.')
        nonlocal next_request
        async with lock:
            if monotonic() >= next_request:
                async with httpx.AsyncClient(
                    base_url='https://api.github.com',
                    headers={
                        'Authorization': 'Bearer ' + github_token,
                        'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2026-03-10',
                    },
                    timeout=8,
                ) as client:
                    await start_codespace(client, codespace, repository_id)
                next_request = monotonic() + 20
        return JSONResponse({'status': 'starting'}, status_code=202, headers={'Cache-Control': 'no-store'})

    return app


def app_from_env():
    private_key = serialization.load_pem_private_key(os.environ['FAIXALAB_WAKE_PRIVATE_KEY'].encode(), password=None)
    oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    github_token = private_key.decrypt(b64decode(os.environ['FAIXALAB_WAKE_TOKEN'], validate=True), oaep).decode()
    signing_key = private_key.decrypt(b64decode(os.environ['FAIXALAB_WAKE_SIGNING_KEY'], validate=True), oaep).decode()
    return make_app(
        os.environ['FAIXALAB_PAGES_URL'], signing_key, os.environ['FAIXALAB_GOOGLE_CLIENT_ID'],
        github_token, os.environ['FAIXALAB_CODESPACE'], int(os.environ['FAIXALAB_REPOSITORY_ID']),
    )
