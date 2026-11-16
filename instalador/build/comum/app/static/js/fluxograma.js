'use strict';
/* Editor de fluxograma de processos (SVG próprio, sem bibliotecas).
   Etapas com formas padrão, ligações com seta e rótulo, raias por setor, cores por tipo / raia / situação / livre,
   arrastar, redimensionar, zoom, desfazer/refazer, salvamento automático e exportação em PNG e SVG. */
(() => {
  const raiz = document.getElementById('fx');
  if (!raiz) return;
  const NS = 'http://www.w3.org/2000/svg';
  const csrf = (document.querySelector('meta[name=csrf]') || {}).content || '';
  const tela = raiz.querySelector('[data-tela]');
  const props = raiz.querySelector('[data-props]');
  const legenda = raiz.querySelector('[data-legenda]');
  const estado = raiz.querySelector('[data-estado]');
  const seletorModo = raiz.querySelector('[data-modo]');
  const caixaGrade = raiz.querySelector('[data-grade]');
  let D;
  try { D = JSON.parse(document.getElementById('fx-dados').textContent) || {}; } catch (e) { D = {}; }
  D.nos = D.nos || []; D.ligacoes = D.ligacoes || []; D.raias = D.raias || []; D.modo_cor = D.modo_cor || 'tipo';
  seletorModo.value = D.modo_cor;

  const RAIA_H = 150, RAIA_ROT = 120, GRADE = 10;
  const NOMES_FORMA = {inicio: 'Início / fim', processo: 'Etapa', decisao: 'Decisão', documento: 'Documento', dados: 'Dados',
                       subprocesso: 'Subprocesso', espera: 'Espera', conector: 'Conector'};
  const COR_TIPO = {inicio: '#c8e6c9', processo: '#e3f2fd', decisao: '#fff3c4', documento: '#f3e5f5', dados: '#ffe0cc',
                    subprocesso: '#d7e3fc', espera: '#eceff1', conector: '#ffffff'};
  const STATUS = {a_implantar: ['A implantar', '#e0e0e0'], em_implantacao: ['Em implantação', '#ffe082'],
                  implantado: ['Implantado', '#a5d6a7'], revisao: ['Em revisão', '#ef9a9a']};
  const PALETA_RAIA = ['#e3f2fd', '#e8f5e9', '#fff8e1', '#fce4ec', '#ede7f6', '#e0f7fa', '#fbe9e7', '#f1f8e9'];

  // ------------------------------------------------------------------ utilidades
  const el = (nome, attrs, pai) => {
    const n = document.createElementNS(NS, nome);
    Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, v));
    if (pai) pai.append(n);
    return n;
  };
  const h = (tag, cls, txt) => { const n = document.createElement(tag); if (cls) n.className = cls; if (txt != null) n.textContent = txt; return n; };
  const snap = (v) => (caixaGrade.checked ? Math.round(v / GRADE) * GRADE : Math.round(v));
  const escurecer = (hex, f) => {
    const n = parseInt((hex || '#cccccc').slice(1), 16);
    const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((x) => Math.max(0, Math.round(x * f)));
    return '#' + c.map((x) => x.toString(16).padStart(2, '0')).join('');
  };
  const novoId = (pref, lista) => { let i = lista.length + 1; while (lista.some((x) => x.id === pref + i)) i += 1; return pref + i; };
  const no = (id) => D.nos.find((n) => n.id === id);
  const indiceRaia = (id) => D.raias.findIndex((r) => r.id === id);

  // ------------------------------------------------------------------ histórico (desfazer/refazer) e salvamento
  const pilha = [JSON.stringify(D)];
  let posPilha = 0, timerSalvar = null;
  const registrar = () => {
    const atual = JSON.stringify(D);
    if (atual === pilha[posPilha]) return;
    pilha.splice(posPilha + 1);
    pilha.push(atual);
    if (pilha.length > 80) pilha.shift();
    posPilha = pilha.length - 1;
    agendarSalvar();
  };
  const voltarPara = (i) => {
    if (i < 0 || i >= pilha.length) return;
    posPilha = i;
    D = JSON.parse(pilha[i]);
    sel = null;
    desenhar();
    agendarSalvar();
  };
  const agendarSalvar = () => {
    estado.textContent = 'Alterações não salvas…';
    estado.className = 'fx-salvo pendente';
    clearTimeout(timerSalvar);
    timerSalvar = setTimeout(salvar, 1200);
  };
  const salvar = async () => {
    try {
      const r = await fetch(raiz.dataset.salvar, {method: 'POST', credentials: 'same-origin',
        headers: {'X-CSRF-Token': csrf, Accept: 'application/json'}, body: new URLSearchParams({dados: JSON.stringify(D)})});
      const j = await r.json();
      if (!r.ok) throw new Error(j.erro || 'erro');
      estado.textContent = 'Salvo · ' + j.etapas + ' etapa(s) · v' + j.versao + (j.status === 'RASCUNHO' ? ' (rascunho)' : '');
      estado.className = 'fx-salvo';
    } catch (e) {
      estado.textContent = 'Não foi possível salvar. Tentando de novo…';
      estado.className = 'fx-salvo erro';
      clearTimeout(timerSalvar);
      timerSalvar = setTimeout(salvar, 5000);
    }
  };
  window.addEventListener('beforeunload', (ev) => { if (estado.classList.contains('pendente')) { ev.preventDefault(); ev.returnValue = ''; } });

  // ------------------------------------------------------------------ SVG base, zoom e rolagem
  const svg = el('svg', {class: 'fx-svg', role: 'img', 'aria-label': 'Fluxograma ' + (raiz.dataset.nome || '')}, tela);
  const defs = el('defs', {}, svg);
  const marcador = el('marker', {id: 'fx-seta', viewBox: '0 0 10 10', refX: '9', refY: '5', markerWidth: '7', markerHeight: '7', orient: 'auto-start-reverse'}, defs);
  el('path', {d: 'M0,0 L10,5 L0,10 z', fill: '#455a64'}, marcador);
  const padrao = el('pattern', {id: 'fx-grade', width: GRADE * 2, height: GRADE * 2, patternUnits: 'userSpaceOnUse'}, defs);
  el('path', {d: `M ${GRADE * 2} 0 L 0 0 0 ${GRADE * 2}`, fill: 'none', stroke: '#e3e8e5', 'stroke-width': '1'}, padrao);
  const mundo = el('g', {}, svg);
  let zoom = 1, panX = 20, panY = 20;
  const aplicarVista = () => {
    mundo.setAttribute('transform', `translate(${panX},${panY}) scale(${zoom})`);
    raiz.querySelector('[data-zoom]').textContent = Math.round(zoom * 100) + '%';
  };
  const ponto = (ev) => {
    const r = svg.getBoundingClientRect();
    return {x: (ev.clientX - r.left - panX) / zoom, y: (ev.clientY - r.top - panY) / zoom};
  };
  const limites = () => {
    let x1 = D.raias.length ? -RAIA_ROT : 0, y1 = 0, x2 = 600, y2 = Math.max(300, D.raias.length * RAIA_H);   // nomes das raias à esquerda
    D.nos.forEach((n) => { x1 = Math.min(x1, n.x); y1 = Math.min(y1, n.y); x2 = Math.max(x2, n.x + n.l); y2 = Math.max(y2, n.y + n.a); });
    return {x1: x1 - 30, y1: y1 - 30, x2: x2 + 60, y2: y2 + 40};
  };
  // minimo: na abertura o desenho não fica minúsculo (dá para rolar); o botão "Mostrar tudo" cabe tudo na tela
  const ajustar = (minimo) => {
    const b = limites();
    const r = svg.getBoundingClientRect();
    zoom = Math.max(typeof minimo === 'number' ? minimo : 0.25, Math.min(1.6, Math.min(r.width / (b.x2 - b.x1), r.height / (b.y2 - b.y1))));
    panX = -b.x1 * zoom + 10;
    panY = -b.y1 * zoom + 10;
    aplicarVista();
  };
  svg.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    const p = ponto(ev);
    const novo = Math.max(0.25, Math.min(2.5, zoom * (ev.deltaY < 0 ? 1.1 : 0.9)));
    const r = svg.getBoundingClientRect();
    panX = ev.clientX - r.left - p.x * novo;
    panY = ev.clientY - r.top - p.y * novo;
    zoom = novo;
    aplicarVista();
  }, {passive: false});

  // ------------------------------------------------------------------ cores
  const corNo = (n) => {
    if (D.modo_cor === 'livre' && n.cor) return n.cor;
    if (D.modo_cor === 'raia') { const i = indiceRaia(n.raia); return i >= 0 ? (D.raias[i].cor || PALETA_RAIA[i % PALETA_RAIA.length]) : '#ffffff'; }
    if (D.modo_cor === 'status') return (STATUS[n.status] || ['', '#ffffff'])[1];
    return COR_TIPO[n.forma] || '#ffffff';
  };

  // ------------------------------------------------------------------ formas
  const forma = (n, g, cor) => {
    const {l, a} = n;
    const borda = escurecer(cor, 0.55);
    const base = {fill: cor, stroke: borda, 'stroke-width': 1.6};
    switch (n.forma) {
      case 'inicio': return el('rect', Object.assign({x: 0, y: 0, width: l, height: a, rx: a / 2}, base), g);
      case 'decisao': return el('polygon', Object.assign({points: `${l / 2},0 ${l},${a / 2} ${l / 2},${a} 0,${a / 2}`}, base), g);
      case 'documento': return el('path', Object.assign({d: `M0,0 H${l} V${a - 10} C${l * 0.75},${a - 22} ${l * 0.25},${a + 4} 0,${a - 8} Z`}, base), g);
      case 'dados': return el('polygon', Object.assign({points: `${l * 0.12},0 ${l},0 ${l * 0.88},${a} 0,${a}`}, base), g);
      case 'subprocesso': {
        const r = el('rect', Object.assign({x: 0, y: 0, width: l, height: a, rx: 4}, base), g);
        el('line', {x1: 10, y1: 0, x2: 10, y2: a, stroke: borda, 'stroke-width': 1.4}, g);
        el('line', {x1: l - 10, y1: 0, x2: l - 10, y2: a, stroke: borda, 'stroke-width': 1.4}, g);
        return r;
      }
      case 'espera': return el('path', Object.assign({d: `M0,0 H${l - a / 2} A${a / 2},${a / 2} 0 0 1 ${l - a / 2},${a} H0 Z`}, base), g);
      case 'conector': return el('ellipse', Object.assign({cx: l / 2, cy: a / 2, rx: l / 2, ry: a / 2}, base), g);
      default: return el('rect', Object.assign({x: 0, y: 0, width: l, height: a, rx: 6}, base), g);
    }
  };
  const quebrarTexto = (txt, largura) => {
    const max = Math.max(6, Math.floor(largura / 7.2));
    const linhas = [];
    let atual = '';
    String(txt || '').split(/\s+/).forEach((p) => {
      if (!p) return;
      if ((atual + ' ' + p).trim().length > max && atual) { linhas.push(atual); atual = p; } else { atual = (atual + ' ' + p).trim(); }
    });
    if (atual) linhas.push(atual);
    return linhas.slice(0, 6);
  };

  // ------------------------------------------------------------------ ligação: pontos nas bordas e caminho em cotovelo
  const centro = (n) => ({x: n.x + n.l / 2, y: n.y + n.a / 2});
  const porta = (n, lado) => ({
    direita: {x: n.x + n.l, y: n.y + n.a / 2}, esquerda: {x: n.x, y: n.y + n.a / 2},
    baixo: {x: n.x + n.l / 2, y: n.y + n.a}, cima: {x: n.x + n.l / 2, y: n.y}}[lado]);
  const caminho = (a, b) => {
    const ca = centro(a), cb = centro(b);
    const dx = cb.x - ca.x, dy = cb.y - ca.y;
    if (Math.abs(dx) >= Math.abs(dy)) {
      const p1 = porta(a, dx >= 0 ? 'direita' : 'esquerda'), p2 = porta(b, dx >= 0 ? 'esquerda' : 'direita');
      const mx = (p1.x + p2.x) / 2;
      return {d: `M${p1.x},${p1.y} H${mx} V${p2.y} H${p2.x}`, meio: {x: mx, y: (p1.y + p2.y) / 2}};
    }
    const p1 = porta(a, dy >= 0 ? 'baixo' : 'cima'), p2 = porta(b, dy >= 0 ? 'cima' : 'baixo');
    const my = (p1.y + p2.y) / 2;
    return {d: `M${p1.x},${p1.y} V${my} H${p2.x} V${p2.y}`, meio: {x: (p1.x + p2.x) / 2, y: my}};
  };

  // ------------------------------------------------------------------ desenho
  let sel = null;          // {tipo: 'no'|'lig'|'raia', id|indice}
  let ligando = null;      // id do nó de origem quando o modo "Ligar" está ativo
  let modoLigar = false;
  const desenhar = () => {
    mundo.replaceChildren();
    const b = limites();
    if (caixaGrade.checked) el('rect', {x: b.x1 - 2000, y: b.y1 - 2000, width: b.x2 - b.x1 + 4000, height: b.y2 - b.y1 + 4000, fill: 'url(#fx-grade)', class: 'fx-fundo'}, mundo);
    else el('rect', {x: b.x1 - 2000, y: b.y1 - 2000, width: b.x2 - b.x1 + 4000, height: b.y2 - b.y1 + 4000, fill: '#ffffff', class: 'fx-fundo'}, mundo);
    // raias
    const largura = Math.max(b.x2, 900) + 200;
    D.raias.forEach((r, i) => {
      const cor = r.cor || PALETA_RAIA[i % PALETA_RAIA.length];
      const g = el('g', {class: 'fx-raia' + (sel && sel.tipo === 'raia' && sel.indice === i ? ' sel' : '')}, mundo);
      el('rect', {x: -RAIA_ROT, y: i * RAIA_H, width: largura + RAIA_ROT, height: RAIA_H, fill: cor, 'fill-opacity': 0.45, stroke: escurecer(cor, 0.7), 'stroke-width': 1}, g);
      el('rect', {x: -RAIA_ROT, y: i * RAIA_H, width: RAIA_ROT - 10, height: RAIA_H, fill: escurecer(cor, 0.92), stroke: escurecer(cor, 0.7)}, g);
      const t = el('text', {x: -RAIA_ROT / 2 - 5, y: i * RAIA_H + RAIA_H / 2, 'text-anchor': 'middle', 'dominant-baseline': 'middle', class: 'fx-raia-txt'}, g);
      quebrarTexto(r.nome || 'Raia', RAIA_ROT - 20).forEach((linha, k, arr) => el('tspan', {x: -RAIA_ROT / 2 - 5, dy: k === 0 ? `${-(arr.length - 1) * 0.6}em` : '1.2em'}, t).textContent = linha);
      g.addEventListener('pointerdown', (ev) => { if (ev.target.closest('.fx-no')) return; sel = {tipo: 'raia', indice: i}; desenhar(); });
    });
    // ligações
    D.ligacoes.forEach((e, i) => {
      const a = no(e.de), c = no(e.para);
      if (!a || !c) return;
      const k = caminho(a, c);
      const g = el('g', {class: 'fx-lig' + (sel && sel.tipo === 'lig' && sel.indice === i ? ' sel' : '')}, mundo);
      el('path', {d: k.d, fill: 'none', stroke: 'transparent', 'stroke-width': 12}, g);
      el('path', {d: k.d, fill: 'none', stroke: e.cor || '#455a64', 'stroke-width': 1.8, 'marker-end': 'url(#fx-seta)'}, g);
      if (e.rotulo) {
        const t = el('text', {x: k.meio.x, y: k.meio.y - 6, 'text-anchor': 'middle', class: 'fx-lig-txt'}, g);
        t.textContent = e.rotulo;
      }
      g.addEventListener('pointerdown', (ev) => { ev.stopPropagation(); sel = {tipo: 'lig', indice: i}; desenhar(); });
    });
    // etapas
    D.nos.forEach((n) => {
      const cor = corNo(n);
      const g = el('g', {class: 'fx-no' + (sel && sel.tipo === 'no' && sel.id === n.id ? ' sel' : '') + (ligando === n.id ? ' origem' : ''),
                         transform: `translate(${n.x},${n.y})`, 'data-id': n.id}, mundo);
      forma(n, g, cor);
      const t = el('text', {x: n.l / 2, y: n.a / 2, 'text-anchor': 'middle', 'dominant-baseline': 'middle', class: 'fx-no-txt'}, g);
      const linhas = quebrarTexto(n.texto || NOMES_FORMA[n.forma], n.forma === 'decisao' ? n.l * 0.62 : n.l - 16);
      linhas.forEach((linha, k) => { el('tspan', {x: n.l / 2, dy: k === 0 ? `${-(linhas.length - 1) * 0.6}em` : '1.2em'}, t).textContent = linha; });
      if (n.responsavel) { const r = el('text', {x: n.l / 2, y: n.a + 13, 'text-anchor': 'middle', class: 'fx-no-resp'}, g); r.textContent = '👤 ' + n.responsavel; }
      if (n.status && D.modo_cor !== 'status') el('circle', {cx: n.l - 7, cy: 7, r: 5, fill: STATUS[n.status][1], stroke: '#607d8b', 'stroke-width': 1}, g);
      el('rect', {x: n.l - 8, y: n.a - 8, width: 10, height: 10, class: 'fx-alca', 'data-alca': '1'}, g);
      g.addEventListener('pointerdown', (ev) => iniciarArraste(ev, n));
      g.addEventListener('dblclick', () => { sel = {tipo: 'no', id: n.id}; desenhar(); const c = props.querySelector('textarea'); if (c) c.focus(); });
    });
    desenharLegenda();
    desenharProps();
  };

  // ------------------------------------------------------------------ arrastar, redimensionar e mover a tela
  let arraste = null;
  const iniciarArraste = (ev, n) => {
    ev.stopPropagation();
    if (modoLigar) {
      if (!ligando) { ligando = n.id; desenhar(); return; }
      if (ligando !== n.id && !D.ligacoes.some((e) => e.de === ligando && e.para === n.id)) {
        D.ligacoes.push({de: ligando, para: n.id, rotulo: no(ligando).forma === 'decisao' ? (D.ligacoes.some((e) => e.de === ligando) ? 'Não' : 'Sim') : '', cor: ''});
        registrar();
      }
      ligando = null;
      desenhar();
      return;
    }
    sel = {tipo: 'no', id: n.id};
    const p = ponto(ev);
    arraste = {n, dx: p.x - n.x, dy: p.y - n.y, redim: ev.target.dataset.alca === '1', l0: n.l, a0: n.a, x0: p.x, y0: p.y, mexeu: false};
    svg.setPointerCapture(ev.pointerId);
    desenhar();
  };
  let pan = null;
  svg.addEventListener('pointerdown', (ev) => {
    if (arraste) return;
    if (ev.target.classList.contains('fx-fundo')) {
      pan = {x: ev.clientX - panX, y: ev.clientY - panY};
      sel = null;
      if (modoLigar) { ligando = null; }
      svg.setPointerCapture(ev.pointerId);
      desenhar();
    }
  });
  svg.addEventListener('pointermove', (ev) => {
    if (arraste) {
      const p = ponto(ev);
      const n = arraste.n;
      if (arraste.redim) { n.l = Math.max(60, snap(arraste.l0 + p.x - arraste.x0)); n.a = Math.max(36, snap(arraste.a0 + p.y - arraste.y0)); }
      else { n.x = snap(p.x - arraste.dx); n.y = snap(p.y - arraste.dy); }
      arraste.mexeu = true;
      desenhar();
    } else if (pan) {
      panX = ev.clientX - pan.x; panY = ev.clientY - pan.y;
      aplicarVista();
    }
  });
  const soltar = () => {
    if (arraste && arraste.mexeu) {
      const n = arraste.n;
      if (D.raias.length) {
        const i = Math.max(0, Math.min(D.raias.length - 1, Math.floor((n.y + n.a / 2) / RAIA_H)));
        n.raia = D.raias[i].id;
      }
      registrar();
      desenhar();
    }
    arraste = null; pan = null;
  };
  svg.addEventListener('pointerup', soltar);
  svg.addEventListener('pointercancel', soltar);

  // ------------------------------------------------------------------ painel de propriedades
  const campo = (rotulo, entrada) => { const l = h('label', 'fx-campo'); l.append(h('span', '', rotulo), entrada); return l; };
  const entradaTexto = (valor, aoMudar, area) => {
    const i = h(area ? 'textarea' : 'input');
    if (!area) i.type = 'text';
    i.value = valor || '';
    i.addEventListener('input', () => { aoMudar(i.value); desenharSoTela(); });
    i.addEventListener('change', registrar);
    return i;
  };
  const selecao = (opcoes, valor, aoMudar) => {
    const s = h('select');
    opcoes.forEach(([v, t]) => { const o = h('option', '', t); o.value = v; if (v === valor) o.selected = true; s.append(o); });
    s.addEventListener('change', () => { aoMudar(s.value); registrar(); desenhar(); });
    return s;
  };
  const entradaCor = (valor, aoMudar) => {
    const i = h('input'); i.type = 'color'; i.value = valor || '#e3f2fd';
    i.addEventListener('input', () => { aoMudar(i.value); desenharSoTela(); });
    i.addEventListener('change', registrar);
    return i;
  };
  const desenharSoTela = () => {
    const foco = document.activeElement;
    const inicio = foco && 'selectionStart' in foco ? foco.selectionStart : null;
    desenhar();
    // o painel foi redesenhado: devolve o foco ao campo equivalente
    if (foco && foco.dataset && foco.dataset.k) {
      const novo = props.querySelector(`[data-k="${foco.dataset.k}"]`);
      if (novo) { novo.focus(); if (inicio != null && 'setSelectionRange' in novo) try { novo.setSelectionRange(inicio, inicio); } catch (e) { /* cor */ } }
    }
  };
  const marcar = (elem, k) => { elem.dataset.k = k; return elem; };
  const desenharProps = () => {
    props.replaceChildren();
    if (modoLigar) { props.append(h('p', 'fx-dica', ligando ? 'Agora clique na etapa de destino.' : 'Clique na etapa de origem da ligação.')); }
    if (!sel) {
      props.append(h('p', 'sub', 'Selecione uma etapa, uma ligação ou uma raia para editar. Arraste as etapas; o canto inferior direito muda o tamanho. Arraste o fundo para mover a tela e use a roda do mouse para o zoom.'));
      return;
    }
    if (sel.tipo === 'no') {
      const n = no(sel.id);
      if (!n) return;
      props.append(h('h3', '', NOMES_FORMA[n.forma]));
      props.append(campo('Texto', marcar(entradaTexto(n.texto, (v) => { n.texto = v; }, true), 'texto')));
      props.append(campo('Forma', selecao(Object.entries(NOMES_FORMA), n.forma, (v) => { n.forma = v; })));
      props.append(campo('Raia (setor)', selecao([['', '(nenhuma)']].concat(D.raias.map((r) => [r.id, r.nome || r.id])), n.raia, (v) => {
        n.raia = v;
        const i = indiceRaia(v);
        if (i >= 0) n.y = i * RAIA_H + (RAIA_H - n.a) / 2;
      })));
      props.append(campo('Responsável', marcar(entradaTexto(n.responsavel, (v) => { n.responsavel = v; }), 'resp')));
      props.append(campo('Situação de implantação', selecao([['', '(não informada)']].concat(Object.entries(STATUS).map(([k, v]) => [k, v[0]])), n.status, (v) => { n.status = v; })));
      if (D.modo_cor === 'livre') props.append(campo('Cor', marcar(entradaCor(n.cor || corNo(n), (v) => { n.cor = v; }), 'cor')));
      else props.append(h('p', 'fx-dica', 'Para escolher a cor de cada etapa, mude "Cores por" para "escolha livre".'));
      props.append(campo('Observação', marcar(entradaTexto(n.obs, (v) => { n.obs = v; }, true), 'obs')));
      const dup = h('button', 'btn sec peq', 'Duplicar');
      dup.type = 'button';
      dup.addEventListener('click', () => { const c = Object.assign({}, n, {id: novoId('n', D.nos), x: n.x + 30, y: n.y + 30}); D.nos.push(c); sel = {tipo: 'no', id: c.id}; registrar(); desenhar(); });
      props.append(dup);
    } else if (sel.tipo === 'lig') {
      const e = D.ligacoes[sel.indice];
      if (!e) return;
      props.append(h('h3', '', 'Ligação'));
      props.append(h('p', 'sub', (no(e.de) || {}).texto + ' → ' + (no(e.para) || {}).texto));
      props.append(campo('Rótulo (ex.: Sim / Não)', marcar(entradaTexto(e.rotulo, (v) => { e.rotulo = v; }), 'rot')));
      props.append(campo('Cor da linha', marcar(entradaCor(e.cor || '#455a64', (v) => { e.cor = v; }), 'corl')));
      const inv = h('button', 'btn sec peq', 'Inverter o sentido');
      inv.type = 'button';
      inv.addEventListener('click', () => { [e.de, e.para] = [e.para, e.de]; registrar(); desenhar(); });
      props.append(inv);
    } else if (sel.tipo === 'raia') {
      const r = D.raias[sel.indice];
      if (!r) return;
      props.append(h('h3', '', 'Raia'));
      props.append(campo('Nome (setor ou responsável)', marcar(entradaTexto(r.nome, (v) => { r.nome = v; }), 'raia')));
      props.append(campo('Cor', marcar(entradaCor(r.cor || PALETA_RAIA[sel.indice % PALETA_RAIA.length], (v) => { r.cor = v; }), 'corr')));
      const mover = (d) => {
        const i = sel.indice, j = i + d;
        if (j < 0 || j >= D.raias.length) return;
        [D.raias[i], D.raias[j]] = [D.raias[j], D.raias[i]];
        D.nos.forEach((n) => { const k = indiceRaia(n.raia); if (k === i || k === j) n.y = k * RAIA_H + (RAIA_H - n.a) / 2; });
        sel.indice = j;
        registrar(); desenhar();
      };
      const sobe = h('button', 'btn sec peq', '↑ Subir'); sobe.type = 'button'; sobe.addEventListener('click', () => mover(-1));
      const desce = h('button', 'btn sec peq', '↓ Descer'); desce.type = 'button'; desce.addEventListener('click', () => mover(1));
      props.append(sobe, desce);
    }
  };

  // ------------------------------------------------------------------ legenda
  const desenharLegenda = () => {
    legenda.replaceChildren(h('strong', '', 'Legenda: '));
    let itens;
    if (D.modo_cor === 'raia') itens = D.raias.map((r, i) => [r.nome || r.id, r.cor || PALETA_RAIA[i % PALETA_RAIA.length]]);
    else if (D.modo_cor === 'status') itens = Object.values(STATUS);
    else if (D.modo_cor === 'tipo') itens = Object.entries(NOMES_FORMA).filter(([k]) => D.nos.some((n) => n.forma === k)).map(([k, v]) => [v, COR_TIPO[k]]);
    else itens = [];
    if (D.modo_cor !== 'status' && D.nos.some((n) => n.status)) itens = itens.concat(Object.values(STATUS).map(([t, c]) => ['● ' + t, c]));
    itens.forEach(([t, c]) => { const s = h('span', 'fx-leg'); const q = h('i'); q.style.background = c; s.append(q, document.createTextNode(t)); legenda.append(s); });
    if (!itens.length) legenda.append(h('span', 'sub', 'cores escolhidas livremente em cada etapa'));
  };

  // ------------------------------------------------------------------ barra de ferramentas
  raiz.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', () => {
    const r = svg.getBoundingClientRect();
    const tipo = b.dataset.add;
    const tam = {decisao: [150, 90], conector: [44, 44], inicio: [150, 56]}[tipo] || [170, 64];
    const x = snap((r.width / 2 - panX) / zoom - tam[0] / 2), y = snap((r.height / 2 - panY) / zoom - tam[1] / 2);
    const n = {id: novoId('n', D.nos), forma: tipo, texto: tipo === 'conector' ? '' : NOMES_FORMA[tipo], x, y, l: tam[0], a: tam[1], cor: '', raia: '', responsavel: '', status: '', obs: ''};
    if (D.raias.length) n.raia = D.raias[Math.max(0, Math.min(D.raias.length - 1, Math.floor((y + n.a / 2) / RAIA_H)))].id;
    D.nos.push(n);
    sel = {tipo: 'no', id: n.id};
    registrar(); desenhar();
  }));
  const botaoLigar = raiz.querySelector('[data-acao="ligar"]');
  const excluirSelecionado = () => {
    if (!sel) return;
    if (sel.tipo === 'no') { D.nos = D.nos.filter((n) => n.id !== sel.id); D.ligacoes = D.ligacoes.filter((e) => e.de !== sel.id && e.para !== sel.id); }
    else if (sel.tipo === 'lig') D.ligacoes.splice(sel.indice, 1);
    else if (sel.tipo === 'raia') {
      const r = D.raias[sel.indice];
      if (!r || !confirm('Excluir a raia "' + (r.nome || '') + '"? As etapas continuam no desenho.')) return;
      D.raias.splice(sel.indice, 1);
      D.nos.forEach((n) => { if (n.raia === r.id) n.raia = ''; });
    }
    sel = null; registrar(); desenhar();
  };
  raiz.querySelectorAll('[data-acao]').forEach((b) => b.addEventListener('click', () => {
    const a = b.dataset.acao;
    if (a === 'ligar') { modoLigar = !modoLigar; ligando = null; botaoLigar.classList.toggle('ativo', modoLigar); desenhar(); }
    if (a === 'raia') { D.raias.push({id: novoId('r', D.raias), nome: 'Setor ' + (D.raias.length + 1), cor: ''}); sel = {tipo: 'raia', indice: D.raias.length - 1}; registrar(); desenhar(); }
    if (a === 'excluir') excluirSelecionado();
    if (a === 'desfazer') voltarPara(posPilha - 1);
    if (a === 'refazer') voltarPara(posPilha + 1);
    if (a === 'mais') { zoom = Math.min(2.5, zoom * 1.15); aplicarVista(); }
    if (a === 'menos') { zoom = Math.max(0.25, zoom / 1.15); aplicarVista(); }
    if (a === 'ajustar') ajustar(0.25);
  }));
  seletorModo.addEventListener('change', () => { D.modo_cor = seletorModo.value; registrar(); desenhar(); });
  caixaGrade.addEventListener('change', desenhar);
  tela.addEventListener('keydown', (ev) => {
    if (ev.target !== tela) return;
    if (ev.key === 'Delete' || ev.key === 'Backspace') { ev.preventDefault(); excluirSelecionado(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') { ev.preventDefault(); voltarPara(posPilha - 1); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'y') { ev.preventDefault(); voltarPara(posPilha + 1); }
    if (sel && sel.tipo === 'no' && ev.key.startsWith('Arrow')) {
      ev.preventDefault();
      const n = no(sel.id), p = ev.shiftKey ? 1 : GRADE;
      if (ev.key === 'ArrowLeft') n.x -= p; if (ev.key === 'ArrowRight') n.x += p; if (ev.key === 'ArrowUp') n.y -= p; if (ev.key === 'ArrowDown') n.y += p;
      registrar(); desenhar();
    }
  });
  svg.addEventListener('pointerdown', () => tela.focus({preventScroll: true}));

  // ------------------------------------------------------------------ exportar
  const svgSolto = () => {
    const b = limites();
    const x1 = D.raias.length ? Math.min(b.x1, -RAIA_ROT) : b.x1;
    const copia = svg.cloneNode(true);
    copia.setAttribute('xmlns', NS);
    copia.setAttribute('width', b.x2 - x1);
    copia.setAttribute('height', b.y2 - b.y1 + 20);
    copia.setAttribute('viewBox', `${x1} ${b.y1} ${b.x2 - x1} ${b.y2 - b.y1 + 20}`);
    copia.querySelector('g').removeAttribute('transform');
    copia.querySelectorAll('.fx-fundo').forEach((f) => f.setAttribute('fill', '#ffffff'));
    copia.querySelectorAll('.fx-alca').forEach((a) => a.remove());
    const estilo = document.createElementNS(NS, 'style');
    estilo.textContent = '.fx-no-txt{font:600 12px Segoe UI,Arial,sans-serif;fill:#1d2522}.fx-no-resp{font:10px Segoe UI,Arial,sans-serif;fill:#455a64}' +
      '.fx-lig-txt{font:600 11px Segoe UI,Arial,sans-serif;fill:#263238;paint-order:stroke;stroke:#fff;stroke-width:4px}.fx-raia-txt{font:700 12px Segoe UI,Arial,sans-serif;fill:#263238}';
    copia.prepend(estilo);
    return new XMLSerializer().serializeToString(copia);
  };
  const baixar = (url, nome) => { const a = document.createElement('a'); a.href = url; a.download = nome; document.body.append(a); a.click(); a.remove(); };
  const nomeArq = (raiz.dataset.nome || 'fluxograma').replace(/[^\w\-À-ÿ ]+/g, '').trim() || 'fluxograma';
  document.querySelectorAll('[data-fx]').forEach((b) => b.addEventListener('click', () => {
    const texto = svgSolto();
    const url = URL.createObjectURL(new Blob([texto], {type: 'image/svg+xml'}));
    if (b.dataset.fx === 'svg') { baixar(url, nomeArq + '.svg'); setTimeout(() => URL.revokeObjectURL(url), 2000); return; }
    const img = new Image();
    img.onload = () => {
      const escala = 2;
      const c = document.createElement('canvas');
      c.width = img.width * escala; c.height = img.height * escala;
      const ctx = c.getContext('2d');
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, c.width, c.height);
      ctx.scale(escala, escala); ctx.drawImage(img, 0, 0);
      c.toBlob((blob) => { const u = URL.createObjectURL(blob); baixar(u, nomeArq + '.png'); setTimeout(() => URL.revokeObjectURL(u), 2000); });
      URL.revokeObjectURL(url);
    };
    img.src = url;
  }));
  window.addEventListener('beforeprint', () => ajustar(0.1));

  desenhar();
  requestAnimationFrame(() => ajustar(0.6));
})();
