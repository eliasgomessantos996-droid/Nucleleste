'use strict';
/* Ajudas para o celular (só agem em tela estreita; no computador não mudam nada).
   1) menu em gaveta: fundo escuro, botão de fechar, fecha ao tocar num item, no fundo ou na tecla Esc;
   2) tabelas simples viram cartões: cada célula recebe o nome da coluna (data-rotulo), o CSS faz o resto;
   3) o que ainda ficar mais largo que a tela ganha uma moldura que rola de lado, sem arrastar a página inteira. */
(() => {
  const mq = window.matchMedia('(max-width: 900px)');
  const menu = document.querySelector('.menu');

  // ---------- 1. gaveta do menu ----------
  if (menu) {
    const botao = document.querySelector('[data-abrir-menu]');
    const fundo = document.createElement('div');
    fundo.className = 'menu-fundo';
    document.body.appendChild(fundo);
    const fechar = document.createElement('button');
    fechar.type = 'button'; fechar.className = 'menu-fechar'; fechar.setAttribute('aria-label', 'Fechar o menu'); fechar.textContent = '✕';
    const marca = menu.querySelector('.marca');
    if (marca) marca.appendChild(fechar);

    const definir = (aberto) => {
      menu.classList.toggle('aberto', aberto);
      document.body.classList.toggle('menu-aberto', aberto);
      if (botao) botao.setAttribute('aria-expanded', String(aberto));
    };
    // o app.js já alterna a classe no clique do botão; aqui só espelhamos no body (e cuidamos de fechar)
    if (botao) botao.addEventListener('click', () => requestAnimationFrame(() => definir(menu.classList.contains('aberto'))));
    fundo.addEventListener('click', () => definir(false));
    fechar.addEventListener('click', () => definir(false));
    menu.addEventListener('click', (ev) => { if (ev.target.closest('a[href]') && mq.matches) definir(false); });
    document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && menu.classList.contains('aberto')) definir(false); });
    mq.addEventListener('change', () => definir(false));

    // arrastar a gaveta para a esquerda fecha; arrastar da borda esquerda abre
    let x0 = null, y0 = null;
    document.addEventListener('touchstart', (ev) => { const t = ev.touches[0]; x0 = t.clientX; y0 = t.clientY; }, {passive: true});
    document.addEventListener('touchend', (ev) => {
      if (x0 === null || !mq.matches) return;
      const t = ev.changedTouches[0], dx = t.clientX - x0, dy = Math.abs(t.clientY - y0);
      const aberto = menu.classList.contains('aberto');
      if (aberto && dx < -70 && dy < 60) definir(false);
      else if (!aberto && x0 < 18 && dx > 80 && dy < 60 && !document.querySelector('dialog[open]')) definir(true);
      x0 = null;
    }, {passive: true});
  }

  // ---------- 2. tabelas em cartões ----------
  const texto = (el) => el.textContent.replace(/\s+/g, ' ').trim();
  const prepararTabela = (tb) => {
    if (tb.dataset.mPronta) return;
    tb.dataset.mPronta = '1';
    const cab = tb.tHead && tb.tHead.rows.length === 1 ? tb.tHead.rows[0] : null;
    if (!cab || tb.classList.contains('sem-cartoes')) return;
    const ths = [...cab.cells];
    if (ths.length < 3 || ths.some((th) => th.colSpan > 1 || th.rowSpan > 1)) return;
    if (tb.closest('.ag-grade, .ag, .bh-calendario, [data-sem-cartoes]')) return;
    if (!tb.classList.contains('tabela')) return;
    const rotulos = ths.map(texto);
    let linhasValidas = 0;
    [...tb.tBodies].forEach((corpo) => [...corpo.rows].forEach((tr) => {
      const tds = [...tr.cells];
      if (tds.length === 1 && tds[0].colSpan > 1) { tds[0].classList.add('vazio'); linhasValidas += 1; return; }   // "Nenhum registro": também vira cartão (sem o cabeçalho espremido)
      if (tds.length !== ths.length || tds.some((td) => td.colSpan > 1)) return;
      linhasValidas += 1;
      tds.forEach((td, i) => {
        td.dataset.rotulo = rotulos[i];
        const vazio = !texto(td) && !td.querySelector('input, button, a, select, img, svg, textarea');
        if (vazio) td.classList.add('m-vazia');
        else if (!rotulos[i] && td.querySelector('a, button, form, input')) td.classList.add('m-sem-rotulo');
      });
      // caixinha de seleção sozinha na célula: vai para o canto do cartão
      tds.forEach((td) => { if (!texto(td) && td.querySelector('input[type=checkbox]') && !td.querySelector('a, button')) { td.classList.add('m-chk'); tr.classList.add('m-tem-chk'); } });
      // a primeira célula com texto é o título do cartão
      const titulo = tds.find((td) => !td.classList.contains('m-vazia') && !td.classList.contains('m-sem-rotulo') && !td.classList.contains('m-chk') && !td.querySelector('input[type=checkbox]'));
      if (titulo) titulo.classList.add('m-titulo');
    }));
    if (linhasValidas) tb.classList.add('m-cartoes');
  };

  // faixa de botões do módulo: a aba aberta aparece no meio da faixa
  const centrarAba = () => {
    const faixa = document.querySelector('.abas-modulo');
    const ativa = faixa && faixa.querySelector('[aria-current="page"]');
    if (!ativa || faixa.scrollWidth <= faixa.clientWidth) return;
    faixa.scrollLeft = Math.max(0, ativa.offsetLeft - (faixa.clientWidth - ativa.offsetWidth) / 2);
  };
  window.addEventListener('load', () => { if (mq.matches) centrarAba(); });

  // ---------- agenda: calendário e ações ficam numa gaveta; a grade do dia aparece logo no começo ----------
  const lado = document.querySelector('[data-agenda] .ag-lado');
  if (lado) {
    const ag = lado.parentElement;
    const barra = document.createElement('button');
    barra.type = 'button'; barra.className = 'btn sec ag-m-alternar'; barra.setAttribute('aria-expanded', 'false');
    const ic = document.body.dataset.icones || '';
    barra.innerHTML = '<svg class="ic" width="18" height="18" aria-hidden="true"><use href="' + ic + '#i-calendar-days"/></svg><span class="agm-txt">Escolher o dia</span><span class="agm-seta" aria-hidden="true">▾</span>';
    ag.insertBefore(barra, lado);
    const dia = document.getElementById('ag-dia');
    const atualizar = () => {
      const h = dia && dia.querySelector('h2');
      barra.querySelector('.agm-txt').textContent = h ? h.textContent.trim() : 'Escolher o dia';
    };
    const alternar = (abrir) => {
      lado.classList.toggle('m-aberto', abrir);
      barra.setAttribute('aria-expanded', String(abrir));
      barra.classList.toggle('aberta', abrir);
    };
    barra.addEventListener('click', () => alternar(!lado.classList.contains('m-aberto')));
    // escolher um dia (ou "Ir para hoje") fecha a gaveta e leva a tela para a grade
    lado.addEventListener('click', (ev) => {
      if (!mq.matches || !ev.target.closest('.ag-dia-btn, .ag-hoje')) return;
      setTimeout(() => { alternar(false); barra.scrollIntoView({block: 'start', behavior: 'smooth'}); }, 200);
    });
    if (dia) new MutationObserver(atualizar).observe(dia, {childList: true, subtree: true});
    atualizar();
  }

  // ---------- 3. o que continuar largo rola dentro de uma moldura ----------
  const proteger = (tb) => {
    if (tb.closest('.rolagem-h, .tabela-wrap') || tb.classList.contains('m-cartoes')) return;
    const pai = tb.parentElement;
    if (!pai || tb.offsetWidth <= pai.clientWidth + 1) return;
    const cx = document.createElement('div');
    cx.className = 'rolagem-h';
    pai.insertBefore(cx, tb); cx.appendChild(tb);
  };

  const varrer = (raiz) => {
    if (!mq.matches) return;
    (raiz || document).querySelectorAll('table').forEach((tb) => { prepararTabela(tb); proteger(tb); });
  };

  const iniciar = () => varrer(document);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
  mq.addEventListener('change', iniciar);

  // tabelas que o JavaScript das telas desenha depois (busca, agenda, filtros)
  let espera = null;
  new MutationObserver((muts) => {
    if (!mq.matches) return;
    if (!muts.some((m) => [...m.addedNodes].some((n) => n.nodeType === 1 && (n.matches('table') || n.querySelector('table'))))) return;
    clearTimeout(espera);
    espera = setTimeout(() => { document.querySelectorAll('table:not([data-m-pronta])').forEach((tb) => { prepararTabela(tb); proteger(tb); }); }, 60);
  }).observe(document.body, {childList: true, subtree: true});
})();
