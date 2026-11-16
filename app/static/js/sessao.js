'use strict';
/* Sessão: sem limite de inatividade. A pessoa só sai do sistema ao fechar o navegador (ou fazer logoff).
   Se o navegador for fechado e reaberto com a sessão restaurada, nenhuma aba estava viva: uma "batida" gravada
   pelas abas abertas denuncia isso e a sessão é encerrada. */
(() => {
  const csrf = (document.querySelector('meta[name=csrf]') || {}).content || '';
  let encerrando = false;
  window.nuclelesteSessao = (resposta) => {
    const destino = resposta.headers.get('X-Login-URL') ||
      (resposta.redirected && new URL(resposta.url, location.href).pathname === '/login' ? resposta.url : '') ||
      (resposta.status === 401 ? '/login' : '');
    if (!destino) return false;
    const login = new URL(destino, location.href);
    if (login.origin !== location.origin || login.pathname !== '/login') return false;
    if (!encerrando) { encerrando = true; window.location.replace(login.href); }
    return true;
  };
  const consultar = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const resposta = await consultar(...args);
    if (new URL(resposta.url || location.href, location.href).origin === location.origin) window.nuclelesteSessao(resposta);
    return resposta;
  };
  const ler = (k) => { try { return Number(localStorage.getItem(k)) || 0; } catch (e) { return 0; } };
  const gravar = (k, v) => { try { localStorage.setItem(k, String(v)); } catch (e) { /* armazenamento bloqueado */ } };

  const batida = ler('nl_batida');
  if (batida && Date.now() - batida > 75000) {
    encerrar();
    return;
  }
  const bater = () => gravar('nl_batida', Date.now());
  bater();
  setInterval(bater, 4000);
  window.addEventListener('pagehide', bater);

  async function encerrar() {
    if (encerrando) return;
    encerrando = true;
    let destino = '/login';
    try {
      const resposta = await fetch('/logout', {method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': csrf}, keepalive: true});
      const login = new URL(resposta.headers.get('X-Login-URL') || '/login', location.href);
      if (login.origin === location.origin && login.pathname === '/login') destino = login.href;
    } catch (e) { /* o navegador descarta a sessão ao fechar */ }
    try { localStorage.removeItem('nl_batida'); } catch (e) { /* ignorado */ }
    window.location.replace(destino);
  }
})();
