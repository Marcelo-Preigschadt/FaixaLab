"""Regression test for local YouTube import and retry in the public site."""
import io, json, wave
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import sys
from playwright.sync_api import sync_playwright, expect

SITE = 'http://localhost:39081'
ORIGIN = 'https://expert-space-funicular-gjxr569wq4939wg9-7861.app.github.dev'
VIDEO = 'https://www.youtube.com/watch?v=aqz-KE-bpKQ'
TOKEN = '9999999999.' + 'a' * 64
f = io.BytesIO()
with wave.open(f, 'wb') as w:
    w.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
    w.writeframes(b'\x10\x00' * 800)
AUDIO = f.getvalue()

class Files(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

server = ThreadingHTTPServer(('127.0.0.1', 39081), partial(Files, directory=sys.argv[1]))
Thread(target=server.serve_forever, daemon=True).start()

def cors(route, status=200, **kwargs):
    route.fulfill(status=status, headers={'Access-Control-Allow-Origin': SITE, 'Access-Control-Allow-Headers': 'Authorization, Content-Type, X-FaixaLab-Import', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'}, **kwargs)

def emulate_backend(route, state):
    path = route.request.url.removeprefix(ORIGIN)
    if route.request.method == 'OPTIONS': return cors(route, 204)
    if path == '/auth/google/config':
        return cors(route, json={'client_id':'test-client', 'nonce':'nonce'})
    if path == '/auth/google/session':
        return cors(route, json={'api':TOKEN, 'media':TOKEN})
    if path == '/api/projects' and not state['server']:
        return cors(route, 503, json={'detail':'Servidor de teste indisponível.'})
    if path == '/api/import/file':
        data = route.request.post_data_buffer
        assert data and AUDIO in data and VIDEO.encode() in data and b'name="options"' in data
        assert route.request.all_headers().get('authorization') == 'Bearer ' + TOKEN
        state['uploads'] += 1
        return cors(route, 202 if state['server'] else 503, json={'id':'fixture'} if state['server'] else {'detail':'Servidor de teste indisponível.'})
    if path == '/api/import/youtube':
        state['cloud_imports'] += 1
        return cors(route, 500)
    if path == '/api/projects/fixture':
        return cors(route, json={'id':'fixture', 'title':'Importação de teste', 'status':'queued','duration':0,'stems':[], 'chords':[], 'lyrics':[]})
    return cors(route, json=[])

def emulate_importer(route, state):
    if route.request.method == 'OPTIONS': return cors(route, 204)
    port = int(route.request.url.split(':')[2].split('/')[0])
    state['ports'].append(port)
    if not state['active'] or port != state['port']: return route.abort('connectionrefused')
    assert route.request.post_data_json['url'] == VIDEO
    assert route.request.headers['x-faixalab-import']=='1'
    if state['busy']:
        state['busy'] = False
        return cors(route, 409 if port in (17862, 17863) else 429, json={'detail':'Já existe uma importação em andamento.'})
    state['local_audio'] += 1
    route.fulfill(status=200, body=AUDIO, headers={'Content-Type':'audio/wav','Access-Control-Allow-Origin':SITE,'Access-Control-Expose-Headers':'X-FaixaLab-Filename','X-FaixaLab-Filename':'FaixaLab.wav'})

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        for platform, ua, port, filename in (
            ('Android','Mozilla/5.0 Android',17862,'FaixaLab_Audio_Android.apk'),
            ('Win32','Mozilla/5.0 Windows',17861,'Instalar_FaixaLab_Windows.exe'),
            ('Chrome OS','Mozilla/5.0 CrOS',17861,'Instalar_FaixaLab_Linux.deb'),
        ):
            page = browser.new_page(user_agent=ua)
            page.add_init_script('Object.defineProperty(navigator,"userAgentData",{value:undefined});Object.defineProperty(navigator,"platform",{value:'+json.dumps(platform)+'});sessionStorage.setItem("faixalab-pages-session:'+ORIGIN+'",'+json.dumps(json.dumps({'api':TOKEN,'media':TOKEN}))+');')
            state={'uploads':0, 'local_audio':0, 'cloud_imports':0, 'active':False, 'server':False, 'port':port, 'ports':[], 'busy':True}
            page.route(ORIGIN+'/**',lambda route:emulate_backend(route,state))
            page.route('http://127.0.0.1:*/import', lambda route:emulate_importer(route,state))
            page.goto(SITE)
            expect(page.locator('#project-list')).to_contain_text('A biblioteca está indisponível', use_inner_text=False)
            expect(page.locator('#project-count')).to_have_text('—', use_inner_text=False)
            page.locator('#new-project').click()
            page.locator('[data-source=youtube]').click()
            assert page.locator('#youtube-import-mode, #youtube-save-local').count() == 0
            page.locator('#youtube-url').fill(VIDEO)
            page.locator('#import-submit').click()
            expect(page.locator('#import-error')).to_be_visible()
            expect(page.locator('#youtube-import-setup')).to_have_attribute('open','')
            assert page.locator('#youtube-import-download').get_attribute('href').endswith(filename)
            state['active'] = True
            page.locator('#import-submit').click()
            expect(page.locator('#import-submit')).to_contain_text('Aguardando a importação anterior')
            expect(page.locator('#import-submit')).to_be_disabled()
            expect(page.locator('#import-error')).to_contain_text('Áudio obtido neste aparelho')
            assert state['uploads']==1 and state['local_audio']==1
            state['server'] = True
            expect(page.locator('#import-submit')).to_contain_text('Tentar enviar novamente')
            page.locator('#import-submit').click()
            expect(page.locator('#import-dialog')).not_to_be_visible()
            assert state['uploads']==2 and state['local_audio']==1 and state['cloud_imports']==0
            print(platform, state, flush=True)
            page.close()
    finally:
        browser.close()
        server.shutdown()
