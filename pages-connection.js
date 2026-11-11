'use strict';
(() => {
  const { backend, connect } = window.faixaLabPagesConfig;
  const storageKey = 'faixalab-pages-session:' + backend;
  const rememberedKey = 'faixalab-pages-connected:' + backend;
  const attemptKey = 'faixalab-pages-reconnecting:' + backend;
  const signInMessage = 'Conecte o Codespace pelo GitHub para acessar seus projetos e separar músicas.';
  const unavailableMessage = 'Codespace indisponível. Abra o ambiente e conecte novamente.';
  const fragment = new URLSearchParams(location.hash.slice(1));
  const api = fragment.get('faixalab_api');
  const media = fragment.get('faixalab_media');
  const tokenPattern = /^\d{1,12}\.[0-9a-f]{64}$/;
  let session;
  try {
    session = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
  } catch {}
  if (tokenPattern.test(api) && tokenPattern.test(media)) {
    session = { api, media };
    try { sessionStorage.setItem(storageKey, JSON.stringify(session)); } catch {}
  }
  if (api || media) history.replaceState(null, '', location.pathname + location.search);

  const dictionary = new Map([['/api/chord-dictionary', './chord-dictionary.json'],
                              ['/api/instruments', './instruments.json']]);
  const connected = () => tokenPattern.test(session?.api) && tokenPattern.test(session?.media)
    && Number(session.api.split('.')[0]) > Date.now() / 1000;
  let checkedLibrary = false;
  let statusText = '';
  function status(message) {
    statusText = message;
    const banner = document.getElementById('pages-connection');
    if (!banner) return;
    banner.hidden = !message;
    banner.querySelector('span').textContent = message;
    document.getElementById('new-project').disabled = Boolean(message);
  }
  const error = (detail, statusCode) => new Response(JSON.stringify({ detail }), { status: statusCode });

  function rememberConnection() {
    try { localStorage.setItem(rememberedKey, '1'); } catch {}
    try { sessionStorage.removeItem(attemptKey); } catch {}
  }

  async function reconnect() {
    try {
      if (localStorage.getItem(rememberedKey) !== '1' || sessionStorage.getItem(attemptKey)) return false;
      sessionStorage.setItem(attemptKey, '1');
    } catch { return false; }
    status('Reconectando ao Codespace pelo GitHub…');
    try {
      const response = await fetch(backend + '/health', { credentials: 'omit', redirect: 'error', cache: 'no-store',
                                                         signal: AbortSignal.timeout(5000) });
      if (response.ok && (await response.json()).service === 'faixalab-pages') {
        location.replace(connect);
        return true;
      }
    } catch {}
    status(unavailableMessage);
    return false;
  }

  window.faixaLabPages = {
    async request(path, options) {
      if (dictionary.has(path)) return fetch(dictionary.get(path), options);
      const library = path === '/api/projects';
      const initialCheck = library && !checkedLibrary;
      if (library) checkedLibrary = true;
      if (!connected()) {
        if (initialCheck) await reconnect();
        if (!statusText) status(signInMessage);
        if (library) return new Response('[]');
        return error(statusText, 401);
      }
      const endpoint = new URL(path, backend);
      if (endpoint.origin !== backend || !endpoint.pathname.startsWith('/api/')) return error('Rota inválida.', 400);
      const headers = new Headers(options.headers);
      headers.set('Authorization', 'Bearer ' + session.api);
      try {
        const response = await fetch(endpoint, { ...options, headers, credentials: 'omit', redirect: 'error' });
        if (response.status === 401) {
          status('A sessão expirou. Conecte o Codespace novamente.');
          if (initialCheck && await reconnect()) return new Response('[]');
        } else if (response.ok) {
          if (library) rememberConnection();
          status('');
        }
        return response;
      } catch (failure) {
        if (failure.name === 'AbortError') throw failure;
        status(unavailableMessage);
        return error(statusText, 503);
      }
    },
    mediaUrl(path) {
      if (!connected()) return '#';
      const url = new URL(path, backend);
      if (url.origin !== backend || !url.pathname.startsWith('/api/projects/')) return '#';
      url.searchParams.set('access', session.media);
      return url.href;
    },
  };

  document.addEventListener('DOMContentLoaded', () => {
    const banner = document.getElementById('pages-connection');
    banner.querySelector('a').href = connect;
    status(statusText || (connected() ? '' : signInMessage));
  });
})();
