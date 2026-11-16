'use strict';
/* Tutorial animado da NucleAI. O roteiro vem pronto do servidor (personalizado pelos módulos do usuário) em
   <script id="tutorial-dados">. A tela escurece, só o alvo fica iluminado e piscando, e a NucleAI anda até ele,
   aponta, pulsa, abre e fecha a boca enquanto fala e dança com os olhos. Abre sozinho no primeiro acesso. */
(() => {
  const dadosEl = document.getElementById('tutorial-dados');
  if (!dadosEl) return;
  let D;
  try { D = JSON.parse(dadosEl.textContent); } catch (e) { return; }
  const passos = D.passos || [];
  if (!passos.length) return;
  const reduz = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const NS = 'http://www.w3.org/2000/svg';

  let ui = null;          // elementos da interface (criados na primeira vez)
  let atual = 0;
  let ativo = false;
  let timerTexto = null;
  let alvoMarcado = null;
  let desfazer = [];      // o que foi aberto/mostrado só para o tutorial e precisa voltar ao que era
  let chuvaTimer = null;

  const MASCOTE = `
<svg viewBox="0 0 128 128" aria-hidden="true">
  <defs><linearGradient id="tmfundo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3a9a5c"/><stop offset="1" stop-color="#1d4f30"/></linearGradient></defs>
  <g class="tm-corpo">
    <circle cx="64" cy="64" r="64" fill="url(#tmfundo)"/>
    <g class="tm-orbitas">
      <g fill="none" stroke="#bfe8cd" stroke-width="3" opacity=".85">
        <ellipse cx="64" cy="64" rx="54" ry="20"/>
        <ellipse cx="64" cy="64" rx="54" ry="20" transform="rotate(60 64 64)"/>
        <ellipse cx="64" cy="64" rx="54" ry="20" transform="rotate(120 64 64)"/>
      </g>
      <circle cx="118" cy="64" r="5" fill="#fff"/><circle cx="37" cy="17.2" r="5" fill="#fff"/><circle cx="37" cy="110.8" r="5" fill="#fff"/>
    </g>
    <line x1="64" y1="40" x2="64" y2="28" stroke="#fff" stroke-width="4" stroke-linecap="round"/>
    <circle class="tm-antena" cx="64" cy="24" r="6" fill="#ffe28a"/>
    <rect x="32" y="40" width="64" height="52" rx="18" fill="#fff"/>
    <rect x="26" y="56" width="8" height="20" rx="4" fill="#bfe8cd"/><rect x="94" y="56" width="8" height="20" rx="4" fill="#bfe8cd"/>
    <g class="tm-olhar">
      <g class="tm-olho"><circle cx="51" cy="62" r="9" fill="#eaf6ee" stroke="#bfe8cd" stroke-width="1.5"/>
        <g class="tm-pupila"><circle cx="51" cy="62" r="5.2" fill="#1d4f30"/><circle cx="52.8" cy="60.2" r="1.8" fill="#fff"/></g></g>
      <g class="tm-olho"><circle cx="77" cy="62" r="9" fill="#eaf6ee" stroke="#bfe8cd" stroke-width="1.5"/>
        <g class="tm-pupila b"><circle cx="77" cy="62" r="5.2" fill="#1d4f30"/><circle cx="78.8" cy="60.2" r="1.8" fill="#fff"/></g></g>
    </g>
    <path class="tm-boca" d="M50 77 Q64 91 78 77" fill="none" stroke="#1d4f30" stroke-width="4" stroke-linecap="round"/>
    <ellipse class="tm-boca-aberta" cx="64" cy="81" rx="9" ry="7" fill="#1d4f30"/>
    <circle cx="44" cy="75" r="4" fill="#ffb4a8" opacity=".75"/><circle cx="84" cy="75" r="4" fill="#ffb4a8" opacity=".75"/>
  </g>
</svg>`;
  const SETA = '<svg viewBox="0 0 34 34"><path d="M4 17h20M16 7l10 10-10 10" fill="none" stroke="#ffe28a" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function montar() {
    if (ui) return;
    const bloqueio = el('div', 'tut-bloqueio');
    const foco = el('div', 'tut-foco');
    const seta = el('div', 'tut-seta', SETA);
    const palco = el('div', 'tut-palco');
    palco.setAttribute('role', 'dialog');
    palco.setAttribute('aria-label', 'Tutorial da NucleAI');
    const mascote = el('div', 'tut-mascote', MASCOTE);
    const balao = el('div', 'tut-balao');
    const passo = el('p', 'tut-passo');
    const titulo = el('h3', 'tut-titulo');
    const texto = el('p', 'tut-texto');
    texto.setAttribute('aria-live', 'polite');
    const barra = el('div', 'tut-barra', '<i></i>');
    const acoes = el('div', 'tut-acoes');
    const ant = el('button', 'tut-ant', '← Voltar'); ant.type = 'button';
    const prox = el('button', 'tut-prox', 'Próximo →'); prox.type = 'button';
    const pular = el('button', 'tut-pular', 'Pular tutorial'); pular.type = 'button';
    acoes.append(ant, prox, pular);
    balao.append(passo, titulo, texto, barra, acoes);
    palco.append(mascote, balao);
    document.body.append(bloqueio, foco, seta, palco);
    ui = {bloqueio, foco, seta, palco, mascote, balao, passo, titulo, texto, barra: barra.firstChild, ant, prox, pular};

    prox.addEventListener('click', () => (atual >= passos.length - 1 ? encerrar() : ir(atual + 1)));
    ant.addEventListener('click', () => ir(atual - 1));
    pular.addEventListener('click', () => encerrar());
    balao.addEventListener('click', (e) => { if (!e.target.closest('button')) mostrarTextoInteiro(); });
    bloqueio.addEventListener('click', mostrarTextoInteiro);
    window.addEventListener('resize', () => { if (ativo) posicionar(passos[atual]); });
  }

  // ------------------------------------------------------------------ alvo
  function visivel(e) {
    if (!e) return false;
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2 && e.getClientRects().length > 0 && r.bottom > 0 && r.right > 0;
  }

  function abrirGrupo(cab) {
    const itens = cab && cab.nextElementSibling;
    if (itens && itens.hasAttribute('data-tema-itens') && itens.hidden) {
      itens.hidden = false;
      cab.setAttribute('aria-expanded', 'true');
      desfazer.push(() => { itens.hidden = true; cab.setAttribute('aria-expanded', 'false'); });
    }
  }

  function acharAlvo(p) {
    if (p.tipo === 'centro') return null;
    let e = null;
    if (p.tipo === 'busca' || p.tipo === 'conta' || p.tipo === 'nucleai') e = document.querySelector('[data-tut="' + p.tipo + '"]');
    else if (p.tipo === 'grupo') e = [...document.querySelectorAll('[data-tut-grupo]')].find((b) => b.dataset.tutGrupo === p.valor) || null;
    else if (p.tipo === 'item') e = [...document.querySelectorAll('[data-tut-item]')].find((a) => a.dataset.tutItem === p.valor) || null;
    if (!e) return null;
    // a barra lateral pode estar escondida pelo usuário: mostra enquanto o tutorial roda
    if (document.body.classList.contains('menu-oculto') && e.closest('.menu')) {
      document.body.classList.remove('menu-oculto');
      desfazer.push(() => document.body.classList.add('menu-oculto'));
    }
    if (p.tipo === 'grupo') abrirGrupo(e);
    if (p.tipo === 'item') { const lista = e.closest('[data-tema-itens]'); if (lista) abrirGrupo(lista.previousElementSibling); }
    if (!visivel(e)) return null;   // celular: a barra lateral fica fechada, o passo vira só conversa
    if (e.closest('.menu')) e.scrollIntoView({block: 'center', behavior: 'instant'});
    return e;
  }

  function retangulo(p, e) {
    const r = e.getBoundingClientRect();
    let x0 = r.left, y0 = r.top, x1 = r.right, y1 = r.bottom;
    if (p.tipo === 'grupo' && e.nextElementSibling && e.nextElementSibling.hasAttribute('data-tema-itens') && !e.nextElementSibling.hidden) {
      const r2 = e.nextElementSibling.getBoundingClientRect();   // ilumina o tema inteiro: título e telas
      x0 = Math.min(x0, r2.left); y0 = Math.min(y0, r2.top); x1 = Math.max(x1, r2.right); y1 = Math.max(y1, r2.bottom);
    }
    const m = 7;
    return {left: x0 - m, top: y0 - m, width: x1 - x0 + 2 * m, height: y1 - y0 + 2 * m};
  }

  // ------------------------------------------------------------------ posição do mascote, do foco e da seta
  function posicionar(p) {
    const e = acharAlvoSemEfeitos(p);
    const vw = window.innerWidth, vh = window.innerHeight, margem = 12;
    const palco = ui.palco;
    const W = palco.offsetWidth, H = palco.offsetHeight;
    const limitar = (v, min, max) => Math.max(min, Math.min(v, max));
    ui.palco.classList.remove('lado-esq');

    if (!e) {
      // passo sem alvo: foco vira um ponto no centro (a tela só escurece) e o mascote fica no meio
      ui.foco.style.left = (vw / 2) + 'px'; ui.foco.style.top = (vh / 2) + 'px';
      ui.foco.style.width = '0px'; ui.foco.style.height = '0px';
      ui.seta.classList.remove('mostra');
      palco.style.left = limitar((vw - W) / 2, margem, vw - W - margem) + 'px';
      palco.style.top = limitar((vh - H) / 2, margem, vh - H - margem) + 'px';
      olhar(0, 0);
      return;
    }
    const r = retangulo(p, e);
    ui.foco.style.left = r.left + 'px'; ui.foco.style.top = r.top + 'px';
    ui.foco.style.width = r.width + 'px'; ui.foco.style.height = r.height + 'px';
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const folga = 48;   // espaço para a seta entre o alvo e o mascote
    const opcoes = [
      {lado: 'dir', left: r.left + r.width + folga, top: cy - H / 2},
      {lado: 'esq', left: r.left - folga - W, top: cy - H / 2},
      {lado: 'baixo', left: cx - W / 2, top: r.top + r.height + folga},
      {lado: 'cima', left: cx - W / 2, top: r.top - folga - H},
    ];
    const cabe = (o) => o.left >= margem && o.left + W <= vw - margem && o.top >= margem - 40 && o.top + H <= vh - margem + 40;
    const escolhida = opcoes.find(cabe) || null;
    let lado, left, top;
    if (escolhida) {
      lado = escolhida.lado;
      left = escolhida.left; top = limitar(escolhida.top, margem, Math.max(margem, vh - H - margem));
      left = limitar(left, margem, Math.max(margem, vw - W - margem));
    } else {   // nenhum lado comporta: fica no canto mais livre da tela
      lado = cy < vh / 2 ? 'baixo' : 'cima';
      left = limitar(cx - W / 2, margem, Math.max(margem, vw - W - margem));
      top = lado === 'baixo' ? vh - H - margem : margem;
    }
    if (lado === 'esq') palco.classList.add('lado-esq');
    palco.style.left = left + 'px'; palco.style.top = top + 'px';

    // seta encostada no alvo, apontando para ele
    const s = ui.seta;
    const rot = {dir: 180, esq: 0, baixo: -90, cima: 90}[lado];
    if (lado === 'dir') { s.style.left = (r.left + r.width + 8) + 'px'; s.style.top = (cy - 17) + 'px'; }
    if (lado === 'esq') { s.style.left = (r.left - 42) + 'px'; s.style.top = (cy - 17) + 'px'; }
    if (lado === 'baixo') { s.style.left = (cx - 17) + 'px'; s.style.top = (r.top + r.height + 8) + 'px'; }
    if (lado === 'cima') { s.style.left = (cx - 17) + 'px'; s.style.top = (r.top - 42) + 'px'; }
    s.firstChild.style.transform = '';
    s.style.transform = 'rotate(' + rot + 'deg)';
    s.classList.add('mostra');
    // os olhos da NucleAI olham para o alvo
    const dx = cx - (left + W / 2), dy = cy - (top + H / 2), n = Math.max(1, Math.hypot(dx, dy));
    olhar(dx / n * 3, dy / n * 3);
  }

  // posicionar() é chamado de novo ao redimensionar: acha o alvo sem abrir/rolar outra vez
  function acharAlvoSemEfeitos(p) {
    if (p.tipo === 'centro') return null;
    let e = null;
    if (p.tipo === 'busca' || p.tipo === 'conta' || p.tipo === 'nucleai') e = document.querySelector('[data-tut="' + p.tipo + '"]');
    else if (p.tipo === 'grupo') e = [...document.querySelectorAll('[data-tut-grupo]')].find((b) => b.dataset.tutGrupo === p.valor) || null;
    else if (p.tipo === 'item') e = [...document.querySelectorAll('[data-tut-item]')].find((a) => a.dataset.tutItem === p.valor) || null;
    return visivel(e) ? e : null;
  }

  function olhar(x, y) {
    ui.mascote.querySelector('.tm-olhar').style.setProperty('--ox', x.toFixed(1) + 'px');
    ui.mascote.querySelector('.tm-olhar').style.setProperty('--oy', y.toFixed(1) + 'px');
  }

  // ------------------------------------------------------------------ fala
  // o que ainda não foi "falado" fica invisível no balão, para ele não crescer enquanto o texto aparece
  function escreverTexto(txt, n) {
    ui.texto.textContent = '';
    const dito = document.createElement('span'); dito.textContent = txt.slice(0, n);
    const resto = document.createElement('span'); resto.textContent = txt.slice(n); resto.style.visibility = 'hidden';
    ui.texto.append(dito, resto);
  }
  function falar(txt) {
    clearInterval(timerTexto);
    ui.texto.dataset.inteiro = txt;
    if (reduz) { ui.texto.textContent = txt; ui.mascote.classList.remove('falando'); return; }
    let n = 0;
    escreverTexto(txt, 0);
    ui.mascote.classList.add('falando');
    timerTexto = setInterval(() => {
      n += 2;
      escreverTexto(txt, n);
      if (n >= txt.length) { clearInterval(timerTexto); ui.texto.textContent = txt; ui.mascote.classList.remove('falando'); }
    }, 22);
  }
  function mostrarTextoInteiro() {
    if (!ui || !ui.texto.dataset.inteiro) return;
    clearInterval(timerTexto);
    ui.texto.textContent = ui.texto.dataset.inteiro;
    ui.mascote.classList.remove('falando');
  }

  // ------------------------------------------------------------------ passos
  function ir(n) {
    if (n < 0 || n >= passos.length) return;
    atual = n;
    const p = passos[n];
    if (alvoMarcado) { alvoMarcado.classList.remove('tut-alvo-pisca'); alvoMarcado = null; }
    const e = acharAlvo(p);   // abre o tema, mostra a barra e rola até o alvo
    if (e) { e.classList.add('tut-alvo-pisca'); alvoMarcado = e; }
    ui.passo.textContent = 'Passo ' + (n + 1) + ' de ' + passos.length;
    ui.titulo.textContent = p.titulo || '';
    ui.barra.style.width = ((n + 1) / passos.length * 100) + '%';
    ui.ant.style.visibility = n === 0 ? 'hidden' : 'visible';
    ui.prox.textContent = n === passos.length - 1 ? 'Concluir ✔' : 'Próximo →';
    ui.pular.style.display = n === passos.length - 1 ? 'none' : '';
    // balão recomeça a animação a cada passo
    ui.balao.style.animation = 'none'; void ui.balao.offsetWidth; ui.balao.style.animation = '';
    ui.palco.classList.remove('pulo'); void ui.palco.offsetWidth; ui.palco.classList.add('pulo');
    ui.mascote.classList.toggle('alegre', n === 0 || n === passos.length - 1);
    // o texto precisa estar no balão (para medir a altura) antes de posicionar
    ui.texto.textContent = p.texto || '';
    posicionar(p);
    // a barra lateral pode ainda estar rolando/abrindo: mede de novo logo depois para o foco cair exatamente no alvo
    [250, 700].forEach((ms) => setTimeout(() => { if (ativo && atual === n) posicionar(p); }, ms));
    falar(p.texto || '');
    ui.prox.focus({preventScroll: true});
    if (n === passos.length - 1) festa();
  }

  // confetes de emoji no final
  function festa() {
    if (reduz) return;
    const EMO = ['🎉', '✨', '💚', '⭐', '🎊'];
    for (let i = 0; i < 18; i++) {
      const c = el('span', '', EMO[i % EMO.length]);
      c.style.cssText = 'position:fixed;z-index:10003;pointer-events:none;font-size:' + (18 + Math.random() * 18) + 'px;left:' + (Math.random() * 100) +
        'vw;top:105vh;transition:transform ' + (2.2 + Math.random() * 1.6) + 's ease-out,opacity 3.6s ease-in;';
      document.body.appendChild(c);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        c.style.transform = 'translateY(-' + (60 + Math.random() * 45) + 'vh) rotate(' + (Math.random() * 360 - 180) + 'deg)';
        c.style.opacity = '0';
      }));
      setTimeout(() => c.remove(), 4200);
    }
  }

  function aoTeclar(ev) {
    if (!ativo) return;
    const naBotao = ev.target && ev.target.closest && ev.target.closest('.tut-palco button');
    if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); encerrar(); return; }
    if (ev.key === 'ArrowRight' || ((ev.key === 'Enter' || ev.key === ' ') && !naBotao)) {
      ev.preventDefault(); ev.stopPropagation();
      atual >= passos.length - 1 ? encerrar() : ir(atual + 1);
    } else if (ev.key === 'ArrowLeft') {
      ev.preventDefault(); ev.stopPropagation(); ir(atual - 1);
    } else if (ev.key === 'Tab' && ui) {   // o foco do teclado fica preso nos botões do tutorial
      const bs = [...ui.palco.querySelectorAll('button')].filter((b) => b.style.visibility !== 'hidden' && b.style.display !== 'none');
      if (!bs.length) return;
      const i = bs.indexOf(document.activeElement);
      ev.preventDefault();
      bs[(i + (ev.shiftKey ? -1 : 1) + bs.length) % bs.length].focus();
    }
  }

  function marcarVisto() {
    const meta = document.querySelector('meta[name="csrf"]');
    try {
      fetch(D.visto_url, {method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': meta ? meta.content : ''}});
    } catch (e) { /* sem rede: o tutorial só abre de novo no próximo acesso */ }
  }

  function encerrar() {
    if (!ativo) return;
    ativo = false;
    clearInterval(timerTexto);
    document.removeEventListener('keydown', aoTeclar, true);
    if (alvoMarcado) { alvoMarcado.classList.remove('tut-alvo-pisca'); alvoMarcado = null; }
    desfazer.reverse().forEach((f) => { try { f(); } catch (e) { /* ignora */ } });
    desfazer = [];
    [ui.bloqueio, ui.foco, ui.seta, ui.palco].forEach((n) => n.remove());
    ui = null;
    marcarVisto();
  }

  function iniciar() {
    if (ativo) return;
    document.querySelectorAll('.boas-vindas').forEach((b) => b.remove());
    ativo = true;
    montar();
    document.addEventListener('keydown', aoTeclar, true);
    ir(0);
  }

  window.Tutorial = {iniciar};
  document.querySelectorAll('[data-tutorial-iniciar]').forEach((b) => b.addEventListener('click', (ev) => { ev.preventDefault(); iniciar(); }));

  // primeiro acesso: abre sozinho depois que a tela terminou de carregar (e depois das boas-vindas da versão, se houver)
  if (D.auto) {
    let tentativas = 0;
    const espera = setInterval(() => {
      tentativas += 1;
      if (document.querySelector('.boas-vindas') && tentativas < 40) return;
      clearInterval(espera);
      if (document.querySelector('.aguarde, .modal-sessao')) return;
      marcarVisto();   // não reabre sozinho se a pessoa navegar; o botão "Rever o tutorial" continua disponível
      iniciar();
    }, 700);
  }
})();
