"""Access checks for the desktop, Codespaces and the hosted gateway."""
import hmac
import os
from urllib.parse import urlsplit


def allowed_api(headers):
    expected = os.environ.get('FAIXALAB_API_KEY', '')
    if not expected:
        return os.environ.get('FAIXALAB_REMOTE') != '1'
    supplied = headers.get('x-faixalab-key', '')
    return hmac.compare_digest(supplied.encode('utf-8'), expected.encode('utf-8'))


def allowed_origin(headers, request_origin):
    origin = headers.get('origin')
    if not origin:
        return True

    codespace = os.environ.get('CODESPACE_NAME')
    port = os.environ.get('PORT', '7860')
    domain = os.environ.get('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'app.github.dev')
    cloud_origin = f'https://{codespace}-{port}.{domain}' if codespace else None
    expected = os.environ.get('FAIXALAB_ORIGIN') or cloud_origin or request_origin
    if origin == expected:
        return True
    if not cloud_origin or expected != cloud_origin or os.environ.get('CODESPACES') != 'true':
        return False

    # The port-forwarding proxy can rewrite the browser's Origin to loopback.
    # Require same-origin browser metadata before accepting that rewrite.
    proxy_origins = {f'{scheme}://{host}:{port}' for scheme in ('http', 'https')
                     for host in ('localhost', '127.0.0.1', '[::1]')}
    if origin not in proxy_origins:
        return False
    fetch_site = headers.get('sec-fetch-site')
    if fetch_site:
        return fetch_site == 'same-origin'
    try:
        referer = urlsplit(headers.get('referer', ''))
    except ValueError:
        return False
    return f'{referer.scheme}://{referer.netloc}' == cloud_origin


def validate_server_settings():
    if os.environ.get('FAIXALAB_REMOTE') == '1' and not os.environ.get('FAIXALAB_API_KEY'):
        raise RuntimeError('Defina FAIXALAB_API_KEY como segredo antes de iniciar o servidor online.')
