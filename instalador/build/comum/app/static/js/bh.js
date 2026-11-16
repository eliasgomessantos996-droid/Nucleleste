'use strict';
/* Banco de Horas: escala, filtros de tabela, jornadas sugeridas, documentos e mensagens ao vivo. */

(() => {
  const normalizar = (v) => v.normalize('NFD').replace(/[̀-ͯ]/g, '').toLocaleLowerCase('pt-BR');

  // Escala: o formulário mostra horário só para "Trabalho"; clicar num dia preenche o formulário.
  const tipo = document.querySelector('[data-roster-kind]');
  if (tipo) {
    const atualizar = () => document.querySelectorAll('.roster-work').forEach((c) => { c.hidden = tipo.value !== 'trabalho'; });
    tipo.addEventListener('change', atualizar);
    atualizar();
    document.querySelectorAll('[data-roster-date]').forEach((cel) => {
      cel.addEventListener('click', () => {
        const f = tipo.form;
        const valores = {employee_id: cel.dataset.employee, start: cel.dataset.rosterDate, end: cel.dataset.rosterDate,
          kind: cel.dataset.kind, start_time: cel.dataset.start || '08:00', end_time: cel.dataset.end || '17:00',
          break_duration: cel.dataset.break, note: cel.dataset.note};
        Object.entries(valores).forEach(([nome, valor]) => { f.elements.namedItem(nome).value = valor; });
        f.elements.namedItem('reset').checked = false;
        atualizar();
        f.scrollIntoView({behavior: 'smooth', block: 'center'});
        document.getElementById('note').focus({preventScroll: true});
      });
    });
  }

  // Busca dentro de uma tabela.
  document.querySelectorAll('[data-table-search]').forEach((campo) => {
    const tabela = document.getElementById(campo.dataset.tableSearch);
    if (!tabela) return;
    campo.addEventListener('input', () => {
      const q = normalizar(campo.value.trim());
      tabela.querySelectorAll('tbody tr').forEach((l) => { l.hidden = !normalizar(l.textContent).includes(q); });
    });
  });

  // Jornadas sugeridas.
  document.querySelectorAll('[data-schedule-preset]').forEach((sel) => {
    const modelos = {
      '44': ['08:00', '08:00', '08:00', '08:00', '08:00', '04:00', '00:00'],
      '20': ['04:00', '04:00', '04:00', '04:00', '04:00', '00:00', '00:00'],
    };
    sel.addEventListener('change', () => {
      const v = modelos[sel.value];
      if (!v) return;
      v.forEach((valor, i) => { const c = sel.form.querySelector(`[name="weekday_${i}"]`); if (c) c.value = valor; });
    });
  });

  // Departamento Pessoal: o mês só vale para a folha de ponto assinada.
  document.querySelectorAll('[data-doc-category]').forEach((sel) => {
    const alternar = () => document.querySelectorAll('.doc-month').forEach((c) => { c.hidden = sel.value !== 'folha_ponto'; });
    sel.addEventListener('change', alternar);
    alternar();
  });

  // Imagens abrem a impressão sozinhas.
  if (document.querySelector('[data-autoprint]')) window.addEventListener('load', () => window.print());
  document.querySelectorAll('[data-print]').forEach((b) => b.addEventListener('click', () => window.print()));
})();

// Mensagens ao vivo: consultas curtas e frequentes (o servidor não mantém conexões abertas).
(() => {
  const url = document.body.dataset.msgPoll;
  if (!url) return;
  const tituloBase = document.title;
  const conversa = document.getElementById('msg-thread');
  const lista = document.querySelector('[data-conv-list]');
  const form = document.getElementById('msg-form');
  const estado = document.querySelector('[data-chat-status]');
  const filtro = document.querySelector('[data-chat-filter]');
  const normalizar = (v) => v.normalize('NFD').replace(/[̀-ͯ]/g, '').toLocaleLowerCase('pt-BR');
  const intervalo = conversa ? 3000 : 15000;
  const exibidas = new Set();
  let depois = conversa ? Number(conversa.dataset.after) : 0;
  let falhas = 0, timer = null, parado = false;

  const definirEstado = (texto, ok) => {
    if (!estado) return;
    estado.textContent = texto;
    estado.classList.toggle('is-off', !ok);
  };
  const definirNaoLidas = (n) => {
    document.querySelectorAll('[data-msg-badge]').forEach((b) => { b.textContent = n; b.hidden = !n; });
    document.title = n ? `(${n}) ${tituloBase}` : tituloBase;
  };
  const balao = (m) => {
    const caixa = document.createElement('div');
    caixa.className = m.mine ? 'msg-bh msg-mine' : 'msg-bh';
    caixa.dataset.id = m.id;
    const meta = document.createElement('div');
    meta.className = 'msg-meta';
    const quem = document.createElement('strong');
    quem.textContent = m.label;
    const hora = document.createElement('time');
    hora.textContent = m.at;
    meta.append(quem, document.createTextNode(m.from_employee ? ' ' : ` · ${m.name} `), hora);
    const corpo = document.createElement('div');
    corpo.className = 'msg-body';
    corpo.textContent = m.body;
    caixa.append(meta, corpo);
    return caixa;
  };
  const acrescentar = (m) => {
    if (!conversa || exibidas.has(m.id)) return;
    exibidas.add(m.id);
    depois = Math.max(depois, m.id);
    const perto = conversa.scrollHeight - conversa.scrollTop - conversa.clientHeight < 120;
    conversa.querySelectorAll('.chat-vazio').forEach((n) => n.remove());
    conversa.append(balao(m));
    if (perto || m.mine) conversa.scrollTop = conversa.scrollHeight;
  };
  const aplicarFiltro = () => {
    if (!lista || !filtro) return;
    const q = normalizar(filtro.value.trim());
    lista.querySelectorAll('li[data-name]').forEach((i) => { i.hidden = !normalizar(i.dataset.name).includes(q); });
  };
  const desenharLista = (conversas) => {
    if (!lista) return;
    const escolhido = conversa ? conversa.dataset.employee : '';
    lista.replaceChildren(...conversas.map((c) => {
      const li = document.createElement('li');
      li.dataset.name = c.name;
      const a = document.createElement('a');
      a.className = String(c.id) === escolhido ? 'chat-conv is-active' : 'chat-conv';
      a.href = `?employee=${c.id}`;
      const principal = document.createElement('span');
      principal.className = 'chat-conv-main';
      const nome = document.createElement('strong');
      nome.textContent = c.name;
      const previa = document.createElement('small');
      previa.textContent = c.preview + (c.has_account ? '' : ' · sem acesso ativo');
      principal.append(nome, previa);
      const selo = document.createElement('span');
      selo.className = 'selo-menu';
      selo.textContent = c.unread;
      selo.hidden = !c.unread;
      a.append(principal, selo);
      li.append(a);
      return li;
    }));
    aplicarFiltro();
  };
  const agendar = () => {
    clearTimeout(timer);
    if (parado) return;
    timer = setTimeout(consultar, falhas ? Math.min(30000, intervalo * 2 ** falhas) : intervalo);
  };
  const parar = () => { parado = true; definirEstado('● desconectado: recarregue a página', false); };

  async function consultar() {
    if (parado) return;
    if (document.hidden) { agendar(); return; }
    const p = new URLSearchParams();
    if (conversa) { p.set('employee', conversa.dataset.employee); p.set('after', depois); p.set('visible', '1'); }
    if (lista) p.set('list', '1');
    try {
      const r = await fetch(`${url}?${p}`, {headers: {Accept: 'application/json', 'X-Passivo': '1'}, credentials: 'same-origin'});
      if (r.redirected || r.status === 401 || r.status === 403) { parar(); return; }
      if (!r.ok) throw new Error(String(r.status));
      const dados = await r.json();
      falhas = 0;
      definirEstado('● ao vivo', true);
      (dados.messages || []).forEach(acrescentar);
      if (dados.conversations) desenharLista(dados.conversations);
      definirNaoLidas(dados.unread || 0);
    } catch (e) {
      falhas += 1;
      definirEstado('● reconectando…', false);
    }
    agendar();
  }

  if (conversa) {
    conversa.querySelectorAll('[data-id]').forEach((n) => exibidas.add(Number(n.dataset.id)));
    conversa.scrollTop = conversa.scrollHeight;
  }
  if (filtro) filtro.addEventListener('input', aplicarFiltro);

  if (form) {
    const texto = form.elements.namedItem('body');
    const botao = form.querySelector('button[type="submit"]');
    const erro = form.querySelector('[data-chat-error]');
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      if (!texto.value.trim()) return;
      botao.disabled = true;
      erro.hidden = true;
      try {
        const r = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {Accept: 'application/json'}, credentials: 'same-origin'});
        if (r.redirected) { parar(); throw new Error('Sua sessão terminou. Recarregue a página.'); }
        const dados = await r.json();
        if (!r.ok) throw new Error(dados.error || 'Não foi possível enviar.');
        texto.value = '';
        acrescentar(dados.message);
      } catch (problema) {
        erro.textContent = problema instanceof SyntaxError ? 'Não foi possível enviar. Recarregue a página.' : problema.message;
        erro.hidden = false;
      } finally {
        botao.disabled = false;
        texto.focus();
      }
    });
    texto.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); form.requestSubmit(); }
    });
  }

  document.addEventListener('visibilitychange', () => { if (!document.hidden && !parado) { clearTimeout(timer); consultar(); } });
  agendar();
})();
