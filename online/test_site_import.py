"""Regression test for local YouTube import and retry in the public site."""
import io, json, os, wave
from email import policy
from email.parser import BytesParser
import re
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import sys
from playwright.sync_api import sync_playwright, expect

SITE = 'http://localhost:39081'
ORIGIN = 'https://expert-space-funicular-gjxr569wq4939wg9-7861.app.github.dev'
VIDEO = 'https://www.youtube.com/watch?v=aqz-KE-bpKQ'
TOKEN = '9999999999.' + 'a' * 64
WAKE = 'https://faixalab-retomada.onrender.com'
GOOGLE_IDENTITY = 'stub-signed-google-identity'
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
    if path == '/api/health':
        assert route.request.all_headers().get('authorization') == 'Bearer ' + state.get('token', TOKEN)
        if state.get('starting'):
            state['health_checks'] += 1
            if state['health_checks'] >= 2:
                state['server'] = True
        return cors(route, 200, json={'status':'ok', 'engines':{'demucs':True}}) if state['server'] else cors(route, 404)
    if path == '/auth/google/config':
        return cors(route, json={'client_id':'test-client', 'nonce':'nonce'})
    if path == '/auth/google/session':
        return cors(route, json={'api':TOKEN, 'media':TOKEN})
    if path == '/auth/google/portal-session':
        assert route.request.post_data_json['credential'] == GOOGLE_IDENTITY
        if not state['starting']: return cors(route, 404)
        state['exchanges'] += 1
        return cors(route, json={'api':TOKEN, 'media':TOKEN})
    if path == '/api/projects' and not state['server']:
        return cors(route, 503, json={'detail':'Servidor de teste indisponível.'})
    if path == '/api/import/file':
        data = route.request.post_data_buffer
        assert data and AUDIO in data and b'name="options"' in data
        if not state.get('file_only'):
            assert VIDEO.encode() in data
        assert route.request.all_headers().get('authorization') == 'Bearer ' + state.get('token', TOKEN)
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

def test_chromebook_capture(playwright):
    title = 'FaixaLab Tab Capture Test'
    source = '''<!doctype html><meta charset="utf-8"><title>'''+title+'''</title>
    <button id="play">Tocar áudio de teste</button>
    <script>
    let player;
    document.querySelector("#play").onclick = () => {
        const audio = new AudioContext();
        const tone = audio.createOscillator();
        const volume = audio.createGain();
        volume.gain.value = 0.25;
        tone.frequency.value = 440;
        tone.connect(volume).connect(audio.destination);
        tone.start();
        player = audio;
    };
    </script>'''
    browser = playwright.chromium.launch(
        headless=False,
        executable_path=os.environ.get('FAIXALAB_TEST_CHROMIUM'),
        args=['--auto-select-tab-capture-source-by-title='+title],
    )
    try:
        context = browser.new_context(user_agent='Mozilla/5.0 (X11; CrOS x86_64)')
        context.add_init_script(
            'Object.defineProperty(navigator,"userAgentData",{value:undefined});'
            'sessionStorage.setItem('+json.dumps('faixalab-pages-session:'+ORIGIN)+','
            +json.dumps(json.dumps({'api':TOKEN,'media':TOKEN}))+');'
        )
        captures = []
        local_requests = []
        state = {'server':True, 'cloud_imports':0}

        def mock_processing_server(route):
            if route.request.method != 'POST' or not route.request.url.endswith('/api/import/file'):
                return emulate_backend(route, state)
            request = route.request
            assert request.all_headers()['authorization'] == 'Bearer '+TOKEN
            content_type = request.headers['content-type'].encode('ascii')
            envelope = BytesParser(policy=policy.default).parsebytes(
                b'Content-Type: '+content_type+b'\r\nMIME-Version: 1.0\r\n\r\n'+request.post_data_buffer
            )
            form = {part.get_param('name',header='content-disposition'):part for part in envelope.iter_parts()}
            assert 'youtube_url' not in form
            assert json.loads(form['options'].get_content())
            assert form['file'].get_filename() == 'YouTube-aqz-KE-bpKQ.webm'
            assert form['file'].get_content_type() == 'audio/webm'
            captures.append(form['file'].get_payload(decode=True))
            if len(captures) == 1:
                return cors(route, 503, json={'detail':'Servidor temporariamente indisponível no teste.'})
            return cors(route, 202, json={'id':'fixture'})

        def local_request(route):
            local_requests.append(route.request.url)
            route.abort()

        def serve_fixture(route):
            assert route.request.url == VIDEO, route.request.url
            route.fulfill(content_type='text/html; charset=utf-8',body=source)

        context.route(ORIGIN+'/**', mock_processing_server)
        context.route('http://127.0.0.1:*/import', local_request)
        context.route('https://www.youtube.com/watch?*', serve_fixture)
        page = context.new_page()
        page.goto(SITE)
        page.locator('#new-project').click()
        page.locator('[data-source=youtube]').click()
        page.locator('#youtube-url').fill(VIDEO+'&list=RDabc&index=3')
        with context.expect_page() as popup:
            page.locator('#youtube-open-video').click()
        video_page = popup.value
        video_page.wait_for_load_state()
        assert video_page.url == VIDEO
        video_page.locator('#play').click()
        page.bring_to_front()

        button = page.locator('#import-submit')
        expect(button).to_have_text('Compartilhar áudio da aba')
        button.click()
        expect(button).to_have_text('Encerrar e separar', timeout=15000)
        assert not captures
        # Wait for full Opus frames in this real-time browser recording.
        page.wait_for_timeout(2400)
        button.click()
        expect(button).to_have_text('Tentar enviar novamente')
        expect(page.locator('#import-error')).to_contain_text('Áudio obtido neste aparelho')
        button.click()
        expect(page.locator('#import-dialog')).to_be_hidden()
        assert len(captures) == 2 and captures[0] == captures[1]
        assert not local_requests and state['cloud_imports'] == 0

        probe = subprocess.run(
            ['ffprobe','-v','error','-show_entries','stream=codec_type,codec_name','-of','json','-i','pipe:0'],
            input=captures[0], capture_output=True,check=True,
        )
        assert json.loads(probe.stdout)['streams'] == [{'codec_name':'opus','codec_type':'audio'}]
        sound = subprocess.run(
            ['ffmpeg','-v','info','-i','pipe:0','-af','volumedetect','-f','null','-'],
            input=captures[0],capture_output=True,check=True,
        )
        level = re.search(rb'max_volume: (-?\d+(?:\.\d+)?) dB', sound.stderr)
        assert level and float(level[1]) > -30, sound.stderr.decode()[-2000:]
        print('ChromeOS simulado: áudio audível de outra aba, WebM Opus sem vídeo, reenvio idêntico e nenhum importador local', flush=True)
    finally:
        browser.close()


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=os.environ.get('FAIXALAB_TEST_CHROMIUM'))
    try:
        for platform, ua, port, filename in (
            ('Android','Mozilla/5.0 Android',17862,'FaixaLab_Audio_Android.apk'),
            ('Win32','Mozilla/5.0 Windows',17861,'Instalar_FaixaLab_Windows.exe'),
            ('MacIntel','Mozilla/5.0 Macintosh',17861,'Instalar_FaixaLab_macOS_1.2.0.pkg'),
            ('Linux x86_64','Mozilla/5.0 Linux',17861,'Instalar_FaixaLab_Linux_1.2.0.deb'),
            ('Chrome OS','Mozilla/5.0 CrOS',17861,None),
        ):
            page = browser.new_page(user_agent=ua)
            page.add_init_script('Object.defineProperty(navigator,"userAgentData",{value:undefined});Object.defineProperty(navigator,"platform",{value:'+json.dumps(platform)+'});sessionStorage.setItem("faixalab-pages-session:'+ORIGIN+'",'+json.dumps(json.dumps({'api':TOKEN,'media':TOKEN}))+');')
            state={'uploads':0, 'local_audio':0, 'cloud_imports':0, 'active':False, 'server':False, 'port':port, 'ports':[], 'busy':True}
            page.route(ORIGIN+'/**',lambda route:emulate_backend(route,state))
            page.route('http://127.0.0.1:*/import', lambda route:emulate_importer(route,state))
            page.goto(SITE)
            expect(page.locator('#project-list')).to_contain_text('A biblioteca está indisponível', use_inner_text=False)
            expect(page.locator('#project-count')).to_have_text('—', use_inner_text=False)
            if platform == 'Chrome OS':
                expect(page.get_by_role('button', name='Instalar site como app', exact=True)).to_be_visible()
                expect(page.locator('#start-import')).to_be_visible()
                devtools = page.context.new_cdp_session(page)
                errors = devtools.send('Page.getInstallabilityErrors')['installabilityErrors']
                assert errors == [], errors
                manifest = json.loads(devtools.send('Page.getAppManifest')['data'])
                assert manifest['start_url'] == './' and 'id' not in manifest
                page.locator('#install-faixalab').click()
                expect(page.locator('#install-faixalab-dialog')).to_contain_text('Instalar esta página como um app')
                page.locator('#install-faixalab-dialog button').click()
                page.evaluate("""() => {
                    const event = new Event('beforeinstallprompt', {cancelable: true});
                    event.prompt = () => { window.faixaLabPromptShown = true; };
                    event.userChoice = Promise.resolve({outcome: 'accepted'});
                    window.dispatchEvent(event);
                }""")
                page.locator('#install-faixalab').click()
                assert page.evaluate('window.faixaLabPromptShown')
                expect(page.locator('#install-faixalab')).to_be_hidden()
            else:
                expect(page.locator('#install-faixalab')).to_be_hidden()
            page.locator('#new-project').click()
            page.locator('[data-source=youtube]').click()
            assert page.locator('#youtube-import-mode, #youtube-save-local').count() == 0
            page.locator('#youtube-url').fill(VIDEO)
            if platform == 'Chrome OS' and page.locator('#youtube-tab-capture').is_visible():
                page.locator('#youtube-import-setup summary').click()
                page.locator('#youtube-use-local').check()
                expect(page.locator('#youtube-tab-capture')).to_be_hidden()
            page.locator('#import-submit').click()
            expect(page.locator('#import-error')).to_be_visible()
            expect(page.locator('#youtube-import-setup')).to_have_attribute('open','')
            if platform == 'Chrome OS':
                expect(page.locator('#youtube-import-download')).to_be_hidden()
                assert page.locator('#youtube-import-download').get_attribute('href') is None
                page.locator('#youtube-use-file').click()
                expect(page.locator('#file-source')).to_be_visible()
                expect(page.locator('#import-error')).to_be_hidden()
                page.locator('[data-source=youtube]').click()
            else:
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
        page = browser.new_page(user_agent='Mozilla/5.0 iPhone')
        page.goto(SITE)
        expect(page.locator('[data-source=youtube]')).to_be_disabled()
        expect(page.locator('#youtube-import-download')).not_to_be_visible()
        page.close()
        if len(sys.argv) > 2:
            server.RequestHandlerClass.keywords['directory'] = sys.argv[2]
            page = browser.new_page(user_agent='Mozilla/5.0 Android', viewport={'width': 393, 'height': 800})
            page.add_init_script('Object.defineProperty(navigator,"userAgentData",{value:undefined});sessionStorage.setItem("faixalab-google-identity:'+ORIGIN+'",'+json.dumps(json.dumps({'credential':GOOGLE_IDENTITY,'expires':9999999999}))+');')
            state = {'uploads':0, 'local_audio':0, 'cloud_imports':0, 'active':True, 'server':False,
                     'port':17863, 'ports':[], 'busy':False, 'wake_calls':0, 'starting':False, 'health_checks':0,
                     'exchanges':0}
            page.route(ORIGIN+'/**', lambda route: emulate_backend(route, state))
            page.route('http://127.0.0.1:*/import', lambda route: emulate_importer(route, state))

            def wake(route):
                if route.request.method == 'OPTIONS': return cors(route, 204)
                assert route.request.url == WAKE + '/wake'
                assert route.request.all_headers().get('authorization') == 'Bearer ' + GOOGLE_IDENTITY
                assert state['local_audio'] == 1 and state['uploads'] == 0
                state['wake_calls'] += 1
                if state['wake_calls'] == 1:
                    return cors(route, 503, json={'detail':'A retomada falhou neste teste.'})
                state['starting'] = True
                return cors(route, 202, json={'status':'starting'})

            page.route(WAKE+'/**', wake)
            page.goto(SITE)
            page.locator('#new-project').click()
            page.locator('[data-source=youtube]').click()
            page.locator('#youtube-url').fill(VIDEO)
            page.locator('#import-submit').click()
            expect(page.locator('#import-error')).to_contain_text('Áudio obtido neste aparelho. A retomada falhou')
            assert state['uploads'] == 0 and state['local_audio'] == 1 and state['wake_calls'] == 1
            page.locator('#import-submit').click()
            expect(page.locator('#import-submit')).to_have_text('Aguardando o servidor de separação…')
            expect(page.locator('#import-dialog')).not_to_be_visible()
            assert state['uploads'] == 1 and state['local_audio'] == 1 and state['wake_calls'] == 2 and state['exchanges'] == 1
            print('Android com Codespace desligado: uma extração, retomada e um upload após verificar o Demucs', flush=True)
            page.close()
            page = browser.new_page(user_agent='Mozilla/5.0 (X11; CrOS x86_64)')
            page.add_init_script('Object.defineProperty(navigator,"userAgentData",{value:undefined});sessionStorage.setItem("faixalab-pages-session:'+ORIGIN+'",'+json.dumps(json.dumps({'api':TOKEN,'media':TOKEN}))+');')
            state = {'uploads':0, 'local_audio':0, 'server':True, 'file_only':True}
            page.route(ORIGIN+'/**', lambda route: emulate_backend(route, state))
            page.goto(SITE)
            page.locator('#start-import').click()
            page.locator('#audio-file').set_input_files(
                {'name':'FaixaLab.wav', 'mimeType':'audio/wav', 'buffer':AUDIO})
            page.locator('#import-submit').click()
            expect(page.locator('#import-dialog')).not_to_be_visible()
            assert state['uploads'] == 1 and state['local_audio'] == 0
            print('Chromebook: instalação web e envio de arquivo sem importador nativo', flush=True)
            page.close()
    finally:
        browser.close()
        try:
            if sys.exc_info()[0] is None and os.environ.get('FAIXALAB_TEST_TAB_CAPTURE') == '1':
                server.RequestHandlerClass.keywords['directory'] = sys.argv[1]
                test_chromebook_capture(p)
        finally:
            server.shutdown()
