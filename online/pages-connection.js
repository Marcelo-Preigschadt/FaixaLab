'use strict';
(() => {
  const { backend } = window.faixaLabPagesConfig;
  const storageKey = 'faixalab-pages-session:' + backend;
  const signInMessage = 'Entre para acessar sua biblioteca e separar músicas.';
  const unavailableMessage = 'O servidor de separação está indisponível.';
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
  let checkedLibrary = false;
  let statusText = '';
  let unavailable = false;
  let googleSetup;
  function status(message) {
    statusText = message;
    const banner = document.getElementById('pages-connection');
    if (!banner) return;
    banner.hidden = !message;
    banner.querySelector('span').textContent = message;
    document.getElementById('pages-signout').hidden = Boolean(message) || !connected();
  }
  const error = (detail, statusCode) => new Response(JSON.stringify({ detail }), { status: statusCode });

  function markUnavailable() {
    unavailable = true;
    status(unavailableMessage);
  }

  function showRetry() {
    document.getElementById('pages-retry').hidden = false;
  }

  async function googleLogin() {
    let config;
    try {
      const response = await fetch(backend + '/auth/google/config', { credentials: 'omit', redirect: 'error',
                                                                     cache: 'no-store', signal: AbortSignal.timeout(5000) });
      if (!response.ok) return false;
      config = await response.json();
    } catch { return false; }
    if (!config?.client_id || !config.nonce) {
      status('A entrada com Google ainda não foi configurada para o FaixaLab online.');
      showRetry();
      return true;
    }

    const button = document.getElementById('pages-google');
    unavailable = false;
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
        session = { api: result.api, media: result.media };
        try { sessionStorage.setItem(storageKey, JSON.stringify(session)); } catch {}
        googleSetup = null;
        document.getElementById('pages-retry').hidden = true;
        status('');
        document.dispatchEvent(new Event('faixalab-refresh'));
      } catch (failure) {
        status(failure.message);
        showRetry();
      }
    }

    function renderGoogleButton() {
      if (!window.google?.accounts?.id) {
        status('O login com Google está indisponível.');
        showRetry();
        return;
      }
      google.accounts.id.initialize({ client_id: config.client_id, nonce: config.nonce, callback: signIn });
      button.hidden = false;
      google.accounts.id.renderButton(button, { theme: 'outline', size: 'large', locale: 'pt-BR' });
    }
    if (window.google?.accounts?.id) {
      renderGoogleButton();
      return true;
    }
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client?hl=pt-BR';
    script.async = true;
    script.onload = renderGoogleButton;
    script.onerror = () => {
      status('O login com Google está indisponível.');
      showRetry();
    };
    document.head.append(script);
    return true;
  }

  async function beginSignIn() {
    googleSetup ??= googleLogin();
    if (!await googleSetup) {
      markUnavailable();
      showRetry();
    }
  }

  window.faixaLabPages = {
    async request(path, options) {
      if (dictionary.has(path)) return fetch(dictionary.get(path), options);
      const library = path === '/api/projects';
      const initialCheck = library && !checkedLibrary;
      if (library) checkedLibrary = true;
      if (!connected()) {
        await beginSignIn();
        if (!statusText) status(signInMessage);
        if (library) return new Response('[]');
        return error(statusText, unavailable ? 503 : 401);
      }
      const endpoint = new URL(path, backend);
      if (endpoint.origin !== backend || !endpoint.pathname.startsWith('/api/')) return error('Rota inválida.', 400);
      const headers = new Headers(options.headers);
      headers.set('Authorization', 'Bearer ' + session.api);
      try {
        const response = await fetch(endpoint, { ...options, headers, credentials: 'omit', redirect: 'error' });
        if (response.status === 401) {
          session = null;
          try { sessionStorage.removeItem(storageKey); } catch {}
          status('A sessão expirou. Entre novamente no FaixaLab.');
          await beginSignIn();
          if (initialCheck) {
            return new Response('[]');
          }
        } else if (response.ok) {
          unavailable = false;
          document.getElementById('pages-retry').hidden = true;
          status('');
        } else if (response.status >= 500 || (library && response.status === 404)) {
          markUnavailable();
          showRetry();
        }
        return response;
      } catch (failure) {
        if (failure.name === 'AbortError') throw failure;
        markUnavailable();
        showRetry();
        if (initialCheck) return new Response('[]');
        return error(statusText, 503);
      }
    },
    libraryNotice() {
      if (unavailable) return 'A biblioteca está indisponível enquanto o servidor não responde.';
      if (!connected()) return 'Entre com Google para acessar sua biblioteca.';
      return '';
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
    document.getElementById('pages-retry').addEventListener('click', () => {
      googleSetup = null;
      document.getElementById('pages-retry').hidden = true;
      document.dispatchEvent(new Event('faixalab-refresh'));
    });
    document.getElementById('pages-signout').addEventListener('click', () => {
      try {
        sessionStorage.removeItem(storageKey);
      } catch {}
      window.google?.accounts?.id?.disableAutoSelect();
      location.reload();
    });
    status(statusText || (connected() ? '' : signInMessage));
  });
})();
