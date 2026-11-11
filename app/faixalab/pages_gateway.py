"""Authenticated HTTP relay for the GitHub Pages interface."""
from contextlib import asynccontextmanager
import hashlib
import hmac
import os
import re
import time
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask


SESSION_SECONDS = 3 * 60 * 60
MEDIA_ROUTE = re.compile(r'/api/projects/[a-f0-9]{32}/(?:audio|backing|export)/[a-zA-Z0-9_-]+')
REQUEST_HEADERS = {'accept', 'content-length', 'content-type', 'if-range', 'range'}
RESPONSE_HEADERS = {'accept-ranges', 'content-disposition', 'content-length', 'content-range', 'content-type'}


def pages_origin(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.github.io')
            or parsed.port is not None or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or not parsed.path.endswith('/')):
        raise ValueError('Configure FAIXALAB_PAGES_URL com a URL HTTPS do projeto no GitHub Pages.')
    return f'https://{parsed.netloc}'


def issue_token(key, scope, expires):
    signature = hmac.new(key.encode(), f'{scope}:{expires}'.encode(), hashlib.sha256).hexdigest()
    return f'{expires}.{signature}'


def valid_token(token, key, scope):
    expiry, dot, signature = token.partition('.')
    if not dot or not re.fullmatch(r'[0-9]{1,12}', expiry) or len(signature) != 64 or int(expiry) <= time.time():
        return False
    return hmac.compare_digest(token, issue_token(key, scope, expiry))


def create_app(upstream, url, key, backend_key=''):
    if not key:
        raise ValueError('FAIXALAB_PAGES_KEY precisa estar configurada.')
    origin = pages_origin(url)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(base_url=upstream, follow_redirects=False, trust_env=False,
                                     timeout=httpx.Timeout(240, connect=5)) as client:
            app.state.backend = client
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=[origin],
                       allow_methods=['GET', 'HEAD', 'POST', 'PATCH', 'DELETE', 'PUT'],
                       allow_headers=['Authorization', 'Content-Type', 'If-Range', 'Range'],
                       expose_headers=['Accept-Ranges', 'Content-Disposition', 'Content-Range'])

    @app.get('/health')
    async def health():
        return {'service': 'faixalab-pages'}

    @app.api_route('/api/{path:path}', methods=['GET', 'HEAD', 'POST', 'PATCH', 'DELETE', 'PUT'])
    async def relay(request: Request, path: str):
        if request.headers.get('origin', origin) != origin or any(part in {'.', '..'} for part in path.split('/')):
            return JSONResponse({'detail': 'Origem não autorizada.'}, status_code=403)
        authorization = request.headers.get('authorization', '')
        api_access = authorization.startswith('Bearer ') and valid_token(authorization[7:], key, 'api')
        media_access = (request.method in {'GET', 'HEAD'} and MEDIA_ROUTE.fullmatch(request.url.path)
                        and valid_token(request.query_params.get('access', ''), key, 'media'))
        if not api_access and not media_access:
            return JSONResponse({'detail': 'Conecte sua conta do GitHub novamente para acessar o FaixaLab.'}, status_code=401)

        headers = {name: value for name, value in request.headers.items() if name in REQUEST_HEADERS}
        headers['accept-encoding'] = 'identity'
        if backend_key:
            headers['x-faixalab-key'] = backend_key
        params = [(name, value) for name, value in request.query_params.multi_items() if name != 'access']
        body = None if request.method in {'GET', 'HEAD'} else request.stream()
        backend = request.app.state.backend
        upstream_request = backend.build_request(request.method, request.url.path, params=params, headers=headers, content=body)
        try:
            response = await backend.send(upstream_request, stream=True)
        except httpx.RequestError:
            return JSONResponse({'detail': 'O processamento do Codespace está indisponível.'}, status_code=503)
        forwarded = {name: value for name, value in response.headers.items() if name in RESPONSE_HEADERS}
        forwarded.update({'cache-control': 'private, no-store', 'referrer-policy': 'no-referrer',
                          'x-content-type-options': 'nosniff'})
        return StreamingResponse(response.aiter_raw(), status_code=response.status_code, headers=forwarded,
                                 background=BackgroundTask(response.aclose))

    return app


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(create_app(f'http://127.0.0.1:{os.environ.get("PORT", "7860")}',
                           os.environ['FAIXALAB_PAGES_URL'], os.environ['FAIXALAB_PAGES_KEY'],
                           os.environ.get('FAIXALAB_API_KEY', '')), host='0.0.0.0', port=7861, access_log=False)
