'use strict';
/* Cartões da NucleAI IA (tabela, gráfico, acessos, proposta, links, perfil do treinador).
   Usado nas Mensagens (chat.js) e no chat de treinamento (nucleai_treino.js). Todo texto entra por textContent. */
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const TIPOS = new Set(['IA_TABELA', 'IA_GRAFICO', 'IA_ACESSOS', 'IA_PROPOSTA', 'IA_LINKS', 'IA_PERFIL', 'IA_ILUSTRACAO']);
  const ICONES = { IA_TABELA: 'clipboard-list', IA_GRAFICO: 'chart-column', IA_ACESSOS: 'shield-check', IA_PROPOSTA: 'list-checks',
                   IA_LINKS: 'send', IA_PERFIL: 'user-cog', IA_ILUSTRACAO: 'clipboard-list' };
  const ICONES_ILUS = { planilha: 'file-chart-column', grafico: 'chart-column', cartao_info: 'clipboard-list',
                        cartao_decisao: 'circle-help', cartao_permissao: 'shield-check', texto: 'file-text' };
  const ENTIDADES = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#x27;': "'" };
  const txtLimpo = (v) => String(v ?? '').replace(/&(?:amp|lt|gt|quot|#x27);/g, (m) => ENTIDADES[m]);

  const el = (tag, cls, txt) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined && txt !== null) e.textContent = txtLimpo(txt);
    return e;
  };
  const svg = (tag, attrs) => {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => e.setAttribute(k, v));
    return e;
  };
  const icone = (nome, tam) => {
    const s = svg('svg', { class: 'ic', width: tam || 16, height: tam || 16, 'aria-hidden': 'true' });
    const u = svg('use', { href: '/static/img/icones.svg#i-' + nome });
    s.append(u);
    return s;
  };
  const num = (v) => (typeof v === 'number' ? v.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) : String(v ?? ''));

  // resposta padrão dos botões Sim/Não: envia pelo formulário do chat aberto
  const responderPadrao = (texto) => {
    const form = document.getElementById('chat-form');
    const campo = form && form.querySelector('textarea, input[name=corpo]');
    if (!form || !campo) return;
    campo.value = texto;
    if (form.requestSubmit) form.requestSubmit(); else form.submit();
  };

  const topo = (c) => {
    const t = el('div', 'nia-topo');
    const selo = el('span', 'nia-selo');
    let nomeIc = ICONES[c.tipo] || 'bot';
    if (c.tipo === 'IA_ILUSTRACAO') {
      nomeIc = (c.subtipo === 'cartao_info' && c.dados && c.dados.icone) || ICONES_ILUS[c.subtipo] || 'bot';
    }
    selo.append(icone(nomeIc, 15));
    const tt = el('div', 'nia-tt');
    tt.append(el('b', '', c.titulo || 'Resultado'));
    if (c.subtitulo) tt.append(el('small', '', c.subtitulo));
    t.append(selo, tt);
    return t;
  };
  const pe = (c, card) => {
    if (c.rodape) card.append(el('p', 'nia-rodape', c.rodape));
    if (c.link && c.link.url) {
      const a = el('a', 'nia-link');
      a.href = c.link.url;
      a.append(icone('send', 14), el('span', '', c.link.rotulo || 'Abrir'));
      card.append(a);
    }
  };

  // ------------------------------------------------------------ tabela
  const tabela = (c, card) => {
    const linhas = c.linhas || [];
    if (!linhas.length) { card.append(el('p', 'nia-vazio', c.vazio || 'Nada encontrado.')); return; }
    const filtro = el('input', 'nia-filtro');
    filtro.type = 'search';
    filtro.placeholder = 'Filtrar nesta lista...';
    const wrap = el('div', 'nia-tabela-wrap');
    const t = el('table', 'nia-tabela');
    const th = el('tr');
    (c.colunas || []).forEach((n) => th.append(el('th', '', n)));
    const thead = el('thead'); thead.append(th);
    const tb = el('tbody');
    linhas.forEach((ln, i) => {
      const tr = el('tr');
      tr.style.animationDelay = Math.min(i, 30) * 18 + 'ms';
      ln.forEach((v, j) => {
        const td = el('td', '', v);
        if ((c.colunas || [])[j] === 'Status') td.classList.add('nia-st', 'st-' + String(v).toLowerCase());
        tr.append(td);
      });
      tb.append(tr);
    });
    t.append(thead, tb);
    wrap.append(t);
    filtro.addEventListener('input', () => {
      const q = filtro.value.trim().toLocaleLowerCase('pt-BR');
      tb.querySelectorAll('tr').forEach((tr) => { tr.hidden = !!q && !tr.textContent.toLocaleLowerCase('pt-BR').includes(q); });
    });
    if (linhas.length > 6) card.append(filtro);
    card.append(wrap);
  };

  // ------------------------------------------------------------ gráfico (barras ou linha com projeção)
  const grafico = (c, card) => {
    const series = c.series || [];
    const pontos = series.flatMap((s) => s.pontos || []);
    if (!pontos.length) { card.append(el('p', 'nia-vazio', 'Sem dados no período.')); return; }
    if (c.destaque) {
      const d = el('div', 'nia-destaque');
      d.append(el('small', '', c.destaque.rotulo), el('b', '', num(c.destaque.valor)));
      if (c.destaque.faixa) d.append(el('span', '', 'faixa provável: ' + c.destaque.faixa));
      if (c.destaque.extra) d.append(el('span', '', c.destaque.extra));
      card.append(d);
    }
    const W = 560, H = 230, ml = 40, mr = 12, mt = 14, mb = 42;
    const max = Math.max(1, ...pontos.map((p) => Math.max(p.valor || 0, p.max || 0)));
    const escalaY = (v) => mt + (H - mt - mb) * (1 - v / max);
    const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'nia-graf', role: 'img', 'aria-label': c.titulo || 'Gráfico' });
    for (let i = 0; i <= 4; i += 1) {   // grade
      const v = (max * i) / 4, y = escalaY(v);
      s.append(svg('line', { x1: ml, x2: W - mr, y1: y, y2: y, class: 'g-grade' }));
      const t = svg('text', { x: ml - 6, y: y + 4, class: 'g-eixo', 'text-anchor': 'end' });
      t.textContent = num(Math.round(v));
      s.append(t);
    }
    if (c.modo === 'barras') {
      const pts = series[0].pontos;
      const passo = (W - ml - mr) / pts.length, larg = Math.min(46, passo * 0.62);
      pts.forEach((p, i) => {
        const x = ml + passo * i + (passo - larg) / 2, y = escalaY(p.valor || 0);
        const r = svg('rect', { x, y, width: larg, height: Math.max(1, H - mb - y), rx: 4, class: 'g-barra' });
        r.style.animationDelay = i * 45 + 'ms';
        const tit = svg('title'); tit.textContent = `${p.rotulo}: ${num(p.valor)}`; r.append(tit);
        s.append(r);
        const v = svg('text', { x: x + larg / 2, y: y - 4, class: 'g-valor', 'text-anchor': 'middle' }); v.textContent = num(p.valor); s.append(v);
        const t = svg('text', { x: x + larg / 2, y: H - mb + 15, class: 'g-eixo', 'text-anchor': 'middle' });
        t.textContent = String(p.rotulo).length > 12 ? String(p.rotulo).slice(0, 11) + '…' : p.rotulo;
        s.append(t);
      });
    } else {
      // linha: a série real e a projeção seguem o mesmo eixo X (histórico + futuro)
      const rotulos = [];
      series.forEach((se) => (se.pontos || []).forEach((p) => { if (!rotulos.includes(p.rotulo)) rotulos.push(p.rotulo); }));
      const passo = rotulos.length > 1 ? (W - ml - mr - 20) / (rotulos.length - 1) : 0;
      const X = (rot) => ml + 10 + passo * rotulos.indexOf(rot);
      series.forEach((se) => {
        const pts = se.pontos || [];
        if (se.estilo === 'projecao') {
          const real = series.find((x) => x.estilo === 'real');
          const ult = real && real.pontos && real.pontos[real.pontos.length - 1];
          const cima = pts.map((p) => `${X(p.rotulo)},${escalaY(p.max ?? p.valor)}`);
          const baixo = pts.slice().reverse().map((p) => `${X(p.rotulo)},${escalaY(p.min ?? p.valor)}`);
          if (ult) { cima.unshift(`${X(ult.rotulo)},${escalaY(ult.valor)}`); baixo.push(`${X(ult.rotulo)},${escalaY(ult.valor)}`); }
          s.append(svg('polygon', { points: cima.concat(baixo).join(' '), class: 'g-faixa' }));
          const linha = (ult ? [ult] : []).concat(pts).map((p) => `${X(p.rotulo)},${escalaY(p.valor)}`).join(' ');
          s.append(svg('polyline', { points: linha, class: 'g-linha proj' }));
        } else {
          s.append(svg('polyline', { points: pts.map((p) => `${X(p.rotulo)},${escalaY(p.valor)}`).join(' '), class: 'g-linha real' }));
        }
        pts.forEach((p, i) => {
          const cx = X(p.rotulo), cy = escalaY(p.valor);
          const ponto = svg('circle', { cx, cy, r: 4, class: 'g-ponto ' + (se.estilo === 'projecao' ? 'proj' : 'real') });
          ponto.style.animationDelay = 300 + i * 60 + 'ms';
          const tit = svg('title');
          tit.textContent = `${p.rotulo}: ${num(p.valor)}` + (p.min !== undefined ? ` (entre ${num(p.min)} e ${num(p.max)})` : '');
          ponto.append(tit);
          s.append(ponto);
          if (se.estilo === 'projecao') {
            const v = svg('text', { x: cx, y: cy - 9, class: 'g-valor proj', 'text-anchor': 'middle' }); v.textContent = num(p.valor); s.append(v);
          }
        });
      });
      const pulo = Math.ceil(rotulos.length / 12);
      rotulos.forEach((r, i) => {
        if (i % pulo) return;
        const t = svg('text', { x: X(r), y: H - mb + 15, class: 'g-eixo', 'text-anchor': 'middle' }); t.textContent = r; s.append(t);
      });
      const leg = el('div', 'nia-legenda');
      series.forEach((se) => { const i = el('span', 'lg ' + (se.estilo === 'projecao' ? 'proj' : 'real')); i.append(el('i'), el('span', '', se.nome)); leg.append(i); });
      card.append(leg);
    }
    card.append(s);
  };

  // ------------------------------------------------------------ acessos (matriz de módulos)
  const acessos = (c, card) => {
    const grade = el('div', 'nia-acessos');
    (c.grupos || []).forEach((g) => {
      const bloco = el('div', 'nia-grupo');
      bloco.append(el('h4', '', g.nome));
      g.itens.forEach((it) => {
        const linha = el('div', 'nia-mod' + (it.tem ? ' tem' : '') + (it.mudanca === '+' ? ' mais' : it.mudanca === '-' ? ' menos' : ''));
        linha.title = it.chave;
        linha.append(icone(it.tem ? 'circle-check' : 'circle-x', 14), el('span', '', it.nome));
        if (it.mudanca) linha.append(el('em', '', it.mudanca === '+' ? 'ganha' : 'perde'));
        bloco.append(linha);
      });
      grade.append(bloco);
    });
    card.append(grade);
  };

  const proposta = (c, card) => {
    const lista = el('dl', 'nia-prop');
    (c.itens || []).forEach(([k, v]) => { lista.append(el('dt', '', k), el('dd', '', v)); });
    card.append(lista);
  };

  const links = (c, card) => {
    const box = el('div', 'nia-links');
    (c.links || []).forEach((l) => {
      if (!l || !l.url) return;
      const a = el('a', 'nia-link');
      a.href = l.url;
      a.append(icone('send', 14), el('span', '', l.rotulo));
      box.append(a);
    });
    card.append(box);
  };

  const perfil = (c, card) => {
    const lista = el('div', 'nia-perfil');
    (c.campos || []).forEach((f) => {
      const linha = el('div', 'nia-campo');
      linha.append(el('span', 'nc-rot', f.rotulo), el('code', 'nc-nome', f.nome));
      if (f.escala && typeof f.valor === 'number') {
        const barra = el('div', 'nia-escala');
        for (let i = 1; i <= 5; i += 1) barra.append(el('i', i <= f.valor ? 'on' : ''));
        barra.append(el('b', '', f.valor + '/5'));
        linha.append(barra);
      } else {
        linha.append(el('b', 'nc-val', f.valor));
      }
      lista.append(linha);
    });
    card.append(lista);
  };

  const botoesConfirmar = (card, responder) => {
    const box = el('div', 'nia-botoes');
    const sim = el('button', 'btn', 'Sim, aplicar'); sim.type = 'button';
    const nao = el('button', 'btn sec', 'Não, cancelar'); nao.type = 'button';
    sim.prepend(icone('check', 14)); nao.prepend(icone('x', 14));
    const travar = () => { sim.disabled = true; nao.disabled = true; };
    sim.addEventListener('click', () => { travar(); responder('Sim'); });
    nao.addEventListener('click', () => { travar(); responder('Não'); });
    box.append(sim, nao);
    card.append(box);
  };

  // ------------------------------------------------------------ Ilustrar (blocos ricos exclusivos da NucleAI)
  const copiarTexto = async (texto, btn) => {
    const antigo = btn.querySelector('span');
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(texto);
      } else {
        const tmp = document.createElement('textarea');
        tmp.value = texto;
        tmp.style.position = 'fixed';
        tmp.style.opacity = '0';
        document.body.append(tmp);
        tmp.select();
        document.execCommand('copy');
        tmp.remove();
      }
      if (antigo) {
        const orig = antigo.textContent;
        antigo.textContent = 'Copiado!';
        setTimeout(() => { antigo.textContent = orig; }, 1600);
      }
    } catch (_) {}
  };

  const valorOrdenacao = (v) => {
    if (typeof v === 'number') return { t: 0, v };
    const s = txtLimpo(v).trim();
    if (!s) return { t: 3, v: '' };
    const mData = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s);
    if (mData) return { t: 1, v: `${mData[3]}-${mData[2]}-${mData[1]}` };
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return { t: 1, v: s.slice(0, 10) };
    const limpo = s.replace(/^R\$\s*/i, '').replace(/%$/, '').trim();
    if (/^-?\d{1,3}(\.\d{3})*(,\d+)?$/.test(limpo) || /^-?\d+(,\d+)?$/.test(limpo)) {
      const n = Number(limpo.replace(/\./g, '').replace(',', '.'));
      if (Number.isFinite(n)) return { t: 0, v: n };
    }
    if (/^-?\d+(\.\d+)?$/.test(limpo)) {
      const n = Number(limpo);
      if (Number.isFinite(n)) return { t: 0, v: n };
    }
    return { t: 2, v: s };
  };

  const compararCelulas = (a, b) => {
    const ka = valorOrdenacao(a), kb = valorOrdenacao(b);
    if (ka.t === 3 && kb.t === 3) return 0;
    if (ka.t === 3) return 1;
    if (kb.t === 3) return -1;
    if (ka.t === 0 && kb.t === 0) return ka.v - kb.v;
    if (ka.t === 1 && kb.t === 1) return ka.v.localeCompare(kb.v);
    return String(ka.v).localeCompare(String(kb.v), 'pt-BR', { numeric: true, sensitivity: 'base' });
  };

  const ilustrarPlanilha = (c, card) => {
    const d = c.dados || {};
    const colunas = Array.isArray(d.colunas) ? d.colunas : [];
    const originais = Array.isArray(d.linhas) ? d.linhas : [];
    if (!colunas.length && !originais.length) { card.append(el('p', 'nia-vazio', 'Planilha sem linhas.')); return; }

    let linhasAtuais = originais.slice();
    let ordem = { col: -1, dir: 0 };
    let termoFiltro = '';

    const barra = el('div', 'nia-ilus-barra');
    barra.append(el('span', 'nia-ilus-cont', `${originais.length} linha(s) · ${colunas.length} col.`));
    const acoes = el('div', 'nia-ilus-acoes');
    const btnCopiar = el('button', 'nia-acao-btn');
    btnCopiar.type = 'button';
    btnCopiar.append(icone('clipboard-check', 14), el('span', '', 'Copiar'));
    btnCopiar.addEventListener('click', () => {
      const cab = colunas.map(txtLimpo).join('\t');
      const corpo = linhasAtuais.map((r) => r.map(txtLimpo).join('\t')).join('\n');
      copiarTexto(cab + (corpo ? '\n' + corpo : ''), btnCopiar);
    });
    acoes.append(btnCopiar);
    if (c.id) {
      const btnExcel = el('a', 'nia-acao-btn nia-excel-btn');
      btnExcel.href = '/mensagens/ilustracao/' + encodeURIComponent(c.id) + '/excel';
      btnExcel.setAttribute('download', '');
      btnExcel.append(icone('file-down', 14), el('span', '', 'Baixar Excel'));
      acoes.append(btnExcel);
    }
    barra.append(acoes);
    card.append(barra);

    const wrap = el('div', 'nia-tabela-wrap');
    const tabelaEl = el('table', 'nia-tabela nia-planilha-tb');
    const thead = el('thead');
    const trCab = el('tr');
    const tb = el('tbody');
    const thButtons = [];

    const desenharCorpo = () => {
      tb.replaceChildren();
      const q = termoFiltro.trim().toLocaleLowerCase('pt-BR');
      linhasAtuais.forEach((ln, i) => {
        const textoLinha = ln.map(txtLimpo).join(' ').toLocaleLowerCase('pt-BR');
        if (q && !textoLinha.includes(q)) return;
        const tr = el('tr');
        tr.style.animationDelay = Math.min(i, 24) * 14 + 'ms';
        colunas.forEach((_, j) => {
          const val = j < ln.length ? ln[j] : '';
          const td = el('td', typeof val === 'number' ? 'num' : '', val);
          tr.append(td);
        });
        tb.append(tr);
      });
    };

    colunas.forEach((nomeCol, idx) => {
      const th = el('th');
      th.setAttribute('aria-sort', 'none');
      const btn = el('button', 'nia-sort-btn');
      btn.type = 'button';
      btn.append(el('span', '', nomeCol), el('span', 'nia-sort-ind', ''));
      btn.addEventListener('click', () => {
        if (ordem.col === idx) {
          ordem.dir = ordem.dir === 1 ? -1 : ordem.dir === -1 ? 0 : 1;
        } else {
          ordem.col = idx;
          ordem.dir = 1;
        }
        if (ordem.dir === 0) {
          linhasAtuais = originais.slice();
        } else {
          linhasAtuais = originais.slice().sort((ra, rb) => compararCelulas(ra[idx], rb[idx]) * ordem.dir);
        }
        thButtons.forEach((item, j) => {
          const dir = (j === ordem.col) ? ordem.dir : 0;
          item.th.setAttribute('aria-sort', dir === 1 ? 'ascending' : dir === -1 ? 'descending' : 'none');
          item.ind.textContent = dir === 1 ? ' ▲' : dir === -1 ? ' ▼' : '';
          item.btn.classList.toggle('ativo', dir !== 0);
        });
        desenharCorpo();
      });
      th.append(btn);
      trCab.append(th);
      thButtons.push({ th, btn, ind: btn.querySelector('.nia-sort-ind') });
    });

    thead.append(trCab);
    tabelaEl.append(thead, tb);
    wrap.append(tabelaEl);

    if (originais.length > 6) {
      const filtro = el('input', 'nia-filtro');
      filtro.type = 'search';
      filtro.placeholder = 'Filtrar na planilha...';
      filtro.addEventListener('input', () => {
        termoFiltro = filtro.value;
        desenharCorpo();
      });
      card.append(filtro);
    }
    desenharCorpo();
    card.append(wrap);
  };

  const polar = (cx, cy, r, angDeg) => {
    const rad = ((angDeg - 90) * Math.PI) / 180;
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
  };

  const arcoSetor = (cx, cy, rOut, rIn, iniDeg, fimDeg) => {
    const grande = fimDeg - iniDeg > 180 ? 1 : 0;
    const [x1, y1] = polar(cx, cy, rOut, iniDeg);
    const [x2, y2] = polar(cx, cy, rOut, fimDeg);
    if (rIn <= 0) {
      return `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${rOut} ${rOut} 0 ${grande} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
    }
    const [x3, y3] = polar(cx, cy, rIn, fimDeg);
    const [x4, y4] = polar(cx, cy, rIn, iniDeg);
    return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${rOut} ${rOut} 0 ${grande} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} `
      + `L ${x3.toFixed(2)} ${y3.toFixed(2)} A ${rIn} ${rIn} 0 ${grande} 0 ${x4.toFixed(2)} ${y4.toFixed(2)} Z`;
  };

  const ilustrarGrafico = (c, card) => {
    const d = c.dados || {};
    const modo = d.modo || 'barras';
    const rotulos = Array.isArray(d.rotulos) ? d.rotulos : [];
    const series = Array.isArray(d.series) ? d.series : [];
    const unidade = d.unidade ? ' ' + txtLimpo(d.unidade) : '';
    if (!rotulos.length || !series.length) {
      card.append(el('p', 'nia-vazio', 'Sem dados para o gráfico.'));
      return;
    }

    const foco = el('div', 'nia-graf-foco', 'Passe o mouse ou foque um elemento para ver o valor.');
    const mostrar = (txt) => { foco.textContent = txtLimpo(txt); foco.classList.add('ativo'); };

    if (modo === 'pizza' || modo === 'rosca') {
      const vals = (series[0].valores || []).map((v) => Math.max(0, Number(v) || 0));
      const total = vals.reduce((a, b) => a + b, 0);
      if (total <= 0) {
        card.append(el('p', 'nia-vazio', 'Sem valores positivos para exibir.'));
        return;
      }
      const W = 240, H = 220, cx = 120, cy = 110, rOut = 88, rIn = modo === 'rosca' ? 48 : 0;
      const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'nia-graf nia-graf-pizza', role: 'img', 'aria-label': txtLimpo(c.titulo || 'Gráfico') });
      let ang = 0;
      const leg = el('div', 'nia-legenda nia-legenda-pizza');
      rotulos.forEach((rot, idx) => {
        const val = vals[idx] || 0;
        const pct = (val / total) * 100;
        const spanDeg = Math.min(359.95, (val / total) * 360);
        const corCls = 'gc-' + (idx % 6);
        const textoDet = `${txtLimpo(rot)}: ${num(val)}${unidade} (${pct.toFixed(1)}%)`;
        if (val > 0) {
          const path = svg('path', {
            d: arcoSetor(cx, cy, rOut, rIn, ang, ang + spanDeg),
            class: 'g-fatia ' + corCls,
            tabindex: '0',
            role: 'graphics-symbol',
            'aria-label': textoDet,
          });
          path.style.animationDelay = idx * 65 + 'ms';
          const tit = svg('title'); tit.textContent = textoDet; path.append(tit);
          const ativar = () => mostrar(textoDet);
          path.addEventListener('pointerenter', ativar);
          path.addEventListener('focus', ativar);
          path.addEventListener('click', ativar);
          s.append(path);
          ang += (val / total) * 360;
        }
        const itemLeg = el('button', 'lg lg-pizza');
        itemLeg.type = 'button';
        itemLeg.append(el('i', corCls), el('span', '', `${txtLimpo(rot)} (${num(val)}${unidade} · ${pct.toFixed(0)}%)`));
        itemLeg.addEventListener('pointerenter', () => mostrar(textoDet));
        itemLeg.addEventListener('focus', () => mostrar(textoDet));
        itemLeg.addEventListener('click', () => mostrar(textoDet));
        leg.append(itemLeg);
      });
      if (modo === 'rosca') {
        const totTxt = svg('text', { x: cx, y: cy - 2, class: 'g-centro-val', 'text-anchor': 'middle' });
        totTxt.textContent = num(total);
        const subTxt = svg('text', { x: cx, y: cy + 16, class: 'g-centro-rot', 'text-anchor': 'middle' });
        subTxt.textContent = 'Total' + unidade;
        s.append(totTxt, subTxt);
      }
      const gradeWrap = el('div', 'nia-pizza-wrap');
      gradeWrap.append(s, leg);
      card.append(foco, gradeWrap);
      return;
    }

    const todosValores = series.flatMap((se) => se.valores || []).map((v) => Number(v) || 0);
    const minVal = Math.min(0, ...todosValores);
    const maxVal = Math.max(1, ...todosValores);
    const faixa = Math.max(1e-9, maxVal - minVal);
    const W = 560, H = 235, ml = 46, mr = 16, mt = 18, mb = 44;
    const escalaY = (v) => mt + (H - mt - mb) * (1 - (v - minVal) / faixa);
    const baseY = escalaY(0);
    const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'nia-graf', role: 'img', 'aria-label': txtLimpo(c.titulo || 'Gráfico') });

    for (let i = 0; i <= 4; i += 1) {
      const v = minVal + (faixa * i) / 4;
      const y = escalaY(v);
      s.append(svg('line', { x1: ml, x2: W - mr, y1: y, y2: y, class: 'g-grade' }));
      const t = svg('text', { x: ml - 6, y: y + 4, class: 'g-eixo', 'text-anchor': 'end' });
      t.textContent = num(Math.round(v * 10) / 10);
      s.append(t);
    }

    if (modo === 'linhas') {
      const passo = rotulos.length > 1 ? (W - ml - mr - 24) / (rotulos.length - 1) : 0;
      const X = (i) => (rotulos.length === 1 ? (W + ml - mr) / 2 : ml + 12 + passo * i);
      series.forEach((se, sIdx) => {
        const clsCor = 'gc-' + (sIdx % 6);
        const ptsCoords = rotulos.map((_, i) => [X(i), escalaY(Number((se.valores || [])[i]) || 0)]);
        if (series.length === 1 && ptsCoords.length > 1) {
          const areaPts = ptsCoords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
            .concat([`${ptsCoords[ptsCoords.length - 1][0].toFixed(1)},${baseY.toFixed(1)}`, `${ptsCoords[0][0].toFixed(1)},${baseY.toFixed(1)}`])
            .join(' ');
          s.append(svg('polygon', { points: areaPts, class: 'g-faixa' }));
        }
        const lineStr = ptsCoords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
        const poly = svg('polyline', { points: lineStr, class: 'g-linha g-linha-s ' + clsCor });
        poly.style.animationDelay = sIdx * 120 + 'ms';
        s.append(poly);
        rotulos.forEach((rot, i) => {
          const val = Number((se.valores || [])[i]) || 0;
          const [cx, cy] = ptsCoords[i];
          const labelTxt = `${txtLimpo(rot)} · ${txtLimpo(se.nome)}: ${num(val)}${unidade}`;
          const pt = svg('circle', {
            cx, cy, r: 4.5, class: 'g-ponto ' + clsCor, tabindex: '0', role: 'graphics-symbol', 'aria-label': labelTxt,
          });
          pt.style.animationDelay = 250 + i * 35 + 'ms';
          const tit = svg('title'); tit.textContent = labelTxt; pt.append(tit);
          const ativar = () => mostrar(labelTxt);
          pt.addEventListener('pointerenter', ativar);
          pt.addEventListener('focus', ativar);
          pt.addEventListener('click', ativar);
          s.append(pt);
        });
      });
      const pulo = Math.max(1, Math.ceil(rotulos.length / 10));
      rotulos.forEach((r, i) => {
        if (i % pulo !== 0 && i !== rotulos.length - 1) return;
        const txtEixo = svg('text', { x: X(i), y: H - mb + 16, class: 'g-eixo', 'text-anchor': 'middle' });
        const rt = txtLimpo(r);
        txtEixo.textContent = rt.length > 12 ? rt.slice(0, 11) + '…' : rt;
        s.append(txtEixo);
      });
    } else {
      const nSer = series.length;
      const passo = (W - ml - mr) / rotulos.length;
      const grupoLarg = Math.min(54, passo * 0.72);
      const barraLarg = Math.max(6, (grupoLarg - (nSer - 1) * 3) / nSer);
      rotulos.forEach((rot, i) => {
        const gX = ml + passo * i + (passo - (barraLarg * nSer + (nSer - 1) * 3)) / 2;
        series.forEach((se, sIdx) => {
          const val = Number((se.valores || [])[i]) || 0;
          const yVal = escalaY(val);
          const yRect = val >= 0 ? yVal : baseY;
          const hRect = Math.max(2, Math.abs(baseY - yVal));
          const bx = gX + sIdx * (barraLarg + 3);
          const labelTxt = nSer > 1
            ? `${txtLimpo(rot)} · ${txtLimpo(se.nome)}: ${num(val)}${unidade}`
            : `${txtLimpo(rot)}: ${num(val)}${unidade}`;
          const rect = svg('rect', {
            x: bx, y: yRect, width: barraLarg, height: hRect, rx: 4,
            class: 'g-barra ' + (nSer > 1 ? 'gc-' + (sIdx % 6) : 'gc-0'),
            tabindex: '0', role: 'graphics-symbol', 'aria-label': labelTxt,
          });
          rect.style.animationDelay = (i * nSer + sIdx) * 35 + 'ms';
          const tit = svg('title'); tit.textContent = labelTxt; rect.append(tit);
          const ativar = () => mostrar(labelTxt);
          rect.addEventListener('pointerenter', ativar);
          rect.addEventListener('focus', ativar);
          rect.addEventListener('click', ativar);
          s.append(rect);
          if (nSer === 1 && rotulos.length <= 12) {
            const vTxt = svg('text', { x: bx + barraLarg / 2, y: yRect - 5, class: 'g-valor', 'text-anchor': 'middle' });
            vTxt.textContent = num(val);
            s.append(vTxt);
          }
        });
        const pulo = Math.max(1, Math.ceil(rotulos.length / 10));
        if (i % pulo === 0) {
          const tx = svg('text', { x: ml + passo * i + passo / 2, y: H - mb + 16, class: 'g-eixo', 'text-anchor': 'middle' });
          const rt = txtLimpo(rot);
          tx.textContent = rt.length > 12 ? rt.slice(0, 11) + '…' : rt;
          s.append(tx);
        }
      });
    }

    card.append(foco, s);
    if (series.length > 1) {
      const leg = el('div', 'nia-legenda');
      series.forEach((se, sIdx) => {
        const it = el('span', 'lg');
        it.append(el('i', 'gc-' + (sIdx % 6)), el('span', '', se.nome));
        leg.append(it);
      });
      card.append(leg);
    }
  };

  const ilustrarCartaoInfo = (c, card) => {
    const d = c.dados || {};
    if (d.destaque) card.append(el('span', 'nia-info-selo', d.destaque));
    const itens = Array.isArray(d.itens) ? d.itens : [];
    if (!itens.length) { card.append(el('p', 'nia-vazio', 'Sem campos informados.')); return; }
    const dl = el('dl', 'nia-info-grid');
    itens.forEach((it) => {
      if (it.rotulo) dl.append(el('dt', '', it.rotulo));
      const dd = el('dd', it.destaque ? 'destaque' : '', it.valor);
      if (!it.rotulo) dd.classList.add('inteiro');
      dl.append(dd);
    });
    card.append(dl);
  };

  const ilustrarCartaoDecisao = (c, card, responder) => {
    const d = c.dados || {};
    if (d.risco === 'alto') card.append(el('span', 'nia-decisao-risco alto', 'Atenção: ação crítica'));
    card.append(el('p', 'nia-decisao-perg', d.pergunta || c.titulo || 'Confirma?'));
    if (Array.isArray(d.detalhes) && d.detalhes.length) {
      const dl = el('dl', 'nia-info-grid compacto');
      d.detalhes.forEach((it) => {
        if (it.rotulo) dl.append(el('dt', '', it.rotulo));
        dl.append(el('dd', '', it.valor));
      });
      card.append(dl);
    }
    const rodapeEstado = el('div', 'nia-decisao-estado');
    const mostrarTravado = (resp) => {
      rodapeEstado.replaceChildren();
      const pos = resp === 'SIM';
      const box = el('div', 'nia-decisao-travado ' + (pos ? 'sim' : 'nao'));
      box.append(icone(pos ? 'circle-check' : 'circle-x', 15));
      const rot = pos ? (d.rotulo_sim || 'Sim') : (d.rotulo_nao || 'Não');
      box.append(el('span', '', 'Escolha registrada: ' + txtLimpo(rot)));
      rodapeEstado.append(box);
      card.dataset.decisaoTravada = resp;
    };
    if (c.decisao_resp === 'SIM' || c.decisao_resp === 'NAO') {
      mostrarTravado(c.decisao_resp);
    } else {
      const box = el('div', 'nia-botoes');
      const sim = el('button', 'btn', d.rotulo_sim || 'Sim'); sim.type = 'button';
      const nao = el('button', 'btn sec', d.rotulo_nao || 'Não'); nao.type = 'button';
      sim.prepend(icone('check', 14)); nao.prepend(icone('x', 14));
      sim.addEventListener('click', () => {
        mostrarTravado('SIM');
        responder('Sim');
      });
      nao.addEventListener('click', () => {
        mostrarTravado('NAO');
        responder('Não');
      });
      box.append(sim, nao);
      rodapeEstado.append(box);
    }
    card.append(rodapeEstado);
  };

  const ilustrarCartaoPermissao = (c, card) => {
    const d = c.dados || {};
    if (d.alvo || d.acao) {
      const meta = el('dl', 'nia-info-grid compacto');
      if (d.alvo) { meta.append(el('dt', '', 'Envolvido'), el('dd', '', d.alvo)); }
      if (d.acao) { meta.append(el('dt', '', 'Ação'), el('dd', '', d.acao)); }
      card.append(meta);
    }
    const auts = Array.isArray(d.autorizadores) ? d.autorizadores : [];
    if (auts.length) {
      const autBox = el('div', 'nia-perm-aut');
      autBox.append(el('small', 'nia-perm-tit', 'Quem precisa autorizar'));
      const chips = el('div', 'nia-perm-chips');
      auts.forEach((a) => {
        const chip = el('span', 'nia-perm-chip');
        chip.append(icone('shield-check', 13));
        const rot = a.cargo ? `${txtLimpo(a.nome)} (${txtLimpo(a.cargo)})` : txtLimpo(a.nome);
        chip.append(el('span', '', rot));
        chips.append(chip);
      });
      autBox.append(chips);
      card.append(autBox);
    }
    const grupos = Array.isArray(d.grupos) ? d.grupos : [];
    if (grupos.length) {
      const grade = el('div', 'nia-acessos');
      grupos.forEach((g) => {
        const bloco = el('div', 'nia-grupo');
        bloco.append(el('h4', '', g.titulo || 'Alterações'));
        (g.itens || []).forEach((it) => {
          const tipoCls = it.tipo === 'mais' ? ' mais' : it.tipo === 'menos' ? ' menos' : ' tem';
          const linha = el('div', 'nia-mod' + tipoCls);
          const icNome = it.tipo === 'menos' ? 'circle-x' : it.tipo === 'mais' ? 'circle-check' : 'settings-2';
          linha.append(icone(icNome, 14));
          const textoItem = it.detalhe ? `${txtLimpo(it.nome)} — ${txtLimpo(it.detalhe)}` : txtLimpo(it.nome);
          linha.append(el('span', '', textoItem));
          const selo = it.tipo === 'mais' ? 'ganha' : it.tipo === 'menos' ? 'perde' : 'altera';
          linha.append(el('em', '', selo));
          bloco.append(linha);
        });
        grade.append(bloco);
      });
      card.append(grade);
    }
  };

  const ilustrarTexto = (c, card) => {
    const d = c.dados || {};
    card.append(el('div', 'nia-ilus-texto', d.texto || ''));
  };

  const marcarSubstituida = (alvo) => {
    if (!alvo || alvo.classList.contains('nia-substituida')) return;
    alvo.classList.add('nia-substituida');
    const topoEl = alvo.querySelector('.nia-topo');
    if (topoEl && !topoEl.querySelector('.nia-sub-badge')) {
      topoEl.append(el('span', 'nia-sub-badge', 'Substituída'));
    }
  };

  const ilustracao = (c, card, responder) => {
    card.classList.add('nia-ilustrar', 'nia-ilus-' + (c.subtipo || 'texto'));
    if (c.id) card.dataset.ilustracaoId = String(c.id);
    if (c.substitui) {
      document.querySelectorAll(`[data-ilustracao-id="${c.substitui}"]`).forEach(marcarSubstituida);
    }
    if (c.substituido_por) marcarSubstituida(card);
    const sub = c.subtipo || 'texto';
    if (sub === 'planilha') ilustrarPlanilha(c, card);
    else if (sub === 'grafico') ilustrarGrafico(c, card);
    else if (sub === 'cartao_info') ilustrarCartaoInfo(c, card);
    else if (sub === 'cartao_decisao') ilustrarCartaoDecisao(c, card, responder);
    else if (sub === 'cartao_permissao') ilustrarCartaoPermissao(c, card);
    else ilustrarTexto(c, card);
  };

  const render = (c, opcoes) => {
    const op = opcoes || {};
    const responder = op.responder || responderPadrao;
    const card = el('div', 'nia-cartao nia-' + c.tipo.slice(3).toLowerCase());
    card.append(topo(c));
    if (c.tipo === 'IA_TABELA') tabela(c, card);
    else if (c.tipo === 'IA_GRAFICO') grafico(c, card);
    else if (c.tipo === 'IA_ACESSOS') acessos(c, card);
    else if (c.tipo === 'IA_PROPOSTA') proposta(c, card);
    else if (c.tipo === 'IA_LINKS') links(c, card);
    else if (c.tipo === 'IA_PERFIL') perfil(c, card);
    else if (c.tipo === 'IA_ILUSTRACAO') ilustracao(c, card, op.confirmavel === false ? () => {} : responder);
    if (c.tipo === 'IA_GRAFICO' && c.rodape) { card.append(el('p', 'nia-rodape', c.rodape)); c = Object.assign({}, c, { rodape: '' }); }
    pe(c, card);
    if ((c.tipo === 'IA_PROPOSTA' || c.confirmar) && op.confirmavel !== false) botoesConfirmar(card, responder);
    return card;
  };

  window.NucleaiCartoes = { suporta: (c) => !!(c && TIPOS.has(c.tipo)), render };
})();
