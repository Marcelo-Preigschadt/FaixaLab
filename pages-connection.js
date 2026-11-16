'use strict';
(() => {
  const { backend, wakeServer } = window.faixaLabPagesConfig;
  const authServer = wakeServer || backend;
  const storageKey = 'faixalab-pages-session:' + backend;
  const identityKey = 'faixalab-google-identity:' + backend;
  const signInMessage = 'Entre para acessar sua biblioteca e separar músicas.';
  const unavailableMessage = 'O servidor de separação está indisponível.';
  const fragment = new URLSearchParams(location.hash.slice(1));
  const api = fragment.get('faixalab_api');
  const media = fragment.get('faixalab_media');
  const tokenPattern = /^\d{1,12}(?:\.[0-9a-f]{64}){1,2}$/;
  let session;
  let identity;
  try {
    session = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    if (wakeServer) identity = JSON.parse(sessionStorage.getItem(identityKey) || 'null');
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
  const hasIdentity = () => wakeServer && typeof identity?.credential === 'string'
    && identity.expires > Date.now() / 1000;
  let checkedLibrary = false;
  let statusText = '';
  let unavailable = false;
  let googleSetup;
  let renewingSession;
  function status(message) {
    statusText = message;
    const banner = document.getElementById('pages-connection');
    if (!banner) return;
    banner.hidden = !message;
    banner.querySelector('span').textContent = message;
    document.getElementById('pages-signout').hidden = Boolean(message) || !(connected() || hasIdentity());
  }
  const error = (detail, statusCode) => new Response(JSON.stringify({ detail }), { status: statusCode });

  function markUnavailable() {
    unavailable = true;
    status(unavailableMessage);
  }

  function showRetry() {
    document.getElementById('pages-retry').hidden = false;
  }

  function clearSession() {
    session = null;
    googleSetup = null;
    try { sessionStorage.removeItem(storageKey); } catch {}
  }

  function saveSession(result) {
    if (!tokenPattern.test(result?.api) || !tokenPattern.test(result?.media)) return false;
    session = { api: result.api, media: result.media };
    try { sessionStorage.setItem(storageKey, JSON.stringify(session)); } catch {}
    return true;
  }

  async function renewGatewaySession() {
    if (!hasIdentity()) return 'expired';
    renewingSession ??= (async () => {
      try {
        const response = await fetch(backend + '/auth/google/portal-session', {
          method: 'POST', credentials: 'omit', redirect: 'error', cache: 'no-store',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ credential: identity.credential }),
          signal: AbortSignal.timeout(8000),
        });
        if (response.status === 401) return 'expired';
        return response.ok && saveSession(await response.json()) ? 'connected' : 'offline';
      } catch { return 'offline'; }
    })().finally(() => { renewingSession = null; });
    return renewingSession;
  }

  async function googleLogin() {
    let config;
    try {
      const response = await fetch(authServer + '/auth/google/config', { credentials: 'omit', redirect: 'error',
        cache: 'no-store', signal: AbortSignal.timeout(wakeServer ? 80000 : 5000) });
      if (!response.ok) return false;
      config = await response.json();
    } catch { return false; }
    if (!config?.client_id || !config.nonce) {
      status('A entrada com Google ainda não foi configurada para o FaixaLab online.');
      showRetry();
      return true;
    }

    const buttons = ['pages-google', 'import-google'].map(id => document.getElementById(id)).filter(Boolean);
    unavailable = false;
    status('Entre com sua conta Google para acessar sua biblioteca e separar músicas.');

    async function signIn({ credential }) {
      buttons.forEach(button => { button.hidden = true; });
      status('Verificando sua conta Google…');
      try {
        const response = await fetch(authServer + '/auth/google/session', {
          method: 'POST', credentials: 'omit', redirect: 'error', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ credential, nonce: config.nonce }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Não foi possível entrar.');
        if (wakeServer) {
          if (!Number.isInteger(result.expires) || result.expires <= Date.now() / 1000) throw new Error('Sessão inválida.');
          clearSession();
          identity = { credential, expires: result.expires };
          try { sessionStorage.setItem(identityKey, JSON.stringify(identity)); } catch {}
        } else if (!saveSession(result)) {
          throw new Error('Sessão inválida.');
        }
        googleSetup = null;
        document.getElementById('pages-retry').hidden = true;
        status('');
        document.dispatchEvent(new Event('faixalab-session-ready'));
        document.dispatchEvent(new Event('faixalab-refresh'));
      } catch (failure) {
        googleSetup = null;
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
      buttons.forEach(button => {
        button.hidden = false;
        button.replaceChildren();
        google.accounts.id.renderButton(button, { theme: 'outline', size: 'large', locale: 'pt-BR' });
      });
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
    if (wakeServer && !googleSetup) status('Conectando ao login do FaixaLab…');
    googleSetup ??= googleLogin();
    if (!await googleSetup) {
      markUnavailable();
      showRetry();
    }
  }

  async function sessionExpired() {
    clearSession();
    identity = null;
    try { sessionStorage.removeItem(identityKey); } catch {}
    await beginSignIn();
    return error('Entre com Google para continuar o envio.', 401);
  }

  async function confirmSeparation(notify = () => {}) {
    const request = async (url, method, timeout, token) => {
      try {
        return await fetch(url, { method, headers: { Authorization: 'Bearer ' + token },
          cache: 'no-store', credentials: 'omit', redirect: 'error',
          signal: AbortSignal.timeout(timeout) });
      } catch { return null; }
    };
    const health = async () => {
      const check = () => request(backend + '/api/health', 'GET', 4500, session.api);
      let response = connected() ? await check() : null;
      if (!connected() || response?.status === 401) {
        clearSession();
        const renewed = await renewGatewaySession();
        if (renewed !== 'connected') return renewed;
        response = await check();
      }
      if (response?.status === 401) return 'expired';
      const result = response?.ok ? await response.json().catch(() => null) : null;
      return result?.status === 'ok' && result.engines?.demucs === true ? 'ready' : 'offline';
    };
    let readiness = await health();
    if (readiness === 'ready') return null;
    if (readiness === 'expired' || !hasIdentity()) return sessionExpired();

    const update = message => { status(message); notify(message); };
    update('Iniciando o servidor de separação…');
    const response = await request(wakeServer + '/wake', 'POST', 80000, identity.credential);
    if (response?.status === 401) return sessionExpired();
    if (!response?.ok) {
      const result = await response?.json().catch(() => null);
      markUnavailable();
      showRetry();
      return error(typeof result?.detail === 'string' ? result.detail : 'Não foi possível solicitar a retomada do servidor.', 503);
    }

    update('Aguardando o servidor de separação…');
    const deadline = Date.now() + 150000;
    do {
      readiness = await health();
      if (readiness === 'ready') {
        update('Enviando áudio para separação…');
        return null;
      }
      if (readiness === 'expired') return sessionExpired();
      await new Promise(resolve => setTimeout(resolve, 2500));
    } while (Date.now() < deadline);

    markUnavailable();
    showRetry();
    return error('O servidor ainda está iniciando.', 503);
  }

  window.faixaLabPages = {
    async request(path, { onWaiting, ...options }) {
      if (dictionary.has(path)) return fetch(dictionary.get(path), options);
      const library = path === '/api/projects';
      const initialCheck = library && !checkedLibrary;
      if (library) checkedLibrary = true;
      if (!(connected() || hasIdentity())) {
        await beginSignIn();
        if (!statusText) status(signInMessage);
        if (library) return new Response('[]');
        return error(statusText, unavailable ? 503 : 401);
      }
      const endpoint = new URL(path, backend);
      if (endpoint.origin !== backend || !endpoint.pathname.startsWith('/api/')) return error('Rota inválida.', 400);
      if (wakeServer && path === '/api/import/file' && options.method === 'POST') {
        const unavailable = await confirmSeparation(onWaiting);
        if (unavailable) return unavailable;
      } else if (!connected()) {
        const renewed = await renewGatewaySession();
        if (renewed === 'expired') return sessionExpired();
        if (renewed !== 'connected') {
          markUnavailable();
          showRetry();
          return initialCheck ? new Response('[]') : error(statusText, 503);
        }
      }
      const send = () => {
        const headers = new Headers(options.headers);
        headers.set('Authorization', 'Bearer ' + session.api);
        return fetch(endpoint, { ...options, headers, credentials: 'omit', redirect: 'error' });
      };
      try {
        let response = await send();
        if (response.status === 401 && hasIdentity() && await renewGatewaySession() === 'connected') {
          response = await send();
        }
        if (response.status === 401) {
          await sessionExpired();
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
    document.getElementById('pages-retry').addEventListener('click', async () => {
      googleSetup = null;
      document.getElementById('pages-retry').hidden = true;
      if (wakeServer && (connected() || hasIdentity()) && await confirmSeparation()) return;
      document.dispatchEvent(new Event('faixalab-refresh'));
    });
    document.getElementById('pages-signout').addEventListener('click', () => {
      try {
        sessionStorage.removeItem(storageKey);
        sessionStorage.removeItem(identityKey);
      } catch {}
      window.google?.accounts?.id?.disableAutoSelect();
      location.reload();
    });
    status(statusText || (connected() ? '' : signInMessage));
  });
})();
