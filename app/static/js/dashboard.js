// Dashboard: gráficos SVG animados, contadores, tooltip e revelação ao rolar. Sem dependências externas.
(function () {
  'use strict';
  const reduz = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const elDados = document.getElementById('dados'), D = elDados ? JSON.parse(elDados.textContent) : {};
  const NS = 'http://www.w3.org/2000/svg';
  const tema = (n, f) => (getComputedStyle(document.body).getPropertyValue(n) || '').trim() || f;   // cores do tema escolhido
  const CORES = [tema('--verde', '#255f39'), tema('--brilho-2', '#2f9e6a'), tema('--brilho', '#5bc0a0'), '#f0b429', '#e07a5f', '#4a7fb5', '#9b8bd0', '#b0bdb6', '#d98fb0', '#7fb069'];
  const fmt = (n, d) => Number(n).toLocaleString('pt-BR', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let uid = 0;

  function svg(tag, attrs, pai) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (pai) pai.appendChild(e);
    return e;
  }
  function html(tag, cls, texto, pai) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (texto != null) e.textContent = texto;
    if (pai) pai.appendChild(e);
    return e;
  }
  function vazio(alvo, msg) { alvo.innerHTML = ''; html('div', 'vazio-graf', msg || 'Sem dados no período.', alvo); }
  const total = (itens) => itens.reduce((s, i) => s + i.valor, 0);

  // ------------------------------------------------------------------ tooltip
  const tip = html('div', 'tip', null, document.body);
  function mover(ev) {
    const r = tip.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY - r.height - 12;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y < 8) y = ev.clientY + 18;
    tip.style.transform = 'translate(' + x + 'px,' + y + 'px)';
  }
  function dica(el, fn) {
    el.addEventListener('pointerenter', (e) => { tip.innerHTML = fn(); tip.classList.add('on'); mover(e); });
    el.addEventListener('pointermove', mover);
    el.addEventListener('pointerleave', () => tip.classList.remove('on'));
  }
  const dicaHtml = (valor, rotulo, extra) => '<b>' + fmt(valor) + '</b> <span>' + esc(rotulo) + '</span>' + (extra ? '<br><span>' + extra + '</span>' : '');

  // ------------------------------------------------------------------ escalas
  function maxBonito(max) {
    if (max <= 4) return 4;
    const exp = Math.pow(10, Math.floor(Math.log10(max)));
    const f = max / exp;
    const n = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
    const v = n * exp;
    return v < max ? v * 1.2 : v;
  }
  function eixoY(g, W, H, m, topo, f) {
    for (let i = 0; i <= 4; i++) {
      const y = m.t + (H - m.t - m.b) * (1 - i / 4);
      svg('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'grade-h' }, g);
      const t = svg('text', { x: m.l - 8, y: y + 4, class: 'eixo', 'text-anchor': 'end' }, g);
      t.textContent = (f || fmt)(topo * i / 4);
    }
  }
  function rotulosX(g, itens, xs, W, H, m, rotulo) {
    const n = itens.length, passo = Math.max(1, Math.ceil(n / Math.max(1, Math.floor((W - m.l - m.r) / 54))));
    itens.forEach((it, i) => {
      if ((n - 1 - i) % passo !== 0) return; // alinhado ao último ponto, sem rótulos sobrepostos
      const t = svg('text', { x: xs[i], y: H - m.b + 18, class: rotulo || 'eixo', 'text-anchor': 'middle' }, g);
      t.textContent = it.rotulo;
    });
  }
  const larguraDe = (alvo, minimo) => Math.max(minimo, Math.round(alvo.clientWidth || minimo));

  // ------------------------------------------------------------------ gráfico de área (série temporal)
  function area(alvo, itens, opc) {
    if (!itens.length || !total(itens)) return vazio(alvo);
    alvo.innerHTML = '';
    const W = larguraDe(alvo, 280), H = W < 520 ? 250 : Math.max(330, Math.round(W * .5)), m = { l: 36, r: 14, t: 18, b: 32 };
    const n = itens.length, topo = maxBonito(Math.max.apply(null, itens.map((i) => i.valor)));
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const xs = itens.map((_, i) => n === 1 ? m.l + iw / 2 : m.l + iw * i / (n - 1));
    const ys = itens.map((i) => m.t + ih * (1 - i.valor / topo));
    const s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'xMidYMid meet' }, alvo);
    const id = 'ga' + (++uid);
    const defs = svg('defs', {}, s);
    const grad = svg('linearGradient', { id: id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    svg('stop', { offset: '0%', 'stop-color': tema('--brilho-2', '#2f9e6a'), 'stop-opacity': .38 }, grad);
    svg('stop', { offset: '100%', 'stop-color': tema('--brilho-2', '#2f9e6a'), 'stop-opacity': 0 }, grad);
    const g = svg('g', {}, s);
    eixoY(g, W, H, m, topo, opc && opc.fmtEixo);
    rotulosX(g, itens, xs, W, H, m);
    // curva com tangentes horizontais (nunca "estoura" abaixo de zero)
    let d = 'M' + xs[0] + ',' + ys[0];
    for (let i = 1; i < n; i++) { const mx = (xs[i - 1] + xs[i]) / 2; d += ' C' + mx + ',' + ys[i - 1] + ' ' + mx + ',' + ys[i] + ' ' + xs[i] + ',' + ys[i]; }
    svg('path', { d: d + ' L' + xs[n - 1] + ',' + (m.t + ih) + ' L' + xs[0] + ',' + (m.t + ih) + ' Z', fill: 'url(#' + id + ')', class: 'area-fill' }, g);
    svg('path', { d: d, class: 'area-linha', pathLength: 1 }, g);
    const guia = svg('line', { class: 'area-guia', y1: m.t, y2: m.t + ih, x1: 0, x2: 0 }, g);
    const ponto = svg('circle', { class: 'area-ponto', r: 6, cx: 0, cy: 0 }, g);
    const capa = svg('rect', { x: m.l, y: 0, width: iw, height: H, fill: 'transparent' }, s);
    capa.addEventListener('pointermove', (e) => {
      const r = s.getBoundingClientRect(), px = (e.clientX - r.left) * W / r.width;
      let melhor = 0, dist = 1e9;
      xs.forEach((x, i) => { const dd = Math.abs(x - px); if (dd < dist) { dist = dd; melhor = i; } });
      guia.setAttribute('x1', xs[melhor]); guia.setAttribute('x2', xs[melhor]);
      ponto.setAttribute('cx', xs[melhor]); ponto.setAttribute('cy', ys[melhor]);
      s.classList.add('area-hover');
      tip.innerHTML = dicaHtml(itens[melhor].valor, itens[melhor].valor === 1 ? 'atendimento' : 'atendimentos', esc(itens[melhor].dica || itens[melhor].rotulo));
      tip.classList.add('on'); mover(e);
    });
    capa.addEventListener('pointerleave', () => { s.classList.remove('area-hover'); tip.classList.remove('on'); });
  }

  // ------------------------------------------------------------------ minigráfico dentro do KPI
  function spark(alvo, itens) {
    if (!itens.length || !total(itens) || itens.length < 2) return;
    const W = 300, H = 46, n = itens.length, max = Math.max.apply(null, itens.map((i) => i.valor)) || 1;
    const xs = itens.map((_, i) => W * i / (n - 1)), ys = itens.map((i) => H - 6 - (H - 14) * i.valor / max);
    const s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'none' }, alvo);
    const id = 'sp' + (++uid), defs = svg('defs', {}, s), grad = svg('linearGradient', { id: id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    svg('stop', { offset: '0%', 'stop-color': tema('--verde', '#255f39'), 'stop-opacity': .28 }, grad);
    svg('stop', { offset: '100%', 'stop-color': tema('--verde', '#255f39'), 'stop-opacity': 0 }, grad);
    let d = 'M' + xs[0] + ',' + ys[0];
    for (let i = 1; i < n; i++) { const mx = (xs[i - 1] + xs[i]) / 2; d += ' C' + mx + ',' + ys[i - 1] + ' ' + mx + ',' + ys[i] + ' ' + xs[i] + ',' + ys[i]; }
    svg('path', { d: d + ' L' + W + ',' + H + ' L0,' + H + ' Z', fill: 'url(#' + id + ')', class: 'area-fill' }, s);
    svg('path', { d: d, class: 'area-linha', pathLength: 1, style: 'stroke:' + tema('--verde', '#255f39') + ';stroke-width:2', 'vector-effect': 'non-scaling-stroke' }, s);
  }

  // ------------------------------------------------------------------ barras verticais
  function barras(alvo, itens, opc) {
    opc = opc || {};
    if (!itens.length || !total(itens)) return vazio(alvo);
    alvo.innerHTML = '';
    const W = larguraDe(alvo, 260), H = 250, m = { l: 34, r: 6, t: 22, b: 30 };
    const n = itens.length, vmax = Math.max.apply(null, itens.map((i) => i.valor)), topo = maxBonito(vmax);
    const iw = W - m.l - m.r, ih = H - m.t - m.b, banda = iw / n, larg = Math.min(46, banda * .66);
    const passoRot = banda < 36 ? 2 : 1;
    const xs = itens.map((_, i) => m.l + banda * i + banda / 2);
    const s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H }, alvo);
    const id = 'gb' + (++uid), defs = svg('defs', {}, s);
    [['n', tema('--brilho-2', '#2f9e6a'), tema('--brilho', '#5bc0a0')], ['d', tema('--verde-escuro', '#173d25'), tema('--brilho-2', '#2f9e6a')], ['f', '#cfe3d7', '#e4f0e9']].forEach((c) => {
      const gr = svg('linearGradient', { id: id + c[0], x1: 0, y1: 1, x2: 0, y2: 0 }, defs);
      svg('stop', { offset: '0%', 'stop-color': c[1] }, gr); svg('stop', { offset: '100%', 'stop-color': c[2] }, gr);
    });
    const g = svg('g', {}, s);
    eixoY(g, W, H, m, topo, opc.fmtEixo);
    itens.forEach((it, i) => {
      const h = Math.max(it.valor ? 3 : 0, ih * it.valor / topo), y = m.t + ih - h;
      const destaque = opc.destaque === 'max' ? it.valor === vmax && vmax > 0 : opc.destaque === 'ultimo' ? i === n - 1 : false;
      const fill = opc.destaque ? (destaque ? 'd' : (opc.destaque === 'ultimo' ? 'n' : 'n')) : 'n';
      const r = svg('rect', { x: xs[i] - larg / 2, y: y, width: larg, height: h, rx: Math.min(7, larg / 2.4), fill: 'url(#' + id + fill + ')', class: 'barra', style: '--d:' + (i * 55) }, g);
      dica(r, () => opc.dicaFn ? opc.dicaFn(it) : dicaHtml(it.valor, it.valor === 1 ? 'atendimento' : 'atendimentos', esc(it.dica || it.rotulo)));
      if (n <= 12 && it.valor && !opc.semValores) {
        const t = svg('text', { x: xs[i], y: y - 6, class: 'barra-val', style: '--d:' + (i * 55) }, g); t.textContent = (opc.fmtValor || fmt)(it.valor);
      }
      if ((n - 1 - i) % passoRot === 0) {
        const rot = svg('text', { x: xs[i], y: H - m.b + 18, class: 'barra-rot' }, g); rot.textContent = it.rotulo;
        if (n > 9) rot.setAttribute('font-size', '10');
      }
    });
  }

  // ------------------------------------------------------------------ rosca (donut)
  function donut(alvo, itens, opc) {
    opc = opc || {};
    const fv = opc.fmtValor || fmt;
    if (!itens.length || !total(itens)) return vazio(alvo);
    alvo.innerHTML = '';
    const tot = total(itens), R = 70, C = 2 * Math.PI * R, folga = itens.length > 1 ? 3 : 0;
    const s = svg('svg', { viewBox: '0 0 190 190', class: 'donut-svg', role: 'img', 'aria-label': 'Distribuição por exame' }, alvo);
    svg('circle', { cx: 95, cy: 95, r: R, fill: 'none', stroke: '#edf2ef', 'stroke-width': 24 }, s);
    const g = svg('g', { transform: 'rotate(-90 95 95)' }, s);
    const legenda = html('div', 'legenda', null, alvo);
    let acum = 0; const segs = [], linhas = [];
    itens.forEach((it, i) => {
      const cor = CORES[i % CORES.length], len = Math.max(0, C * it.valor / tot - folga);
      const c = svg('circle', { cx: 95, cy: 95, r: R, class: 'seg', stroke: cor, 'stroke-linecap': 'butt', 'stroke-dashoffset': -acum,
        style: '--a:' + len.toFixed(2) + ' ' + (C - len).toFixed(2) + ';--b:0 ' + C.toFixed(2) + ';--k:' + i }, g);
      acum += C * it.valor / tot;
      const l = html('div', 'leg', null, legenda); l.style.setProperty('--c', cor);
      html('i', null, null, l); html('span', null, it.rotulo, l); html('b', null, fv(it.valor), l);
      html('em', null, fmt(100 * it.valor / tot, 1) + '%', l);
      const foco = (on) => { s.classList.toggle('tem-foco', on); c.classList.toggle('foco', on); l.classList.toggle('foco', on); };
      [c, l].forEach((el) => { el.addEventListener('pointerenter', () => foco(true)); el.addEventListener('pointerleave', () => foco(false)); });
      dica(c, () => '<b>' + fv(it.valor) + '</b> <span>' + esc(it.rotulo) + '<br>' + fmt(100 * it.valor / tot, 1) + '% do total</span>');
      segs.push(c); linhas.push(l);
    });
    const t1 = svg('text', { x: 95, y: 97, class: 'donut-centro', 'font-size': 30, 'data-contar': tot }, s); t1.textContent = fv(tot); if (opc.fonteCentro) t1.setAttribute('font-size', opc.fonteCentro);
    const t2 = svg('text', { x: 95, y: 116, class: 'donut-centro-sub' }, s); t2.textContent = opc.sub || (tot === 1 ? 'atendimento' : 'atendimentos');
  }

  // ------------------------------------------------------------------ barras horizontais
  function hbarras(alvo, itens, substantivo) {
    if (!itens.length || !total(itens)) return vazio(alvo);
    alvo.innerHTML = '';
    const tot = total(itens), principais = itens.filter((i) => !i.resto), resto = itens.find((i) => i.resto);
    const max = Math.max.apply(null, principais.map((i) => i.valor));
    principais.forEach((it, i) => {
      const linha = html('div', 'hrow', null, alvo);
      const rot = html('span', 'hr-rot', it.rotulo, linha); rot.title = it.rotulo;
      const tr = html('div', 'hr-trilho', null, linha), b = html('div', 'hr-barra', null, tr);
      b.style.setProperty('--w', (100 * it.valor / max).toFixed(1) + '%'); b.style.setProperty('--d', i * 70);
      const v = html('span', 'hr-val', fmt(it.valor), linha); html('small', null, fmt(100 * it.valor / tot) + '%', v);
      dica(linha, () => dicaHtml(it.valor, it.rotulo, fmt(100 * it.valor / tot, 1) + '% do total'));
    });
    if (resto) {
      html('p', 'hr-resto', '+ ' + fmt(resto.valor) + ' atendimentos em outros ' + fmt(resto.qtd_itens) + ' ' + (substantivo || 'itens') + ' (' + fmt(100 * resto.valor / tot) + '% do total)', alvo);
    }
  }

  // ------------------------------------------------------------------ montar tudo
  // cada gráfico só é desenhado se o painel existe na página e os dados chegaram (painéis ocultos não mandam dados)
  function desenhar() {
    const ld = (id, chave, fn) => { const el = document.getElementById(id); if (el && D[chave]) fn(el); };
    ld('g-serie', 'serie', (el) => area(el, D.serie.itens));
    if (D.serie) document.querySelectorAll('[data-spark="serie"]').forEach((el) => { el.innerHTML = ''; spark(el, D.serie.itens); });
    ld('g-exames', 'exames', (el) => donut(el, D.exames));
    ld('g-convenios', 'convenios', (el) => hbarras(el, D.convenios, 'convênios'));
    ld('g-medicos', 'medicos', (el) => hbarras(el, D.medicos, 'médicos'));
    ld('g-faixas', 'faixas', (el) => barras(el, D.faixas, { destaque: 'max' }));
    ld('g-semana', 'semana', (el) => barras(el, D.semana, { destaque: 'max' }));
    ld('g-doze', 'doze_meses', (el) => barras(el, D.doze_meses, { destaque: 'ultimo' }));
  }
  window.Graficos = { svg, html, vazio, fmt, esc, dica, dicaHtml, maxBonito, eixoY, rotulosX, larguraDe, barras, donut, hbarras, area, total, CORES };
  desenhar();
  // Redesenha ao mudar a largura (girar o celular, redimensionar a janela); só o que depende da largura.
  let larguraAnterior = window.innerWidth, timerResize = null;
  window.addEventListener('resize', () => {
    clearTimeout(timerResize);
    timerResize = setTimeout(() => {
      if (Math.abs(window.innerWidth - larguraAnterior) < 24) return;
      larguraAnterior = window.innerWidth; desenhar();
    }, 220);
  });

  // avatares com cor estável por nome
  document.querySelectorAll('.avatar[data-nome]').forEach((a) => {
    let h = 0; for (const ch of a.dataset.nome) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    a.style.setProperty('--av', CORES[h % 7]);
  });

  // ------------------------------------------------------------------ contadores animados
  function contar(el) {
    const alvo = parseFloat(el.dataset.contar), dec = parseInt(el.dataset.dec || '0', 10);
    if (isNaN(alvo)) return;
    if (reduz || alvo === 0) { el.textContent = fmt(alvo, dec); return; }
    const t0 = performance.now(), dur = 1100;
    (function passo(t) {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 4);
      el.textContent = fmt(alvo * e, dec);
      if (p < 1) requestAnimationFrame(passo);
    })(t0);
  }

  // ------------------------------------------------------------------ revelação ao rolar
  const revelaveis = document.querySelectorAll('.revelar');
  function mostrar(el) {
    el.classList.add('visivel');
    el.querySelectorAll('[data-contar]').forEach(contar);
    if (el.matches('[data-contar]')) contar(el);
    setTimeout(() => el.classList.add('pronto'), 1400);
  }
  if ('IntersectionObserver' in window && !reduz) {
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { mostrar(e.target); io.unobserve(e.target); } }), { threshold: .12, rootMargin: '0px 0px -30px 0px' });
    revelaveis.forEach((el) => io.observe(el));
  } else revelaveis.forEach(mostrar);

  // ------------------------------------------------------------------ seletor de período (indicador deslizante)
  const seg = document.querySelector('.seg-periodo');
  if (seg) {
    const ind = seg.querySelector('.seg-ind'), ativo = seg.querySelector('.ativo');
    const pos = (el) => ({ l: el.offsetLeft, t: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight });
    const aplicar = (p) => { ind.style.left = p.l + 'px'; ind.style.top = p.t + 'px'; ind.style.width = p.w + 'px'; ind.style.height = p.h + 'px'; };
    if (ativo) {
      const novo = pos(ativo); let ant = null;
      try { ant = JSON.parse(sessionStorage.getItem('dashPill')); } catch (e) { /* sem storage */ }
      const ini = reduz || !ant || ant.h === undefined ? novo : ant;
      ind.style.transition = 'none'; aplicar(ini); void ind.offsetWidth; ind.style.transition = '';
      requestAnimationFrame(() => aplicar(novo));
      try { sessionStorage.setItem('dashPill', JSON.stringify(novo)); } catch (e) { /* ignora */ }
      if (seg.scrollWidth > seg.clientWidth) seg.scrollLeft = Math.max(0, novo.l - seg.clientWidth / 2 + novo.w / 2);
    } else ind.style.display = 'none';
  }
  const btnCustom = document.getElementById('btn-custom'), pop = document.getElementById('pop-custom');
  if (btnCustom && pop) {
    btnCustom.addEventListener('click', () => {
      const abrir = pop.hidden; pop.hidden = !abrir; btnCustom.setAttribute('aria-expanded', abrir);
    });
    if (new URLSearchParams(location.search).get('p') === 'custom') pop.hidden = true;
  }

  // ------------------------------------------------------------------ atualização
  const btnAtu = document.getElementById('btn-atualizar'), chk = document.getElementById('auto-atualizar');
  if (btnAtu) btnAtu.addEventListener('click', () => { btnAtu.classList.add('gira'); location.reload(); });
  if (chk) {
    try { chk.checked = localStorage.getItem('dashAuto') === '1'; } catch (e) { /* ignora */ }
    chk.addEventListener('change', () => { try { localStorage.setItem('dashAuto', chk.checked ? '1' : '0'); } catch (e) { /* ignora */ } });
    // a atualização automática não pode manter a sessão viva: só recarrega se alguém mexeu na tela nos últimos 2 min 30 s
    const ativoRecente = () => { try { return Date.now() - Number(localStorage.getItem('nl_ativo') || 0) < 150000; } catch (e) { return true; } };
    setInterval(() => { if (chk.checked && document.visibilityState === 'visible' && !(pop && !pop.hidden) && ativoRecente()) location.reload(); }, 120000);
  }
})();
