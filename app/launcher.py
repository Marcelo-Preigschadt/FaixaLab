"""FaixaLab desktop launcher: local processing, browser-based interface."""
import argparse
import os
import socket
import threading
import webbrowser
import sys
import time
import atexit


def main():
    # pythonw.exe has no console streams; keep native-window startup logs usable.
    if sys.stdout is None or sys.stderr is None:
        from faixalab.storage import ROOT
        log = (ROOT / 'FaixaLab.log').open('a', encoding='utf-8', buffering=1)
        if sys.stdout is None:
            sys.stdout = log
        if sys.stderr is None:
            sys.stderr = log
    parser = argparse.ArgumentParser(description='FaixaLab — faixas, cifras e letra')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    from filelock import FileLock, Timeout
    from faixalab.storage import ROOT
    instance_lock = FileLock(str(ROOT / 'FaixaLab.lock'), timeout=0)
    try:
        instance_lock.acquire()
    except Timeout:
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, 'O FaixaLab já está aberto. Volte à janela existente.', 'FaixaLab', 0x40)
        else:
            print('O FaixaLab já está aberto.')
        return
    atexit.register(instance_lock.release)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', args.port))
        port = sock.getsockname()[1]
    os.environ['FAIXALAB_ORIGIN'] = f'http://127.0.0.1:{port}'
    import uvicorn
    print(f'FaixaLab: http://127.0.0.1:{port}')
    if sys.platform == 'win32' and not args.no_browser:
        server = uvicorn.Server(uvicorn.Config('faixalab.app:app', host='127.0.0.1', port=port, access_log=False, use_colors=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(200):
            if server.started:
                break
            time.sleep(.05)
        try:
            import webview
            webview.settings['ALLOW_DOWNLOADS'] = True
            webview.create_window('FaixaLab — seu estúdio de estudo', f'http://127.0.0.1:{port}',
                                  width=1440, height=960, min_size=(900, 680), background_color='#10141b', text_select=True)
            webview.start()
        except Exception:
            webbrowser.open(f'http://127.0.0.1:{port}')
            thread.join()
        finally:
            from faixalab.solo_tabs import cancel as cancel_tabs
            cancel_tabs()
            from faixalab.pipeline import CANCELLATIONS
            for event in list(CANCELLATIONS.values()):
                event.set()
            server.should_exit = True
    else:
        if not args.no_browser:
            threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()
        uvicorn.run('faixalab.app:app', host='127.0.0.1', port=port, access_log=False)


if __name__ == '__main__':
    main()
