'use strict';
(() => {
  const { backend, connect } = window.faixaLabPagesConfig;
  const storageKey = 'faixalab-pages-session:' + backend;
  const rememberedKey = 'faixalab-pages-connected:' + backend;
  const attemptKey = 'faixalab-pages-reconnecting:' + backend;
  const signInMessage = 'Entre para acessar sua biblioteca e separar músicas.';
  const unavailableMessage = 'Servidor de processamento indisponível. Tente novamente em instantes.';
  const fragment = new URLSearchParams(location.hash.slice(1));
  const api = fragment.get('faixalab_api');
  const media = fragment.get('faixalab_media');
  const tokenPattern = /^\d{1,12}(?:\.[0-9a-f]{64}){1,2}$/;
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
  const ownerSession = () => session?.api?.split('.').length === 2;
  let checkedLibrary = false;
  let statusText = '';
  let googleSetup;
  const ownerControl = () => document.querySelector('#pages-owner-connect, #pages-connection a');
  function status(message) {
    statusText = message;
    const banner = document.getElementById('pages-connection');
    if (!banner) return;
    banner.hidden = !message;
    banner.querySelector('span').textContent = message;
    document.getElementById('new-project').disabled = Boolean(message);
    document.getElementById('start-import').disabled = Boolean(message);
    document.getElementById('pages-signout').hidden = Boolean(message) || !connected();
  }
  const error = (detail, statusCode) => new Response(JSON.stringify({ detail }), { status: statusCode });

  function rememberConnection() {
    if (ownerSession()) {
      try { localStorage.setItem(rememberedKey, '1'); } catch {}
    }
    try { sessionStorage.removeItem(attemptKey); } catch {}
  }

  async function googleLogin() {
    let config;
    try {
      const response = await fetch(backend + '/auth/google/config', { credentials: 'omit', redirect: 'error',
                                                                     cache: 'no-store', signal: AbortSignal.timeout(5000) });
      if (!response.ok) return false;
      config = await response.json();
    } catch { return false; }
    if (!config.client_id) return false;

    const button = document.getElementById('pages-google');
    ownerControl().hidden = true;
    status('Entre com sua conta Google para acessar sua biblioteca e separar músicas.');

    async function signIn({ credential }) {
      button.hidden = true;
      status('Verificando sua conta Google…');
      try {
        const response = await fetch(backend + '/auth/google/session', {
          method: 'POST', credentials: 'omit', redirect: 'error', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ credential, nonce: config.nonce }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Não foi possível entrar.');
        if (!tokenPattern.test(result.api) || !tokenPattern.test(result.media)) throw new Error('Sessão inválida.');
        sessionStorage.setItem(storageKey, JSON.stringify({ api: result.api, media: result.media }));
        location.reload();
      } catch (failure) {
        status(`${failure.message} Recarregue o FaixaLab para tentar novamente.`);
      }
    }

    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client?hl=pt-BR';
    script.async = true;
    script.onload = () => {
      if (!window.google?.accounts?.id) {
        status('O login com Google está indisponível. Recarregue a página e tente novamente.');
        return;
      }
      google.accounts.id.initialize({ client_id: config.client_id, nonce: config.nonce, callback: signIn });
      button.hidden = false;
      google.accounts.id.renderButton(button, { theme: 'outline', size: 'large', locale: 'pt-BR' });
    };
    script.onerror = () => status('O login com Google está indisponível. Recarregue a página e tente novamente.');
    document.head.append(script);
    return true;
  }

  async function beginSignIn() {
    googleSetup ??= googleLogin();
    if (!await googleSetup) await reconnect();
  }

  async function connectOwner() {
    const button = ownerControl();
    if (button.disabled) return false;
    button.disabled = true;
    status('Verificando a conexão com o servidor…');
    try {
      const response = await fetch(backend + '/health', { credentials: 'omit', redirect: 'error', cache: 'no-store',
                                                         signal: AbortSignal.timeout(5000) });
      if (response.ok && (await response.json()).service === 'faixalab-pages') {
        location.replace(connect);
        return true;
      }
    } catch {}
    button.disabled = false;
    status(unavailableMessage);
    return false;
  }

  async function reconnect() {
    try {
      if (localStorage.getItem(rememberedKey) !== '1' || sessionStorage.getItem(attemptKey)) return false;
      sessionStorage.setItem(attemptKey, '1');
    } catch { return false; }
    return connectOwner();
  }

  window.faixaLabPages = {
    async request(path, options) {
      if (dictionary.has(path)) return fetch(dictionary.get(path), options);
      const library = path === '/api/projects';
      const initialCheck = library && !checkedLibrary;
      if (library) checkedLibrary = true;
      if (!connected()) {
        if (initialCheck) await beginSignIn();
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
          status('A sessão expirou. Entre novamente no FaixaLab.');
          if (initialCheck) {
            await beginSignIn();
            return new Response('[]');
          }
          googleSetup ??= googleLogin();
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
    ownerControl().addEventListener('click', event => {
      event.preventDefault();
      void connectOwner();
    });
    document.getElementById('pages-signout').addEventListener('click', () => {
      try {
        sessionStorage.removeItem(storageKey);
        sessionStorage.removeItem(attemptKey);
        localStorage.removeItem(rememberedKey);
      } catch {}
      window.google?.accounts?.id?.disableAutoSelect();
      location.reload();
    });
    status(statusText || (connected() ? '' : signInMessage));
  });
})();
