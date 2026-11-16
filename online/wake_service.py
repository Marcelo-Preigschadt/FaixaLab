"""Authenticated request to start the FaixaLab Codespace through GitHub Actions."""
import asyncio
import os
import re
from time import monotonic

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from faixalab.pages_gateway import checked_google_identity, create_app, pages_origin


async def dispatch_restore(client, repository):
    try:
        response = await client.post(f'/repos/{repository}/actions/workflows/faixalab-codespace.yml/dispatches',
                                     json={'ref': 'main'})
        response.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(503, 'O GitHub não confirmou a retomada do servidor.') from None


def make_app(pages_url, google_client_id, dispatch_token, repository):
    if not google_client_id or not re.fullmatch(r'[\w.-]+/[\w.-]+', repository):
        raise ValueError('Configuração incompleta para a retomada do FaixaLab')
    origin = pages_origin(pages_url)
    app = create_app(None, pages_url, 'auth-only', google_client_id=google_client_id, relay_enabled=False)
    lock = asyncio.Lock()
    next_request = 0.0

    @app.get('/wake/health')
    async def wake_health():
        return {'service': 'faixalab-wake', 'configured': bool(dispatch_token)}

    @app.post('/wake', status_code=202)
    async def wake(request: Request):
        if request.headers.get('origin') != origin:
            raise HTTPException(403, 'Origem não autorizada.')
        if not dispatch_token:
            raise HTTPException(503, 'A retomada do servidor ainda está em configuração.')
        authorization = request.headers.get('authorization', '')
        if not authorization.startswith('Bearer ') or not 7 < len(authorization) <= 8199:
            raise HTTPException(401, 'Entre com Google para iniciar a separação.')
        await run_in_threadpool(checked_google_identity, authorization[7:], google_client_id)
        nonlocal next_request
        async with lock:
            if monotonic() >= next_request:
                async with httpx.AsyncClient(
                    base_url='https://api.github.com',
                    headers={
                        'Authorization': 'Bearer ' + dispatch_token,
                        'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2026-03-10',
                    },
                    timeout=8, trust_env=False,
                ) as client:
                    await dispatch_restore(client, repository)
                next_request = monotonic() + 45
        return JSONResponse({'status': 'starting'}, status_code=202, headers={'Cache-Control': 'no-store'})

    return app


def app_from_env():
    return make_app(
        os.environ['FAIXALAB_PAGES_URL'], os.environ['FAIXALAB_GOOGLE_CLIENT_ID'],
        os.environ.get('FAIXALAB_WAKE_DISPATCH_TOKEN', ''), os.environ['FAIXALAB_WAKE_REPOSITORY'],
    )
