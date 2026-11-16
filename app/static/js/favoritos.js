'use strict';
/* Painel de favoritos: mostra os módulos escolhidos como widgets (grade ou lista). No modo "Personalizar" dá para marcar
   módulos, arrastar (ou usar ◀ ▶) para mudar a posição, alargar e trocar a cor. Cada mudança é salva no perfil do usuário. */
(() => {
  const raiz = document.querySelector('[data-fav]');
  if (!raiz) return;
  const csrf = (document.querySelector('meta[name=csrf]') || {}).content || '';
  const dados = JSON.parse(document.getElementById('fav-dados').textContent);
  const mapa = Object.fromEntries(dados.disponiveis.map((m) => [m.ep, m]));
  const estado = dados.estado;           // {modo, itens: [{ep, tam, cor}]}
  let editando = false;
  let origem = null;                     // índice do widget que está sendo arrastado
  let aberto = null;                     // atalho com a grade de símbolos aberta

  const q = (s, c = document) => c.querySelector(s);
  const el = (tag, classe, texto) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined) e.textContent = texto;
    return e;
  };
  // desenho do sprite (Lucide): traço fino, acompanha a cor do texto
  const NS = 'http://www.w3.org/2000/svg';
  const icone = (nome, tam) => {
    const s = document.createElementNS(NS, 'svg');
    s.setAttribute('class', 'ic'); s.setAttribute('width', tam); s.setAttribute('height', tam); s.setAttribute('aria-hidden', 'true');
    const u = document.createElementNS(NS, 'use');
    u.setAttribute('href', `${document.body.dataset.icones}#i-${nome}`);
    s.append(u);
    return s;
  };
  const botao = (texto, classe, titulo, aoClicar, desenho) => {
    const b = el('button', classe, desenho ? undefined : texto);
    if (desenho) b.append(icone(desenho, 20));
    b.type = 'button';
    b.title = titulo;
    b.setAttribute('aria-label', titulo);
    b.addEventListener('click', (ev) => { ev.preventDefault(); ev.stopPropagation(); aoClicar(); });
    return b;
  };

  let pendente = null;
  const salvar = () => {
    clearTimeout(pendente);
    pendente = setTimeout(() => {
      fetch('/favoritos/salvar', {method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': csrf},
        body: new URLSearchParams({dados: JSON.stringify(estado)})}).catch(() => { /* sem conexão: tenta na próxima mudança */ });
    }, 250);
  };

  const mover = (de, para) => {
    if (para < 0 || para >= estado.itens.length || de === para) return;
    const [x] = estado.itens.splice(de, 1);
    estado.itens.splice(para, 0, x);
    salvar();
    desenhar();
  };

  const CORES = dados.cores;
  const desenhar = () => {
    const area = q('#fav-area');
    area.replaceChildren();
    area.className = 'fav-area ' + estado.modo + (editando ? ' fav-editando' : '');
    raiz.classList.toggle('editando', editando);
    document.querySelectorAll('[data-modo]').forEach((b) => b.classList.toggle('ativo', b.dataset.modo === estado.modo));
    q('#fav-vazio').hidden = estado.itens.length > 0;
    estado.itens.forEach((it, i) => {
      const m = mapa[it.ep];
      if (!m) return;
      const card = el(editando ? 'div' : 'a', `fav-card tam-${it.tam}` + (it.cor ? ' cor-' + it.cor : ''));
      if (!editando) card.href = m.url;
      const bolha = el('span', 'fav-ico');
      bolha.setAttribute('aria-hidden', 'true');
      bolha.append(icone(it.ico || m.icone || 'layout-grid', 26));
      const txt = el('div', 'fav-txt');
      txt.append(el('strong', '', m.rotulo), el('small', '', m.grupo));
      card.append(bolha, txt);
      if (editando) {
        card.draggable = true;
        card.addEventListener('dragstart', (ev) => { origem = i; card.classList.add('arrastando'); ev.dataTransfer.effectAllowed = 'move'; try { ev.dataTransfer.setData('text/plain', String(i)); } catch (e) { /* ignorado */ } });
        card.addEventListener('dragend', () => { origem = null; card.classList.remove('arrastando'); });
        card.addEventListener('dragover', (ev) => { if (origem !== null) { ev.preventDefault(); card.classList.add('alvo'); } });
        card.addEventListener('dragleave', () => card.classList.remove('alvo'));
        card.addEventListener('drop', (ev) => { ev.preventDefault(); card.classList.remove('alvo'); if (origem !== null) mover(origem, i); });
        const ctl = el('div', 'fav-ctl');
        ctl.append(
          botao('◀', '', 'Mover para antes', () => mover(i, i - 1)),
          botao('▶', '', 'Mover para depois', () => mover(i, i + 1)),
          botao('⇔', '', it.tam === 2 ? 'Deixar estreito' : 'Alargar', () => { it.tam = it.tam === 2 ? 1 : 2; salvar(); desenhar(); }),
          botao('●', 'cor', 'Trocar a cor', () => { it.cor = CORES[(CORES.indexOf(it.cor) + 1) % CORES.length]; salvar(); desenhar(); }),
          botao('', '', 'Escolher o desenho deste atalho', () => { aberto = aberto === it.ep ? null : it.ep; desenhar(); }, 'palette'),
          botao('✕', 'rem', 'Tirar dos favoritos', () => { estado.itens.splice(i, 1); salvar(); desenhar(); montarLista(); }));
        card.append(ctl);
        if (aberto === it.ep) {   // grade de símbolos para escolher
          const grade = el('div', 'fav-simbolos');
          [m.icone, ...dados.icones].filter((x, k, a) => a.indexOf(x) === k).forEach((sim) => {
            grade.append(botao('', sim === (it.ico || m.icone) ? 'atual' : '', 'Usar o desenho ' + sim, () => { it.ico = sim === m.icone ? '' : sim; aberto = null; salvar(); desenhar(); }, sim));
          });
          card.append(grade);
        }
      }
      area.append(card);
    });
  };

  // lista de módulos para marcar (modo Personalizar)
  const semAcento = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const montarLista = () => {
    const lista = q('#fav-lista');
    const termo = semAcento(q('#fav-busca').value.trim());
    lista.replaceChildren();
    const grupos = new Map();
    dados.disponiveis.forEach((m) => {
      if (termo && !semAcento(m.rotulo + ' ' + m.grupo).includes(termo)) return;
      if (!grupos.has(m.grupo)) grupos.set(m.grupo, []);
      grupos.get(m.grupo).push(m);
    });
    grupos.forEach((itens, grupo) => {
      lista.append(el('h4', '', grupo));
      itens.forEach((m) => {
        const l = el('label');
        const c = document.createElement('input');
        c.type = 'checkbox';
        c.checked = estado.itens.some((x) => x.ep === m.ep);
        c.addEventListener('change', () => {
          if (c.checked) estado.itens.push({ep: m.ep, tam: 1, cor: ''});
          else estado.itens = estado.itens.filter((x) => x.ep !== m.ep);
          salvar();
          desenhar();
        });
        l.append(c, ' ' + m.rotulo);
        lista.append(l);
      });
    });
  };

  q('#fav-editar').addEventListener('click', () => {
    editando = !editando;
    const b = q('#fav-editar');
    b.textContent = editando ? 'Concluir' : 'Personalizar';
    b.setAttribute('aria-pressed', String(editando));
    q('#fav-editor').hidden = !editando;
    if (editando) montarLista();
    desenhar();
  });
  q('#fav-busca').addEventListener('input', montarLista);
  document.querySelectorAll('[data-modo]').forEach((b) => b.addEventListener('click', () => { estado.modo = b.dataset.modo; salvar(); desenhar(); }));

  desenhar();
})();
