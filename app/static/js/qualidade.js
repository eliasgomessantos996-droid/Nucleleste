'use strict';
/* Gráficos e desenhos da Qualidade (SVG próprio, sem bibliotecas): linhas dos indicadores, Pareto, espinha de peixe
   (Ishikawa), organograma e a prévia da nota na avaliação de fornecedores. */
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const el = (nome, attrs, pai, texto) => {
    const n = document.createElementNS(NS, nome);
    Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, v));
    if (texto != null) n.textContent = texto;
    if (pai) pai.append(n);
    return n;
  };
  const cor = (v, f) => (getComputedStyle(document.body).getPropertyValue(v) || '').trim() || f;
  const VERDE = cor('--verde', '#255f39'), BRILHO = cor('--brilho-2', '#2f9e6a');
  const fmt = (v, d) => Number(v).toLocaleString('pt-BR', {minimumFractionDigits: d || 0, maximumFractionDigits: d == null ? 1 : d});
  const ler = (n, attr) => { try { return JSON.parse(n.getAttribute(attr)); } catch (e) { return null; } };
  const quebrar = (txt, max) => {
    const linhas = []; let atual = '';
    String(txt || '').split(/\s+/).forEach((p) => {
      if ((atual + ' ' + p).trim().length > max && atual) { linhas.push(atual); atual = p; } else atual = (atual + ' ' + p).trim();
    });
    if (atual) linhas.push(atual);
    return linhas;
  };
  const multilinha = (t, x, linhas, alt) => linhas.forEach((l, i) => el('tspan', {x, dy: i === 0 ? 0 : alt || '1.15em'}, t, l));

  // ------------------------------------------------------------------ linha dos indicadores (últimos meses, com a meta)
  document.querySelectorAll('.q-spark[data-serie]').forEach((cx) => {
    const serie = ler(cx, 'data-serie') || [];
    const meta = parseFloat(cx.dataset.meta);
    const vals = serie.map((s) => s.valor).filter((v) => v != null);
    if (!vals.length) { cx.textContent = 'sem histórico'; cx.classList.add('vazio'); return; }
    const W = 220, H = 54, P = 6;
    const todos = vals.concat(isFinite(meta) ? [meta] : []);
    let min = Math.min(...todos), max = Math.max(...todos);
    if (max === min) { max += 1; min -= 1; }
    const x = (i) => P + i * (W - 2 * P) / Math.max(1, serie.length - 1);
    const y = (v) => H - P - (v - min) / (max - min) * (H - 2 * P);
    const s = el('svg', {viewBox: `0 0 ${W} ${H + 14}`, class: 'q-spark-svg', role: 'img', 'aria-label': 'Evolução nos últimos meses'}, cx);
    if (isFinite(meta)) el('line', {x1: P, x2: W - P, y1: y(meta), y2: y(meta), stroke: '#c62828', 'stroke-dasharray': '4 3', 'stroke-width': 1}, s);
    let d = '';
    serie.forEach((p, i) => { if (p.valor == null) return; d += (d ? ' L' : 'M') + x(i).toFixed(1) + ',' + y(p.valor).toFixed(1); });
    el('path', {d, fill: 'none', stroke: VERDE, 'stroke-width': 2, 'stroke-linejoin': 'round'}, s);
    serie.forEach((p, i) => {
      el('text', {x: x(i), y: H + 12, 'text-anchor': 'middle', class: 'q-spark-rot'}, s, p.rotulo);
      if (p.valor == null) return;
      const c = el('circle', {cx: x(i), cy: y(p.valor), r: 3, fill: VERDE}, s);
      el('title', {}, c, p.rotulo + ': ' + fmt(p.valor) + (cx.dataset.unidade === '%' ? '%' : ''));
    });
  });

  // ------------------------------------------------------------------ Pareto: barras, % acumulado e linha dos 80%
  document.querySelectorAll('.q-pareto[data-pareto]').forEach((cx) => {
    const itens = (ler(cx, 'data-pareto') || []).slice(0, 25);
    if (!itens.length) return;
    const W = 900, H = 380, E = 60, D = 50, T = 20, B = 110;
    const larg = (W - E - D) / itens.length;
    const max = itens[0].valor || 1;
    const s = el('svg', {viewBox: `0 0 ${W} ${H}`, class: 'q-pareto-svg', role: 'img', 'aria-label': 'Gráfico de Pareto'}, cx);
    const yv = (v) => H - B - v / max * (H - B - T);
    const yp = (p) => H - B - p / 100 * (H - B - T);
    for (let k = 0; k <= 4; k += 1) {
      const p = k * 25;
      el('line', {x1: E, x2: W - D, y1: yp(p), y2: yp(p), stroke: '#e3e8e5'}, s);
      el('text', {x: W - D + 6, y: yp(p) + 4, class: 'q-eixo'}, s, p + '%');
      el('text', {x: E - 6, y: yv(max * k / 4) + 4, 'text-anchor': 'end', class: 'q-eixo'}, s, fmt(max * k / 4, 0));
    }
    el('line', {x1: E, x2: W - D, y1: yp(80), y2: yp(80), stroke: '#c62828', 'stroke-dasharray': '6 4', 'stroke-width': 1.2}, s);
    el('text', {x: E + 4, y: yp(80) - 5, class: 'q-eixo', fill: '#c62828'}, s, '80%');
    let d = '';
    itens.forEach((it, i) => {
      const x = E + i * larg;
      const b = el('rect', {x: x + larg * 0.12, y: yv(it.valor), width: larg * 0.76, height: H - B - yv(it.valor), rx: 3,
                            fill: it.classe === 'A' ? VERDE : it.classe === 'B' ? BRILHO : '#b0bdb6'}, s);
      el('title', {}, b, `${it.rotulo}: ${fmt(it.valor)} (${fmt(it.pct)}%; acumulado ${fmt(it.acum)}%)`);
      el('text', {x: x + larg / 2, y: yv(it.valor) - 4, 'text-anchor': 'middle', class: 'q-valor'}, s, fmt(it.valor));
      const t = el('text', {x: x + larg / 2, y: H - B + 14, 'text-anchor': 'end', class: 'q-rot', transform: `rotate(-35 ${x + larg / 2} ${H - B + 14})`}, s);
      t.textContent = it.rotulo.length > 26 ? it.rotulo.slice(0, 25) + '…' : it.rotulo;
      d += (i ? ' L' : 'M') + (x + larg / 2).toFixed(1) + ',' + yp(it.acum).toFixed(1);
    });
    el('path', {d, fill: 'none', stroke: '#e07a5f', 'stroke-width': 2.4}, s);
    itens.forEach((it, i) => {
      const c = el('circle', {cx: E + i * larg + larg / 2, cy: yp(it.acum), r: 3.5, fill: '#e07a5f'}, s);
      el('title', {}, c, 'Acumulado: ' + fmt(it.acum) + '%');
    });
  });

  // ------------------------------------------------------------------ Ishikawa (espinha de peixe, 6M)
  document.querySelectorAll('.q-ishikawa[data-ishikawa]').forEach((cx) => {
    const dados = ler(cx, 'data-ishikawa');
    if (!dados) return;
    const grupos = dados.grupos;
    const maxCausas = Math.max(2, ...grupos.map((g) => g.causas.length));
    const W = 1100, alturaOsso = 60 + maxCausas * 26, H = alturaOsso * 2 + 40, meio = H / 2, cabeca = 210;
    const s = el('svg', {viewBox: `0 0 ${W} ${H}`, class: 'q-ishikawa-svg', role: 'img', 'aria-label': 'Diagrama de Ishikawa'}, cx);
    el('line', {x1: 30, y1: meio, x2: W - cabeca, y2: meio, stroke: '#37474f', 'stroke-width': 4}, s);
    el('polygon', {points: `${W - cabeca},${meio - 14} ${W - cabeca + 18},${meio} ${W - cabeca},${meio + 14}`, fill: '#37474f'}, s);
    el('rect', {x: W - cabeca + 22, y: meio - 60, width: cabeca - 30, height: 120, rx: 10, fill: VERDE}, s);
    const tp = el('text', {x: W - cabeca / 2 + 8, y: meio - 6 - (Math.min(5, quebrar(dados.problema, 22).length) - 1) * 9, 'text-anchor': 'middle', class: 'q-isk-cab'}, s);
    multilinha(tp, W - cabeca / 2 + 8, quebrar(dados.problema, 22).slice(0, 5));
    const passo = (W - cabeca - 80) / 3;
    grupos.forEach((g, i) => {
      const cima = i < 3;
      const col = i % 3;
      const xBase = 80 + passo * col + passo * 0.85;
      const yPonta = cima ? 34 : H - 34;
      const xPonta = xBase - alturaOsso * 0.55;
      el('line', {x1: xPonta, y1: yPonta, x2: xBase, y2: meio, stroke: '#546e7a', 'stroke-width': 2.4}, s);
      el('rect', {x: xPonta - 70, y: cima ? yPonta - 26 : yPonta + 2, width: 140, height: 24, rx: 12, fill: '#eceff1', stroke: '#90a4ae'}, s);
      el('text', {x: xPonta, y: cima ? yPonta - 9 : yPonta + 19, 'text-anchor': 'middle', class: 'q-isk-cat'}, s, g.categoria);
      g.causas.forEach((c, k) => {
        const f = (k + 1) / (g.causas.length + 1);
        const yC = yPonta + (meio - yPonta) * f;
        const xC = xPonta + (xBase - xPonta) * f;
        el('line', {x1: xC - 150, y1: yC, x2: xC, y2: yC, stroke: c.principal ? '#c62828' : '#90a4ae', 'stroke-width': c.principal ? 2 : 1.2}, s);
        const t = el('text', {x: xC - 150, y: yC - 4, class: 'q-isk-causa' + (c.principal ? ' principal' : '')}, s);
        t.textContent = (c.principal ? '★ ' : '') + (c.texto.length > 34 ? c.texto.slice(0, 33) + '…' : c.texto);
        el('title', {}, t, c.texto);
      });
    });
  });

  // ------------------------------------------------------------------ organograma (árvore arrumada automaticamente)
  document.querySelectorAll('.q-org[data-org]').forEach((cx) => {
    const nos = ler(cx, 'data-org') || [];
    if (!nos.length) return;
    const filhos = {};
    nos.forEach((n) => { (filhos[n.pai_id || 0] = filhos[n.pai_id || 0] || []).push(n); });
    Object.values(filhos).forEach((l) => l.sort((a, b) => (a.ordem - b.ordem) || (a.id - b.id)));
    const LW = 190, LH = 74, GX = 24, GY = 56;
    const largura = (n) => { const f = filhos[n.id] || []; n._w = f.length ? Math.max(LW, f.reduce((s, x) => s + largura(x) + GX, -GX)) : LW; return n._w; };
    const raizes = filhos[0] || [];
    let total = raizes.reduce((s, r) => s + largura(r) + GX * 2, 0);
    let prof = 0;
    const posicionar = (n, x, nivel) => {
      n._x = x + n._w / 2 - LW / 2; n._y = nivel * (LH + GY);
      prof = Math.max(prof, nivel);
      let cursor = x;
      (filhos[n.id] || []).forEach((f) => { posicionar(f, cursor, nivel + 1); cursor += f._w + GX; });
    };
    let cur = 0;
    raizes.forEach((r) => { posicionar(r, cur, 0); cur += r._w + GX * 2; });
    total = Math.max(total, LW);
    const W = total + 20, H = (prof + 1) * (LH + GY);
    const s = el('svg', {viewBox: `-10 -10 ${W} ${H}`, class: 'q-org-svg', role: 'img', 'aria-label': 'Organograma'}, cx);
    nos.forEach((n) => {
      if (!n.pai_id) return;
      const p = nos.find((x) => x.id === n.pai_id);
      if (!p || p._x == null) return;
      const x1 = p._x + LW / 2, y1 = p._y + LH, x2 = n._x + LW / 2, y2 = n._y, my = y1 + GY / 2;
      el('path', {d: `M${x1},${y1} V${my} H${x2} V${y2}`, fill: 'none', stroke: '#90a4ae', 'stroke-width': 1.6}, s);
    });
    nos.forEach((n) => {
      if (n._x == null) return;
      const g = el('g', {class: 'q-org-no', transform: `translate(${n._x},${n._y})`, tabindex: 0}, s);
      el('rect', {width: LW, height: LH, rx: 10, fill: '#ffffff', stroke: n.cor || VERDE, 'stroke-width': 1.6}, g);
      el('rect', {width: LW, height: 8, rx: 4, fill: n.cor || VERDE}, g);
      el('text', {x: LW / 2, y: 28, 'text-anchor': 'middle', class: 'q-org-cargo'}, g, n.cargo.length > 26 ? n.cargo.slice(0, 25) + '…' : n.cargo);
      if (n.pessoa) el('text', {x: LW / 2, y: 47, 'text-anchor': 'middle', class: 'q-org-pessoa'}, g, n.pessoa.length > 28 ? n.pessoa.slice(0, 27) + '…' : n.pessoa);
      if (n.setor) el('text', {x: LW / 2, y: 64, 'text-anchor': 'middle', class: 'q-org-setor'}, g, n.setor);
      const ir = () => { location.href = cx.dataset.editar + '?editar=' + n.id; };
      g.addEventListener('click', ir);
      g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ir(); });
      el('title', {}, g, 'Clique para editar');
    });
    const botao = document.querySelector('[data-org-png]');
    if (botao) botao.addEventListener('click', () => {
      const copia = s.cloneNode(true);
      copia.setAttribute('xmlns', NS); copia.setAttribute('width', W * 1.5); copia.setAttribute('height', H * 1.5);
      const st = document.createElementNS(NS, 'style');
      st.textContent = '.q-org-cargo{font:700 13px Segoe UI,Arial;fill:#1d2522}.q-org-pessoa{font:12px Segoe UI,Arial;fill:#37474f}.q-org-setor{font:11px Segoe UI,Arial;fill:#78909c}';
      copia.prepend(st);
      const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copia)], {type: 'image/svg+xml'}));
      const img = new Image();
      img.onload = () => {
        const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
        const ctx = c.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height); ctx.drawImage(img, 0, 0);
        c.toBlob((b) => { const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'organograma.png'; a.click(); });
        URL.revokeObjectURL(url);
      };
      img.src = url;
    });
  });

  // ------------------------------------------------------------------ avaliação de fornecedor: prévia da nota
  const fForn = document.querySelector('[data-forn-form]');
  if (fForn) {
    const previa = fForn.querySelector('[data-previa]');
    const calcular = () => {
      const pesos = {}, notas = {};
      fForn.querySelectorAll('input[type=radio][data-peso]').forEach((r) => { pesos[r.name] = +r.dataset.peso; if (r.checked) notas[r.name] = +r.value; });
      const nomes = Object.keys(pesos);
      const feitas = nomes.filter((n) => notas[n]);
      if (!feitas.length) return;
      const pts = feitas.reduce((s, n) => s + pesos[n] * notas[n], 0), max = feitas.reduce((s, n) => s + pesos[n] * 5, 0);
      const pct = 100 * pts / max;
      const classe = pct >= 80 ? 'APROVADO' : pct >= 60 ? 'APROVADO COM RESTRIÇÕES' : 'REPROVADO';
      previa.textContent = `Resultado parcial: ${fmt(pct)}% da nota máxima · ${classe}` + (feitas.length < nomes.length ? ` (${feitas.length} de ${nomes.length} critérios)` : '');
      previa.className = 'q-previa ' + (pct >= 80 ? 'ok' : pct >= 60 ? 'atencao' : 'critico');
    };
    fForn.addEventListener('change', calcular);
    calcular();
  }
})();
