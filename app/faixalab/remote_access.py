"""Server-to-server access for the separately hosted online interface."""
import hmac
import os


def allowed_api(headers):
    expected = os.environ.get('FAIXALAB_API_KEY', '')
    if not expected:
        return os.environ.get('FAIXALAB_REMOTE') != '1'
    supplied = headers.get('x-faixalab-key', '')
    return hmac.compare_digest(supplied.encode('utf-8'), expected.encode('utf-8'))


def validate_server_settings():
    if os.environ.get('FAIXALAB_REMOTE') == '1' and not os.environ.get('FAIXALAB_API_KEY'):
        raise RuntimeError('Defina FAIXALAB_API_KEY como segredo antes de iniciar o servidor online.')
