// Gráficos do dashboard de faturamento (valores em R$). Usa os helpers expostos por dashboard.js.
(function () {
  'use strict';
  const G = window.Graficos, el = document.getElementById('dados-fat');
  if (!G || !el) return;
  const D = JSON.parse(el.textContent);
  const R = (v) => 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const K = (v) => v >= 1e6 ? Number(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi'
    : v >= 1e3 ? Number(v / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mil' : G.fmt(v);
  const COR_FAT = '#9bd3b4', COR_REC = (getComputedStyle(document.body).getPropertyValue('--verde') || '').trim() || '#255f39', COR_AB = '#f0b429';

  function legenda(alvo, series) {
    const lg = G.html('div', 'legenda-h', null, alvo);
    series.forEach((s) => { const sp = G.html('span', null, null, lg); sp.innerHTML = '<i style="background:' + s.cor + '"></i>' + G.esc(s.nome); });
  }

  // barras agrupadas (faturado x recebido por mês)
  function grupo(alvo, itens, series) {
    if (!itens.length || !itens.some((i) => i.valores.some((v) => v > 0))) return G.vazio(alvo);
    alvo.innerHTML = '';
    const W = G.larguraDe(alvo, 280), H = 290, m = { l: 52, r: 8, t: 18, b: 30 };
    const topo = G.maxBonito(Math.max.apply(null, itens.map((i) => Math.max.apply(null, i.valores))));
    const iw = W - m.l - m.r, ih = H - m.t - m.b, n = itens.length, banda = iw / n, ns = series.length;
    const larg = Math.min(28, banda * .8 / ns), gap = 2;
    const s = G.svg('svg', { viewBox: '0 0 ' + W + ' ' + H }, alvo), g = G.svg('g', {}, s);
    const xs = itens.map((_, i) => m.l + banda * i + banda / 2);
    G.eixoY(g, W, H, m, topo, K);
    G.rotulosX(g, itens, xs, W, H, m);
    itens.forEach((it, i) => it.valores.forEach((v, k) => {
      const h = Math.max(v ? 3 : 0, ih * v / topo), x = xs[i] - (ns * larg + (ns - 1) * gap) / 2 + k * (larg + gap);
      const r = G.svg('rect', { x: x, y: m.t + ih - h, width: larg, height: h, rx: Math.min(6, larg / 2.4), fill: series[k].cor, class: 'barra', style: '--d:' + (i * 45 + k * 90) }, g);
      G.dica(r, () => '<b>' + R(v) + '</b> <span>' + G.esc(series[k].nome) + '<br>' + G.esc(it.dica) + '</span>');
    }));
    legenda(alvo, series);
  }

  // barras horizontais empilhadas (recebido x em aberto por convênio)
  function empilhado(alvo, itens) {
    if (!itens.length) return G.vazio(alvo);
    alvo.innerHTML = '';
    const max = Math.max.apply(null, itens.map((c) => c.recebido + c.aberto)) || 1;
    itens.forEach((c, i) => {
      const linha = G.html('div', 'hrow hrow-emp', null, alvo), tot = c.recebido + c.aberto;
      const rot = G.html('span', 'hr-rot', c.rotulo, linha); rot.title = c.rotulo;
      const tr = G.html('div', 'trilho-emp', null, linha), bl = G.html('div', 'emp-bloco', null, tr);
      bl.style.setProperty('--w', (100 * tot / max).toFixed(1) + '%'); bl.style.setProperty('--d', i * 70);
      const a = G.html('div', 'seg-rec', null, bl), b = G.html('div', 'seg-ab', null, bl);
      a.style.flexGrow = c.recebido; b.style.flexGrow = c.aberto;
      G.html('span', 'hr-val', K(tot), linha);
      G.dica(linha, () => '<b>' + G.esc(c.rotulo) + '</b><br><span>Recebido: ' + R(c.recebido) + '<br>Em aberto: ' + R(c.aberto) + '<br>' +
        (tot ? G.fmt(100 * c.recebido / tot, 1) : 0) + '% recebido · ' + c.n + ' fatura(s)</span>');
    });
    legenda(alvo, [{ nome: 'Recebido', cor: COR_REC }, { nome: 'Em aberto', cor: COR_AB }]);
  }

  // barras simples com percentual (tributos)
  function percentuais(alvo, itens) {
    if (!itens.length) return G.vazio(alvo, 'Sem dados no período.');
    alvo.innerHTML = '';
    const max = Math.max.apply(null, itens.map((i) => i.valor)) || 1;
    const lista = G.html('div', 'g-hbar', null, alvo);
    itens.forEach((it, i) => {
      const linha = G.html('div', 'hrow', null, lista), rot = G.html('span', 'hr-rot', it.rotulo, linha); rot.title = it.rotulo;
      const tr = G.html('div', 'hr-trilho', null, linha), b = G.html('div', 'hr-barra', null, tr);
      b.style.setProperty('--w', (100 * it.valor / max).toFixed(1) + '%'); b.style.setProperty('--d', i * 70);
      b.style.background = 'linear-gradient(90deg,#c77d0a,#f0b429)';
      G.html('span', 'hr-val', G.fmt(it.valor, 1) + '%', linha);
    });
  }

  function desenhar() {
    grupo(document.getElementById('g-mensal'), D.mensal, [{ nome: 'Faturado (líquido)', cor: COR_FAT }, { nome: 'Recebido', cor: COR_REC }]);
    G.donut(document.getElementById('g-comp'), D.composicao, { fmtValor: K, sub: 'líquido no período', fonteCentro: 22 });
    empilhado(document.getElementById('g-conv'), D.convenios);
    G.barras(document.getElementById('g-aging'), D.aging, { fmtEixo: K, fmtValor: K, destaque: 'max',
      dicaFn: (it) => '<b>' + R(it.valor) + '</b> <span>' + G.esc(it.rotulo) + '</span>' });
    percentuais(document.getElementById('g-trib'), D.tributos);
  }
  desenhar();
  // avatares da lista (cor estável por nome)
  document.querySelectorAll('.avatar[data-nome]').forEach((a) => {
    let h = 0; for (const ch of a.dataset.nome) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    a.style.setProperty('--av', G.CORES[h % 7]);
  });
  let largAnt = innerWidth, t = null;
  addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => { if (Math.abs(innerWidth - largAnt) > 24) { largAnt = innerWidth; desenhar(); } }, 220); });
})();
