'use strict';
/* Agenda de exames: calendário à esquerda e, à direita, a agenda do dia (uma grade por exame, como uma planilha).
   Cada célula é salva ao sair dela. A tela confere o servidor a cada poucos segundos, então o que outra pessoa
   marcar aparece sem recarregar; se duas pessoas mexerem na mesma célula, a segunda recebe um aviso em vez de
   sobrescrever. */
(() => {
  const raiz = document.querySelector('[data-agenda]');
  if (!raiz) return;
  const csrf = (document.querySelector('meta[name=csrf]') || {}).content || '';
  const hoje = raiz.dataset.hoje;
  const somenteLeitura = raiz.dataset.somenteLeitura === '1';   // estagiário: vê e imprime, não altera nada
  const podeExcluir = raiz.dataset.podeExcluir === '1';   // excluir agenda: só administrador e gerência
  const statusTravado = (l) => l.status === 'RETORNO' && !!l.remarcado_para && !podeExcluir;   // remarcado para outra data: só a nova marcação muda de status, exceto para administrador e gerência
  const MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
  const ROTULOS = {AGENDADO: 'Agendado', VEIO: 'Veio', FALTOU: 'Faltou', RETORNO: 'Retorno', RESGATADO: 'Reagendado', DESISTIU: 'Desistiu'};
  // mensagem de resgate: a importância do exame e um convite caloroso para realizá-lo
  // textos enviados pelo WhatsApp: editados pela gerência (Administração > Mensagens do WhatsApp)
  const MODELOS_WHATS = (() => { try { return JSON.parse(document.getElementById('ag-mensagens').textContent); } catch (e) { return {}; } })();
  const preencherModelo = (modelo, p) => {
    const primeiro = ((p.nome || '').trim().split(' ')[0] || '').toLowerCase().replace(/^\p{L}/u, (c) => c.toUpperCase());
    const v = {saudacao: primeiro ? 'Olá, ' + primeiro : 'Olá', nome: primeiro, exame: p.exame || '', agenda: p.exame || '', data: p.data || '', hora: p.hora || ''};
    return (modelo || '').replace(/\{(\w+)\}/g, (marca, chave) => (chave in v ? v[chave] : marca));
  };
  // quem envia: o primeiro nome do usuário logado, antes do texto ("Enviado por Adriano: ...")
  const USUARIO_ENVIO = (() => { try { return JSON.parse(document.getElementById('ag-usuario').textContent); } catch (e) { return ''; } })();
  const mensagemResgate = (nome, exame, data, hora) => preencherModelo(MODELOS_WHATS.falta, {nome, exame, data, hora});
  const COLUNAS = {hora: 'Horário', paciente: 'Paciente', idade: 'Idade', convenio: 'Convênio', contato: 'Contato', senha: 'Senha de autorização', observacao: 'Observação/Senha'};
  const LIMITES = {hora: 5, paciente: 120, idade: 3, convenio: 60, contato: 80, senha: 40, observacao: 300};

  const estado = {dia: JSON.parse(document.getElementById('ag-inicial').textContent), data: '', mes: '', filtro: 'todos',
                  marcas: {dias: [], bloqueados: {}}, assinatura: ''};
  let ordenando = false;   // modo de ordenar as agendas (setas ↑ ↓ nos exames)
  estado.data = estado.dia.data;
  estado.mes = estado.data.slice(0, 7);
  estado.assinatura = JSON.stringify(estado.dia);

  // ------------------------------------------------------------ utilidades
  const q = (sel, ctx = document) => ctx.querySelector(sel);
  const el = (tag, classe, texto) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined) e.textContent = texto;
    return e;
  };
  const NS_SVG = 'http://www.w3.org/2000/svg';
  const icone = (nome, tam) => {   // ícone do sprite /static/img/icones.svg
    const s = document.createElementNS(NS_SVG, 'svg');
    s.setAttribute('class', 'ic'); s.setAttribute('width', tam || 16); s.setAttribute('height', tam || 16);
    s.setAttribute('aria-hidden', 'true'); s.setAttribute('focusable', 'false');
    const u = document.createElementNS(NS_SVG, 'use');
    u.setAttribute('href', '/static/img/icones.svg#i-' + nome);
    s.appendChild(u);
    return s;
  };
  const botao = (texto, classe, aoClicar, desabilitado, iconeNome) => {
    const b = el('button', classe, texto);
    if (iconeNome) { b.prepend(icone(iconeNome)); b.classList.add('com-icone'); }
    b.type = 'button';
    if (desabilitado) b.disabled = true;
    b.addEventListener('click', aoClicar);
    return b;
  };
  const dataBR = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  const somarDias = (iso, n) => {
    const d = new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)) + n);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const dataExtenso = (iso) => {
    const d = new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)));
    const t = d.toLocaleDateString('pt-BR', {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'});
    return t.charAt(0).toUpperCase() + t.slice(1);
  };

  const enviar = async (url, dados) => {
    const r = await fetch(url, {method: 'POST', body: new URLSearchParams(dados || {}), credentials: 'same-origin',
      headers: {Accept: 'application/json', 'X-CSRF-Token': csrf}});
    if (r.redirected) { location.href = '/login'; throw new Error('sessão encerrada'); }
    let j = {};
    try { j = await r.json(); } catch (e) { /* resposta sem JSON */ }
    return Object.assign({}, j, {http: r.status, ok: r.ok});
  };
  const buscar = async (url, passivo) => {
    const r = await fetch(url, {credentials: 'same-origin', headers: Object.assign({Accept: 'application/json'}, passivo ? {'X-Passivo': '1'} : {})});
    if (r.redirected || r.status === 401) { location.href = '/login'; throw new Error('sessão encerrada'); }
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  };

  let temporizadorAviso = null;
  const aviso = (texto, tipo) => {
    const caixa = q('#ag-aviso');
    caixa.textContent = texto;
    caixa.className = 'ag-aviso ' + (tipo || 'ok');
    caixa.hidden = false;
    clearTimeout(temporizadorAviso);
    temporizadorAviso = setTimeout(() => { caixa.hidden = true; }, tipo === 'erro' ? 10000 : 6000);
  };
  const piscar = (alvo, classe) => {
    alvo.classList.remove('salvo', 'conflito');
    void alvo.offsetWidth;
    alvo.classList.add(classe);
    setTimeout(() => alvo.classList.remove(classe), 1300);
  };

  // ------------------------------------------------------------ calendário (só destaca os dias; sem números)
  let trocouMes = false;
  const renderCalendario = () => {
    const cx = q('#ag-calendario');
    cx.replaceChildren();
    cx.classList.toggle('ag-troca', trocouMes);
    trocouMes = false;
    const [ano, mes] = estado.mes.split('-').map(Number);
    const topo = el('div', 'ag-cal-topo');
    const ant = botao('‹', 'ag-nav', () => mudarMes(-1));
    ant.setAttribute('aria-label', 'Mês anterior');
    const prox = botao('›', 'ag-nav', () => mudarMes(1));
    prox.setAttribute('aria-label', 'Próximo mês');
    topo.append(ant, el('strong', '', `${MESES[mes - 1]} ${ano}`), prox);
    const grade = el('div', 'ag-cal-grade');
    ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'].forEach((l) => grade.append(el('span', 'ag-semana', l)));
    const deslocamento = new Date(ano, mes - 1, 1).getDay();
    for (let i = 0; i < deslocamento; i += 1) grade.append(el('span', 'ag-vazio'));
    const total = new Date(ano, mes, 0).getDate();
    for (let d = 1; d <= total; d += 1) {
      const iso = `${estado.mes}-${String(d).padStart(2, '0')}`;
      let classe = 'ag-dia-btn';
      if (estado.marcas.dias.includes(iso)) classe += ' tem';
      if (iso in estado.marcas.bloqueados) classe += ' bloq';
      if (iso === hoje) classe += ' hoje';
      if (iso === estado.data) classe += ' sel';
      const b = botao(String(d), classe, () => selecionar(iso));
      if (iso in estado.marcas.bloqueados) b.title = 'Bloqueado: ' + (estado.marcas.bloqueados[iso] || 'sem atendimento');
      else if (estado.marcas.dias.includes(iso)) b.title = 'Há agenda neste dia';
      grade.append(b);
    }
    aplicarTamanhoCalendario(cx);
    cx.append(topo, grade, botao('Ir para hoje', 'btn sec peq ag-hoje', () => selecionar(hoje)));
    cx.append(linhaTamanhoCalendario(cx), linhaCorCalendario(cx));
  };
  // tamanho dos números do calendário (botões Nº− e Nº+); fica neste navegador
  const CHAVE_CAL_FS = 'nucleleste.agendaCalNumero';
  let calFs = 12;
  try { calFs = Number(localStorage.getItem(CHAVE_CAL_FS)) || 12; } catch (e) { calFs = 12; }
  const aplicarTamanhoCalendario = (cx) => { calFs = Math.min(20, Math.max(10, calFs)); cx.style.setProperty('--ag-cal-fs', calFs + 'px'); };
  const linhaTamanhoCalendario = (cx) => {
    const linha = el('div', 'ag-cal-cor ag-cal-tam');
    const mudar = (delta) => {
      calFs += delta;
      aplicarTamanhoCalendario(cx);
      try { localStorage.setItem(CHAVE_CAL_FS, String(calFs)); } catch (e) { /* vale só para esta tela */ }
    };
    const menos = botao('Nº−', 'btn sec peq', () => mudar(-2));
    menos.title = 'Diminuir os números do calendário';
    const mais = botao('Nº+', 'btn sec peq', () => mudar(2));
    mais.title = 'Aumentar os números do calendário';
    linha.append(el('span', '', 'Números do calendário'), el('span', 'ag-cal-botoes'));
    linha.lastChild.append(menos, mais);
    return linha;
  };
  // cor de fundo do calendário, escolhida por quem usa; fica no perfil (vale em qualquer computador)
  const aplicarCorCalendario = (cx, cor) => {
    cx.dataset.cor = cor;
    cx.classList.toggle('personalizado', !!cor);
    if (!cor) { cx.style.removeProperty('--ag-cal-fundo'); cx.style.removeProperty('--texto'); cx.style.removeProperty('--suave'); return; }
    cx.style.setProperty('--ag-cal-fundo', cor);
    // fundo escuro: texto claro, para o calendário continuar legível
    const n = [1, 3, 5].map((i) => parseInt(cor.substr(i, 2), 16));
    const claro = (0.299 * n[0] + 0.587 * n[1] + 0.114 * n[2]) / 255 > 0.6;
    cx.style.setProperty('--texto', claro ? '#1d2522' : '#f4f8f6');
    cx.style.setProperty('--suave', claro ? '#5d6b64' : '#c9d6cf');
  };
  const linhaCorCalendario = (cx) => {
    const linha = el('div', 'ag-cal-cor');
    const rotulo = el('label', '', 'Cor do calendário');
    const escolha = el('input');
    escolha.type = 'color';
    escolha.value = cx.dataset.cor || '#ffffff';
    rotulo.prepend(escolha);
    const salvar = async (cor) => {
      try {
        const r = await fetch('/meu-tema', {method: 'POST', body: new URLSearchParams({cor_calendario: cor}), credentials: 'same-origin',
          headers: {Accept: 'application/json', 'X-CSRF-Token': csrf}});
        if (!r.ok) throw new Error(String(r.status));
      } catch (e) { aviso('Não foi possível salvar a cor do calendário.', 'erro'); return; }
      aplicarCorCalendario(cx, cor);
    };
    escolha.addEventListener('change', () => salvar(escolha.value));
    const padrao = botao('Cor padrão', 'btn sec peq', () => { escolha.value = '#ffffff'; salvar(''); }, !cx.dataset.cor);
    linha.append(rotulo, padrao);
    if (cx.dataset.cor) aplicarCorCalendario(cx, cx.dataset.cor);
    return linha;
  };
  const mudarMes = (delta) => {
    const [ano, mes] = estado.mes.split('-').map(Number);
    const d = new Date(ano, mes - 1 + delta, 1);
    estado.mes = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    trocouMes = true;
    renderCalendario();
    carregarMarcas();
  };
  const carregarMarcas = async () => {
    try { estado.marcas = await buscar('/agenda/mes?mes=' + estado.mes, true); } catch (e) { /* mantém as marcas atuais */ }
    renderCalendario();
  };

  // ------------------------------------------------------------ dia
  const calcResumo = (linhas) => {
    const r = {vagas: linhas.length, marcados: 0, livres: 0, reservados: 0, AGENDADO: 0, VEIO: 0, FALTOU: 0, RETORNO: 0, RESGATADO: 0, DESISTIU: 0, chegou: 0};
    linhas.forEach((l) => {
      if (l.paciente.trim()) { r.marcados += 1; r[l.status in ROTULOS ? l.status : 'AGENDADO'] += 1; if (l.chegou) r.chegou += 1; }
      else if (l.reservado) r.reservados += 1;   // guardado para o UNACON: não conta como livre
      else r.livres += 1;
    });
    return r;
  };
  const preencherResumo = (cx, r) => {
    cx.replaceChildren();
    cx.append(el('span', 'ag-sel', `${r.marcados}/${r.vagas} marcados`));
    // singular quando for 1 ("1 veio", "1 faltou"); plural a partir de 2 ("2 vieram", "2 faltaram")
    // atendido = veio + retorno (classe do balão de "veio")
    [['chegou', r.chegou || 0, ['chegou', 'chegaram']], ['veio', (r.VEIO || 0) + (r.RETORNO || 0), ['atendido', 'atendidos']], ['faltou', r.FALTOU, ['faltou', 'faltaram']],
     ['resgatado', r.RESGATADO, ['reagendado', 'reagendados']]].forEach(([c, n, [um, varios]]) => {
      if (n) cx.append(el('span', 'ag-sel st-' + c, `${n} ${n === 1 ? um : varios}`));
    });
    if (r.livres) cx.append(el('span', 'ag-sel livre', `${r.livres} livre(s)`));
    if (r.reservados) cx.append(el('span', 'ag-sel reservado', `${r.reservados} reservado(s)`));
  };

  const visiveis = () => estado.dia.agendas.filter((a) => estado.filtro === 'todos' || String(a.id) === estado.filtro);

  // `animar`: entrada suave dos blocos e linhas (ao abrir um dia ou trocar de exame; não nas atualizações automáticas)
  const renderDia = (animar) => {
    const cx = q('#ag-dia');
    const painel = q('#ag-painel');
    cx.replaceChildren();
    painel.replaceChildren();
    cx.classList.toggle('ag-anima', !!animar);
    painel.classList.toggle('ag-anima', !!animar);
    const d = estado.dia;
    if (estado.filtro !== 'todos' && !d.agendas.some((a) => String(a.id) === estado.filtro)) estado.filtro = 'todos';
    const bloqueado = d.bloqueado !== null;

    // topo da agenda: só a data (cada exame tem o seu nome no próprio bloco)
    const cab = el('div', 'ag-cab');
    cab.append(el('h2', '', dataExtenso(d.data)));
    // escolha do exame mostrado (substitui os botões que ficavam abaixo de "Criar agenda")
    if (d.agendas.length) {
      const escolha = el('span', 'ag-escolha');
      // bloco com título, ícone do sprite e uma dica curta embaixo do seletor
      const caixa = el('span', 'ag-escolha-caixa');
      const rotulo = el('span', 'ag-escolha-rotulo');
      rotulo.append(icone('flask-conical', 14), el('span', '', 'Exame'));
      caixa.append(rotulo);
      const sel = document.createElement('select');
      sel.setAttribute('aria-label', 'Exame mostrado na agenda');
      sel.title = 'Escolher o exame mostrado na agenda';
      [['todos', 'Todos os exames']].concat(d.agendas.map((a) => [String(a.id), `${a.exame} · ${a.inicio}`])).forEach(([v, t]) => {
        const o = document.createElement('option'); o.value = v; o.textContent = t; o.selected = estado.filtro === v; sel.append(o);
      });
      sel.addEventListener('change', () => { estado.filtro = sel.value; renderDia(true); });
      caixa.append(sel);
      escolha.append(caixa, el('small', 'ag-escolha-dica', 'Escolha um exame para ver só a grade dele, ou Todos para o dia inteiro.'));
      if (d.agendas.length > 1) caixa.append(botao(ordenando ? 'Pronto' : 'Ordenar', 'btn sec peq', () => { ordenando = !ordenando; renderDia(false); }));
      cab.append(escolha);
    }
    // observações das agendas do dia, como lembrete em vermelho ao lado da data
    const lembretes = [...new Set(d.agendas.map((a) => a.observacao).filter(Boolean))];
    if (lembretes.length) cab.append(el('span', 'ag-lembrete', lembretes.join(' · ')));
    cx.append(cab);
    // ações do dia ficam no painel, abaixo da legenda
    const barra = el('div', 'ag-barra');
    barra.append(
      botao('+ Criar agenda', 'btn', abrirCriar, bloqueado),
      botao('Copiar para outro dia', 'btn sec', abrirCopiar, !d.agendas.length),
      botao('🖨 Imprimir o dia', 'btn sec', imprimir, !d.agendas.length),
      botao(bloqueado ? 'Desbloquear dia' : 'Bloquear dia', 'btn sec', alternarBloqueio, !bloqueado && d.agendas.length > 0));
    // planilhas das vagas reservadas para convênio: só aparecem quando o dia tem vaga reservada ainda em branco
    if (calcResumo(d.agendas.flatMap((a) => a.linhas)).reservados > 0) {
      barra.append(botao('Planilha das reservas', 'btn sec', () => { window.open(`/agenda/reservas/planilha?de=${d.data}&ate=${d.data}`, '_blank'); }, false, 'file-down'),
        botao('Importar planilha', 'btn sec', importarPlanilha, false, 'upload'));
    }
    painel.append(barra);
    if (bloqueado) cx.append(el('div', 'ag-bloqueado', 'Dia bloqueado: ' + (d.bloqueado || 'sem atendimento') + '. Não é possível criar agendas.'));

    if (d.agendas.length) {
      // ordem das agendas: o botão "Ordenar" (ao lado da escolha do exame) mostra as setas ↑ ↓ (a ordem fica salva para todos os dias)
      const chips = el('div', 'ag-chips');
      d.agendas.forEach((a) => {
        const item = el('span', 'ag-chip-item');
        if (ordenando) {
          item.append(el('span', 'ag-chip', `${a.exame} · ${a.inicio}`));
          const mover = (direcao) => async () => {
            try { await enviar('/agenda/exame/mover', {exame: a.exame, direcao}); } catch (e) { return; }
            carregarDia(true);
          };
          item.append(botao('↑', 'ag-chip ag-chip-seta', mover('cima'), d.agendas[0] === a));
          item.append(botao('↓', 'ag-chip ag-chip-seta', mover('baixo'), d.agendas[d.agendas.length - 1] === a));
        }
        chips.append(item);
      });
      if (ordenando) painel.append(chips);
      const total = calcResumo(visiveis().flatMap((a) => a.linhas));
      const geral = el('div', 'ag-resumo ag-geral');
      preencherResumo(geral, total);
      painel.append(geral);
      visiveis().forEach((a, i) => {
        const bloco = blocoAgenda(a);
        bloco.style.setProperty('--b', i);
        cx.append(bloco);
      });
    } else if (!bloqueado) {
      cx.append(el('div', 'ag-vazio-dia', 'Nenhuma agenda neste dia. Clique em “+ Criar agenda” para começar.'));
    }
    cx.append(blocoEspera());
    if (somenteLeitura) bloquearEdicao();
  };

  // importar a planilha que o convênio devolveu (o arquivo é lido e descartado; nada fica guardado)
  const importarPlanilha = () => {
    const entrada = document.createElement('input');
    entrada.type = 'file';
    entrada.accept = '.xlsx';
    entrada.addEventListener('change', async () => {
      const arq = entrada.files[0];
      if (!arq) return;
      const dados = new FormData();
      dados.append('planilha', arq);
      let r, j = {};
      try {
        r = await fetch('/agenda/reservas/importar?json=1', {method: 'POST', body: dados, credentials: 'same-origin',
          headers: {Accept: 'application/json', 'X-CSRF-Token': csrf}});
        j = await r.json();
      } catch (e) { aviso('Não foi possível importar a planilha.', 'erro'); return; }
      if (!r.ok) { aviso(j.erro || 'Não foi possível importar a planilha.', 'erro'); return; }
      const problemas = (j.problemas || []).length;
      aviso(`${j.preenchidas} vaga(s) preenchida(s) na agenda` + (problemas ? ` · ${problemas} linha(s) com problema: ${j.problemas.slice(0, 3).join(' | ')}${problemas > 3 ? '…' : ''}` : '.'),
        problemas ? 'erro' : 'ok');
      await recarregar();
    });
    entrada.click();
  };

  // perfil só de consulta: campos travados e sem botões de alteração (o servidor também recusa qualquer alteração)
  const bloquearEdicao = () => {
    raiz.classList.add('ag-leitura');
    raiz.querySelectorAll('#ag-dia input, #ag-dia select, #ag-dia textarea').forEach((c) => { if (c.tagName === 'SELECT') c.disabled = true; else c.readOnly = true; });
    raiz.querySelectorAll('#ag-painel .btn').forEach((b) => { if (!/Imprimir/.test(b.textContent)) b.hidden = true; });
  };

  // ------------------------------------------------------------ grade de uma agenda
  const blocoAgenda = (a) => {
    const sec = el('section', 'ag-bloco');
    sec.dataset.agenda = a.id;
    const topo = el('div', 'ag-bloco-topo');
    const tit = el('div', 'ag-bloco-tit');
    tit.append(el('h3', '', a.exame), el('small', '', `${a.inicio} às ${a.fim} · intervalo de ${a.intervalo} min` + (a.vagas > 1 ? ` · ${a.vagas} por horário` : '')));
    const resumo = el('div', 'ag-resumo');
    resumo.dataset.resumo = a.id;
    preencherResumo(resumo, a.resumo);
    const acoes = el('div', 'ag-bloco-acoes');
    acoes.append(botao('+ Horário', 'btn sec peq', () => acrescentar(a)));
    // reserva para convênio: os botões só aparecem na agenda criada com a aba "Reservar horários para um convênio"
    if (a.reserva_convenio) acoes.append(botao('Reservar ' + a.reserva_convenio, 'btn sec peq', () => reservarFaixa(a, true)),
      botao('Liberar reserva', 'btn sec peq', () => reservarFaixa(a, false)));
    acoes.append(botao('Renomear', 'btn sec peq', () => renomearAgenda(a)));
    if (podeExcluir) acoes.append(botao('Excluir agenda', 'btn perigo peq', () => excluirAgenda(a)));
    topo.append(tit, resumo, acoes);

    const wrap = el('div', 'tabela-wrap ag-wrap');
    const t = el('table', 'ag-grade');
    const cols = el('colgroup');
    ['ag-c-n', 'ag-c-hora', 'ag-c-paciente', 'ag-c-idade', 'ag-c-convenio', 'ag-c-contato', 'ag-c-senha', 'ag-c-obs', 'ag-c-status', 'ag-c-acoes'].forEach((c) => cols.append(el('col', c)));
    const cabeca = el('thead');
    const tr = el('tr');
    ['Nº', ...Object.entries(COLUNAS).map(([k, n]) => (k === 'senha' ? (a.coluna_titulo || n) : n)), 'Status', ''].forEach((n, k) => tr.append(el('th', k === 0 ? 'ag-th-n' : '', n)));
    cabeca.append(tr);
    const corpo = el('tbody');
    a.linhas.forEach((l, i) => {
      const tr = linha(a, l);
      tr.style.setProperty('--r', Math.min(i, 16));
      corpo.append(tr);
    });
    t.append(cols, cabeca, corpo);
    habilitarRedimensionar(t, cols, tr);
    wrap.append(t);
    sec.append(topo, wrap);
    return sec;
  };

  // ------------------------------------------------------------ colunas como no Excel
  // arrastar a borda do título muda a largura da coluna em todas as agendas; fica salvo neste navegador
  const CHAVE_COLS = 'nucleleste.agendaColunas';
  const numPx = () => 39;   // largura da coluna do número das linhas
  let larguras = null;   // null = larguras padrão (proporcionais à tela); senão uma lista de px, uma por coluna
  try { larguras = JSON.parse(localStorage.getItem(CHAVE_COLS)); } catch (e) { larguras = null; }
  // formato antigo (8 colunas, sem idade): a idade entra na posição 2 com a largura padrão
  if (Array.isArray(larguras) && larguras.length === 8) larguras.splice(2, 0, 52);
  if (!Array.isArray(larguras) || larguras.length !== 9) larguras = null;
  const salvarLarguras = () => { try { if (larguras) localStorage.setItem(CHAVE_COLS, JSON.stringify(larguras)); else localStorage.removeItem(CHAVE_COLS); } catch (e) { /* vale só para esta tela */ } };
  const aplicarLarguras = (t) => {
    const cs = t.querySelectorAll('col');
    if (!larguras) { t.style.width = ''; cs.forEach((c) => { c.style.width = ''; }); return; }
    let soma = numPx();
    cs[0].style.width = soma + 'px';
    larguras.forEach((w, i) => {
      cs[i + 1].style.width = w + 'px';
      const oculta = (i === 2 && raiz.querySelector('.ag-principal.ag-sem-idade')) || (i === larguras.length - 1 && raiz.querySelector('.ag-principal.ag-sem-acoes'));
      if (!oculta) soma += w;
    });
    t.style.width = soma + 'px';
  };
  const aplicarTodas = () => document.querySelectorAll('.ag-grade:not(.ag-grade-espera)').forEach(aplicarLarguras);
  function habilitarRedimensionar(t, cols, linhaTitulos) {
    [...linhaTitulos.children].forEach((th, c) => {
      if (c === 0 || c === linhaTitulos.children.length - 1) return;   // o número e a última (ações) não precisam de alça
      const i = c - 1;   // posição em `larguras`
      const alca = el('span', 'ag-rz');
      alca.title = 'Arraste para mudar a largura da coluna (duplo clique: largura original). Use "Tornar padrão" para guardar.';
      alca.addEventListener('dblclick', (ev) => { ev.stopPropagation(); if (larguras) { larguras = null; salvarLarguras(); aplicarTodas(); } });
      alca.addEventListener('pointerdown', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        if (!larguras) larguras = [...linhaTitulos.children].slice(1).map((x, k, todos) => (k === todos.length - 1 ? 172 : Math.max(48, Math.round(x.getBoundingClientRect().width))));   // congela as larguras atuais
        const x0 = ev.clientX, w0 = larguras[i];
        alca.setPointerCapture(ev.pointerId);
        document.body.classList.add('ag-redimensionando');
        const mover = (e) => { larguras[i] = Math.max(48, Math.round(w0 + e.clientX - x0)); aplicarTodas(); };
        const soltar = () => {
          alca.removeEventListener('pointermove', mover);
          alca.removeEventListener('pointerup', soltar);
          alca.removeEventListener('pointercancel', soltar);
          document.body.classList.remove('ag-redimensionando');   // só vira padrão no botão "Tornar padrão"
        };
        alca.addEventListener('pointermove', mover);
        alca.addEventListener('pointerup', soltar);
        alca.addEventListener('pointercancel', soltar);
      });
      th.append(alca);
    });
    aplicarLarguras(t);
  }

  // protocolo (MIBI) pinta a linha de verde enquanto o paciente está só agendado; presença (Veio) fica azul
  // reservado para o UNACON: rosa (ver agenda.css)
  const classeLinha = (a, l) => {
    const unacon = l.reservado ? ' unacon' : '';
    if (!l.paciente.trim()) return 'ag-linha livre' + unacon;
    if (a.mibi && l.senha === 'Protocolo' && l.status === 'AGENDADO') return 'ag-linha protocolo' + unacon;
    return 'ag-linha st-' + l.status.toLowerCase() + unacon;
  };

  // caixa "Chegou" ao lado do número da linha: vale para todos os usuários, entra no resumo e no relatório e fica registrada no histórico da linha
  const celulaNumero = (a, l) => {
    const td = el('td', 'ag-num');
    const cb = el('input', 'ag-chegou');
    cb.type = 'checkbox';
    cb.checked = !!l.chegou;
    cb.disabled = !l.paciente.trim();
    cb.title = l.chegou && l.chegou_por ? 'Chegou (marcado por ' + l.chegou_por + ')' : 'Marcar que o paciente chegou';
    cb.setAttribute('aria-label', 'Chegou');
    cb.addEventListener('change', async () => {
      const marcado = cb.checked;
      let r;
      try { r = await enviar(`/agenda/horario/${l.id}/chegou`, {valor: marcado ? '1' : '0'}); } catch (e) { cb.checked = !marcado; return; }
      if (!r.ok) { cb.checked = !marcado; aviso(r.erro || 'Não foi possível marcar a chegada.', 'erro'); return; }
      l.chegou = marcado;
      atualizarLinha(a, l);
    });
    td.append(cb);
    return td;
  };
  const linha = (a, l) => {
    const tr = el('tr', classeLinha(a, l));
    tr.dataset.id = l.id;
    tr.append(celulaNumero(a, l), celulaTexto(a, l, 'hora', 'ag-hora'), celulaTexto(a, l, 'paciente'), celulaTexto(a, l, 'idade', 'ag-idade'), celulaConvenio(a, l), celulaContato(a, l),
              celulaSenha(a, l), celulaTexto(a, l, 'observacao'), celulaStatus(a, l), celulaAcoes(a, l));
    // rótulos que o celular mostra em cada campo (a linha vira um cartão; ver agenda.css)
    ['Nº', 'Horário', 'Paciente', 'Idade', 'Convênio', 'Contato', a.coluna_titulo || 'Senha de autorização', 'Observação/Senha', 'Status', ''].forEach((r, k) => { tr.children[k].dataset.rot = r; });
    return tr;
  };

  const navegar = (ev) => {
    if (ev.key !== 'Enter' && ev.key !== 'ArrowDown' && ev.key !== 'ArrowUp') return;
    const td = ev.target.closest('td');
    const tr = td.parentElement;
    const col = Array.prototype.indexOf.call(tr.children, td);
    const alvo = ev.key === 'ArrowUp' ? tr.previousElementSibling : tr.nextElementSibling;
    if (!alvo) return;
    ev.preventDefault();
    const dest = alvo.children[col].querySelector('input, select');
    if (dest) { dest.focus(); if (dest.select) dest.select(); }
  };

  const criarCampo = (l, campo, classe) => {
    const i = el('input', classe || '');
    i.type = 'text';
    i.value = l[campo];
    i.dataset.antes = l[campo];
    i.maxLength = LIMITES[campo];
    i.autocomplete = 'off';
    if (campo === 'idade') i.inputMode = 'numeric';
    i.setAttribute('aria-label', COLUNAS[campo]);
    if (campo === 'paciente') i.placeholder = 'livre';
    i.addEventListener('keydown', navegar);
    return i;
  };
  const celulaTexto = (a, l, campo, classe) => {
    const td = el('td');
    const i = criarCampo(l, campo, classe);
    i.addEventListener('change', () => salvar(a, l, campo, i));
    td.append(i);
    return td;
  };
  // no MIBI, a senha de autorização é uma escolha (Estresse, Repouso ou Protocolo)
  const OPCOES_SENHA_MIBI = ['Estresse', 'Repouso', 'Protocolo'];
  const celulaSenha = (a, l) => {
    if (!a.mibi) return celulaTexto(a, l, 'senha');
    const td = el('td', 'ag-senha-td');
    const sel = el('select', 'ag-senha');
    sel.setAttribute('aria-label', COLUNAS.senha);
    sel.append(Object.assign(el('option', '', '—'), {value: ''}));
    OPCOES_SENHA_MIBI.forEach((op) => sel.append(Object.assign(el('option', '', op), {value: op})));
    // texto digitado antes da mudança para MIBI: continua aparecendo até ser trocado
    if (l.senha && !OPCOES_SENHA_MIBI.includes(l.senha)) sel.append(Object.assign(el('option', '', l.senha), {value: l.senha}));
    sel.value = l.senha;
    sel.dataset.antes = l.senha;
    sel.className = 'ag-senha' + (l.senha === 'Protocolo' ? ' protocolo' : '');
    sel.addEventListener('change', () => salvar(a, l, 'senha', sel));
    sel.addEventListener('keydown', navegar);
    td.append(sel);
    return td;
  };
  // convênio: escolhido entre os cadastrados em Convênios (um texto antigo fica visível até ser trocado)
  const celulaConvenio = (a, l) => {
    const td = el('td', 'ag-convenio-td');
    const sel = el('select', 'ag-convsel');
    sel.setAttribute('aria-label', COLUNAS.convenio);
    const lista = estado.dia.convenios || [];
    sel.append(Object.assign(el('option', '', '—'), {value: ''}));
    lista.forEach((nome) => sel.append(Object.assign(el('option', '', nome), {value: nome})));
    if (l.convenio && !lista.includes(l.convenio)) sel.append(Object.assign(el('option', '', l.convenio + ' (fora da lista)'), {value: l.convenio}));
    sel.value = l.convenio;
    sel.dataset.antes = l.convenio;
    sel.addEventListener('change', () => salvar(a, l, 'convenio', sel));
    sel.addEventListener('keydown', navegar);
    td.append(sel);
    return td;
  };
  // vários contatos ficam no mesmo campo, separados por " / "; a setinha alterna qual aparece e para quem vai o WhatsApp
  const contatosDe = (v) => (v || '').split('/').map((s) => s.trim()).filter(Boolean);
  const celulaContato = (a, l) => {
    const td = el('td', 'ag-contato');
    const i = criarCampo(l, 'contato');
    let ativo = 0;
    const trocar = el('button', 'ag-trocar', '⇄');
    trocar.type = 'button';
    const zap = el('a', 'ag-zap', '💬');
    zap.target = '_blank';
    zap.rel = 'noopener';
    zap.href = '#';
    zap.title = 'Enviar pelo WhatsApp';
    const digitos = () => i.value.replace(/\D/g, '');
    // mostra o contato ativo; com dois ou mais, a setinha aparece
    const mostrar = () => {
      const lista = contatosDe(l.contato);
      if (ativo >= lista.length) ativo = 0;
      i.value = lista[ativo] || '';
      i.dataset.antes = i.value;
      trocar.hidden = lista.length < 2;
      trocar.title = lista.length > 1 ? `Trocar contato (${ativo + 1} de ${lista.length})` : '';
      ajustar();
    };
    i.addEventListener('change', async () => {
      // guarda a lista inteira: troca só o contato que estava na tela
      const lista = contatosDe(l.contato);
      lista[ativo] = i.value.trim();
      const todos = contatosDe(lista.join(' / ')).join(' / ');
      i.value = todos;
      i.dataset.antes = contatosDe(l.contato).join(' / ');
      await salvar(a, l, 'contato', i);
      mostrar();
    });
    trocar.addEventListener('click', () => {
      const n = contatosDe(l.contato).length;
      ativo = (ativo + 1) % n;
      mostrar();
    });
    const ajustar = () => { zap.hidden = digitos().length < 10; };
    zap.addEventListener('click', (ev) => {
      ev.preventDefault();
      const d = digitos();
      const numero = d.length <= 11 ? '55' + d : d;
      const nome = (l.paciente || '').trim().split(' ')[0];
      // quem faltou recebe a mensagem de resgate (importância do exame e apelo); os demais, o lembrete
      const msg = l.status === 'FALTOU'
        ? mensagemResgate(nome, a.exame, dataBR(estado.data), l.hora)
        : preencherModelo(MODELOS_WHATS.lembrete, {nome, exame: a.exame, data: dataBR(estado.data), hora: l.hora});
      const texto = encodeURIComponent((USUARIO_ENVIO ? `Enviado por ${USUARIO_ENVIO}: ` : '') + msg);
      const web = `https://wa.me/${numero}?text=${texto}`;
      zap.href = web;
      // 1º tenta abrir o WhatsApp instalado no computador; se a janela não perder o foco (o app não abriu), abre o WhatsApp Web
      let abriuApp = false;
      const aoPerderFoco = () => { abriuApp = true; };
      window.addEventListener('blur', aoPerderFoco, {once: true});
      // iframe escondido: se não houver app instalado, a página do sistema não sai do lugar
      const ponte = document.createElement('iframe');
      ponte.style.display = 'none';
      ponte.src = `whatsapp://send?phone=${numero}&text=${texto}`;
      document.body.append(ponte);
      setTimeout(() => {
        window.removeEventListener('blur', aoPerderFoco);
        ponte.remove();
        if (!abriuApp) window.open(web, '_blank', 'noopener');
      }, 1500);
    });
    i.addEventListener('input', ajustar);
    mostrar();
    td.append(i, trocar, zap);
    return td;
  };
  // abre o cadastro de cliente em outra aba, com o nome, o contato e o convênio da linha
  const abrirCadastro = (l) => {
    const p = new URLSearchParams({nome: l.paciente.trim(), contato: l.contato || '', convenio: l.convenio || '', idade: l.idade || ''});
    window.open('/clientes/novo?' + p.toString(), '_blank', 'noopener');
  };
  const celulaStatus = (a, l) => {
    const td = el('td', 'ag-status-td');
    const sel = el('select', 'ag-status st-' + l.status.toLowerCase());
    sel.setAttribute('aria-label', 'Status');
    Object.keys(ROTULOS).forEach((k) => {
      const o = el('option', '', ROTULOS[k]);
      o.value = k;
      sel.append(o);
    });
    sel.value = l.status;
    const travado = statusTravado(l);
    sel.disabled = !l.paciente.trim() || travado;
    if (travado) sel.title = 'Remarcado para outra data: o status desta linha só pode ser alterado por administrador ou gerência.';
    sel.addEventListener('change', async () => {
      const novo = sel.value;
      const anterior = l.status;
      if (novo === 'RETORNO') { sel.value = anterior; abrirRemarcar(a, l, false); return; }
      if (novo === 'RESGATADO' && !l.remarcado_para) { sel.value = anterior; abrirRemarcar(a, l, true); return; }
      let r;
      try { r = await enviar(`/agenda/horario/${l.id}/status`, {status: novo}); } catch (e) { sel.value = anterior; return; }
      if (!r.ok) { aviso(r.erro || 'Não foi possível mudar o status.', 'erro'); sel.value = anterior; return; }
      l.status = novo;
      l.remarcado_para = '';
      atualizarLinha(a, l);
      if (novo === 'VEIO' && r.cadastrado === false && window.confirm('Cadastrar ' + l.paciente.trim() + ' como cliente agora? Os dados da linha já vão preenchidos.')) abrirCadastro(l);
    });
    td.append(sel);
    if (l.remarcado_para) td.append(el('small', 'ag-remarcado', '→ ' + l.remarcado_para));
    return td;
  };
  // tesourinha (SVG próprio): as lâminas "cortam" quando o botão recebe o mouse
  const tesoura = () => {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('width', '18'); svg.setAttribute('height', '18'); svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('class', 'ag-tesoura');
    const parte = (tag, attrs, classe) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); if (classe) n.setAttribute('class', classe); svg.append(n); };
    parte('circle', {cx: 5.5, cy: 6, r: 2.8}); parte('circle', {cx: 5.5, cy: 18, r: 2.8});
    parte('path', {d: 'M8 7.6 21 18.6'}, 'lamina-a'); parte('path', {d: 'M8 16.4 21 5.4'}, 'lamina-b');
    return svg;
  };
  const celulaAcoes = (a, l) => {
    const td = el('td', 'ag-acoes-td');
    const recortar = botao('', 'ag-ico ag-ico-tesoura', () => abrirRecortar(a, l));
    recortar.append(tesoura());
    recortar.title = 'Recortar: leva este paciente para outro dia e libera este horário';
    recortar.setAttribute('aria-label', 'Recortar este paciente para outro dia');
    recortar.dataset.recortar = '1';
    recortar.hidden = !l.paciente.trim();
    const mais = botao('＋', 'ag-ico', () => acrescentar(a, l));
    mais.title = 'Mais uma vaga neste horário';
    const remarcar = botao('↪', 'ag-ico', () => abrirRemarcar(a, l));
    remarcar.title = 'Marcar o retorno: escolhe o outro dia e o horário (ex.: 2ª etapa do MIBI)';
    remarcar.dataset.remarcar = '1';
    remarcar.hidden = !l.paciente.trim();
    const copiar = botao('⧉', 'ag-ico', () => abrirCopiarLinha(a, l));
    copiar.title = 'Copiar este paciente para outro dia (ex.: retorno)';
    copiar.dataset.copiar = '1';
    copiar.hidden = !l.paciente.trim();
    const tirar = botao('✕', 'ag-ico ag-ico-perigo', () => retirar(l));
    tirar.title = 'Retirar este horário';
    const hist = botao('', 'ag-ico', () => abrirHistorico(l), false, 'history');
    hist.title = 'Histórico desta linha (quem alterou o quê e quando)';
    hist.setAttribute('aria-label', 'Histórico da linha');
    td.append(recortar, mais, copiar, remarcar, hist, tirar);
    return td;
  };

  // atualiza a linha na tela sem recriá-la (para não perder o foco de quem está digitando)
  const atualizarLinha = (a, l) => {
    const tr = q(`tr[data-id="${l.id}"]`);
    if (tr) {
      tr.className = classeLinha(a, l) + ' mudou';
      setTimeout(() => tr.classList.remove('mudou'), 1000);
      const sel = q('select.ag-status', tr);
      sel.value = l.status;
      sel.className = 'ag-status st-' + l.status.toLowerCase();
      sel.disabled = !l.paciente.trim() || statusTravado(l);
      const cbc = q('input.ag-chegou', tr);
      if (cbc) { cbc.checked = !!l.chegou; cbc.disabled = !l.paciente.trim(); }
      const sn = q('select.ag-senha', tr);
      if (sn) sn.className = 'ag-senha' + (l.senha === 'Protocolo' ? ' protocolo' : '');
      const r = q('[data-remarcar]', tr);
      if (r) r.hidden = !l.paciente.trim();
      const c = q('[data-copiar]', tr);
      if (c) c.hidden = !l.paciente.trim();
      const rc = q('[data-recortar]', tr);
      if (rc) rc.hidden = !l.paciente.trim();
      const nota = q('.ag-remarcado', tr);
      if (nota && !l.remarcado_para) nota.remove();
    }
    a.resumo = calcResumo(a.linhas);
    const cx = q(`[data-resumo="${a.id}"]`);
    if (cx) preencherResumo(cx, a.resumo);
    const geral = q('.ag-geral');
    if (geral) preencherResumo(geral, calcResumo(visiveis().flatMap((x) => x.linhas)));
    estado.assinatura = JSON.stringify(estado.dia);
  };

  // escreve o valor no campo; no seletor da senha, um texto antigo ganha a sua opção para continuar visível
  const definirValor = (i, v) => {
    if (i.tagName === 'SELECT' && v && ![...i.options].some((o) => o.value === v)) i.append(Object.assign(el('option', '', v), {value: v}));
    i.value = v;
  };

  const salvar = async (a, l, campo, i) => {
    const antes = i.dataset.antes || '';
    const valor = i.value;
    if (valor.trim() === antes.trim()) return;
    let r;
    try { r = await enviar(`/agenda/horario/${l.id}/campo`, {campo, valor, antes}); } catch (e) { return; }
    if (r.conflito) {
      definirValor(i, r.atual);
      i.dataset.antes = r.atual;
      l[campo] = r.atual;
      piscar(i, 'conflito');
      aviso(`${r.por || 'Outra pessoa'} alterou este campo agora há pouco. Mostrando o valor atual.`, 'erro');
      return;
    }
    if (!r.ok) {
      definirValor(i, antes);
      aviso(r.erro || 'Não foi possível salvar.', 'erro');
      return;
    }
    definirValor(i, r.valor);
    i.dataset.antes = r.valor;
    l[campo] = r.valor;
    l.status = r.status;
    l.reservado = !!r.reservado;
    if (campo === 'paciente') { if (!r.valor) l.remarcado_para = ''; }
    if (campo === 'paciente' || campo === 'senha' || campo === 'convenio') atualizarLinha(a, l);
    estado.assinatura = JSON.stringify(estado.dia);
    piscar(i, 'salvo');
    if (r.aviso) aviso(r.aviso, 'aviso');
  };

  // ------------------------------------------------------------ ações da agenda
  const recarregar = () => carregarDia(true);

  const acrescentar = async (a, linhaRef) => {
    let dados = {};
    if (linhaRef) dados = {depois: linhaRef.id};
    else {
      const resp = prompt('Quantos horários acrescentar ao fim da agenda?', '1');
      if (resp === null) return;
      const n = parseInt(resp, 10);
      if (!(n >= 1 && n <= 50)) { aviso('Informe um número entre 1 e 50.', 'erro'); return; }
      dados = {qtd: n};
    }
    const r = await enviar(`/agenda/${a.id}/horario`, dados);
    if (!r.ok) { aviso(r.erro || 'Não foi possível acrescentar.', 'erro'); return; }
    recarregar();
  };
  // reserva para o convênio da agenda: uma faixa de horários
  const reservarFaixa = async (a, reservar) => {
    const primeira = (a.linhas[0] || {}).hora || a.inicio;
    const ultima = (a.linhas[a.linhas.length - 1] || {}).hora || a.inicio;
    const texto = reservar
      ? `Reservar para ${a.reserva_convenio} os horários livres desta agenda.\nDo horário (HH:MM) até o horário (HH:MM), separados por espaço:`
      : `Liberar a reserva de ${a.reserva_convenio} nos horários sem paciente.\nDo horário (HH:MM) até o horário (HH:MM), separados por espaço:`;
    const resp = prompt(texto, `${primeira} ${ultima}`);
    if (resp === null) return;
    const [de, ate] = resp.trim().split(/\s+/);
    const r = await enviar(`/agenda/${a.id}/reservar`, {de: de || '', ate: ate || '', valor: reservar ? '1' : '0'});
    if (!r.ok) { aviso(r.erro || 'Não foi possível alterar a reserva.', 'erro'); return; }
    await recarregar();
    aviso(`${r.qtd} horário(s) ${reservar ? 'reservado(s) para ' + a.reserva_convenio : 'liberado(s)'}.`, 'ok');
  };
  const retirar = async (l) => {
    let r = await enviar(`/agenda/horario/${l.id}/excluir`, {});
    if (r.confirmar) {
      if (!confirm(r.erro)) return;
      r = await enviar(`/agenda/horario/${l.id}/excluir`, {confirmar: '1'});
    }
    if (!r.ok) { aviso(r.erro || 'Não foi possível retirar.', 'erro'); return; }
    recarregar();
  };
  // o nome da agenda vai no texto das mensagens de WhatsApp ({exame} e {agenda}); o exame cadastrado vinculado não muda
  const renomearAgenda = async (a) => {
    const nome = window.prompt('Nome da agenda (usado no texto das mensagens de WhatsApp):', a.exame);
    if (nome === null || nome.trim() === '' || nome.trim() === a.exame) return;
    const r = await enviar(`/agenda/${a.id}/nome`, {nome: nome.trim()});
    if (!r.ok) { aviso(r.erro || 'Não foi possível renomear.', 'erro'); return; }
    await recarregar();
    aviso('Nome da agenda alterado.', 'ok');
  };
  const dlgHistorico = q('#dlg-historico');
  async function abrirHistorico(l) {
    const lista = q('#historico-lista');
    lista.replaceChildren(el('li', 'sub', 'Carregando…'));
    q('#historico-titulo').textContent = `Histórico: ${l.paciente.trim() || 'horário ' + l.hora}`;
    dlgHistorico.showModal();
    let d;
    try { d = await (await fetch(`/agenda/horario/${l.id}/historico`, {credentials: 'same-origin', headers: {Accept: 'application/json'}})).json(); } catch (e) { lista.replaceChildren(el('li', 'sub', 'Não foi possível carregar.')); return; }
    lista.replaceChildren();
    (d.itens || []).forEach((i) => {
      const detalhe = i.campo ? `${i.campo}: ${i.antes || '(vazio)'} → ${i.depois || '(vazio)'}` : '';
      lista.append(el('li', '', `${dataBR(i.criado_em.slice(0, 10))} ${i.criado_em.slice(11, 16)} · ${i.usuario || 'sistema'} · ${i.acao}${detalhe ? ' (' + detalhe + ')' : ''}`));
    });
    if (!lista.children.length) lista.append(el('li', 'sub', 'Nenhuma alteração registrada nesta linha.'));
  }
  const excluirAgenda = async (a) => {
    if (!confirm(`Excluir a agenda de ${a.exame} (${a.inicio}) deste dia?`)) return;
    let r = await enviar(`/agenda/${a.id}/excluir`, {});
    if (r.confirmar) {
      if (!confirm(r.erro)) return;
      r = await enviar(`/agenda/${a.id}/excluir`, {confirmar: '1'});
    }
    if (!r.ok) { aviso(r.erro || 'Não foi possível excluir.', 'erro'); return; }
    estado.filtro = 'todos';
    await recarregar();
    carregarMarcas();
  };
  // --- imprimir: todos os exames ou só um
  const dlgImprimir = q('#dlg-imprimir');
  const fImprimir = q('#form-imprimir');
  const imprimir = () => {
    const lista = q('#imprimir-opcoes');
    lista.replaceChildren();
    const opcao = (valor, rotulo, marcado) => {
      const l = el('label', 'inline');
      const r = document.createElement('input');
      r.type = 'radio'; r.name = 'alvo'; r.value = valor; r.checked = marcado;
      l.append(r, ' ' + rotulo);
      lista.append(l, document.createElement('br'));
    };
    opcao('todos', 'Todos os exames', estado.filtro === 'todos');
    estado.dia.agendas.forEach((a) => opcao(String(a.id), `${a.exame} · ${a.inicio}`, estado.filtro === String(a.id)));
    dlgImprimir.showModal();
  };
  fImprimir.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const alvo = (fImprimir.querySelector('input[name="alvo"]:checked') || {}).value || 'todos';
    window.open(`/agenda/imprimir/${estado.data}.pdf?agenda=${alvo}`, '_blank');
    dlgImprimir.close();
  });
  const alternarBloqueio = async () => {
    let r;
    if (estado.dia.bloqueado !== null) r = await enviar('/agenda/desbloquear', {data: estado.data});
    else {
      const motivo = prompt('Motivo do bloqueio (feriado, manutenção do equipamento...):', '');
      if (motivo === null) return;
      r = await enviar('/agenda/bloquear', {data: estado.data, motivo});
    }
    if (!r.ok) { aviso(r.erro || 'Não foi possível alterar o bloqueio.', 'erro'); return; }
    await recarregar();
    carregarMarcas();
  };

  // ------------------------------------------------------------ janelas
  const mostrarErro = (dlg, texto) => {
    const p = q('[data-erro]', dlg);
    p.textContent = texto || '';
    p.hidden = !texto;
  };

  // --- criar agenda
  const dlgCriar = q('#dlg-criar');
  const fCriar = q('#form-criar');
  const campoCriar = (n) => fCriar.elements.namedItem(n);
  const emMinutos = (v) => { const m = /^(\d{1,2}):(\d{2})$/.exec(v || ''); return m ? Number(m[1]) * 60 + Number(m[2]) : null; };
  const deMinutos = (n) => `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`;
  const calcularFim = () => {
    const ini = emMinutos(campoCriar('inicio').value);
    const inter = Number(campoCriar('intervalo').value);
    const qtd = Number(campoCriar('qtd').value);
    campoCriar('fim').value = ini !== null && inter > 0 && qtd > 0 && ini + inter * qtd < 1440 ? deMinutos(ini + inter * qtd) : '';
  };
  const calcularQtd = () => {
    const ini = emMinutos(campoCriar('inicio').value);
    const fim = emMinutos(campoCriar('fim').value);
    const inter = Number(campoCriar('intervalo').value);
    if (ini !== null && fim !== null && inter > 0 && fim > ini) campoCriar('qtd').value = Math.floor((fim - ini) / inter);
  };
  ['inicio', 'intervalo', 'qtd'].forEach((n) => campoCriar(n).addEventListener('input', calcularFim));
  campoCriar('fim').addEventListener('input', calcularQtd);
  campoCriar('salvar_modelo').addEventListener('change', () => {
    const nome = campoCriar('nome_modelo');
    nome.hidden = !campoCriar('salvar_modelo').checked;
    if (!nome.hidden) nome.focus();
  });
  campoCriar('modelo').addEventListener('change', () => {
    const m = estado.dia.modelos.find((x) => String(x.id) === campoCriar('modelo').value);
    if (!m) return;
    campoCriar('exame').value = m.exame;
    if (m.exame_id) campoCriar('exame_id').value = m.exame_id;
    campoCriar('inicio').value = m.inicio;
    campoCriar('intervalo').value = m.intervalo;
    campoCriar('qtd').value = m.qtd;
    campoCriar('vagas').value = m.vagas;
    calcularFim();
    ajustarColuna();
  });
  // 6ª coluna: no MIBI pede a etapa (a coluna se chama Etapa); nos demais exames o título é editável e já vem o exame vinculado
  const ehMibiNome = (t) => /MIBI|MIOCARD/i.test(t || '');
  const ajustarColuna = () => {
    const sel = campoCriar('exame_id');
    const nome = sel.selectedIndex > 0 ? sel.options[sel.selectedIndex].text : '';
    const mibi = ehMibiNome(nome);
    q('#c-etapa-bloco').hidden = !mibi;
    q('#c-coluna-bloco').hidden = mibi;
    campoCriar('etapa').required = mibi;
    if (!mibi) campoCriar('etapa').value = '';
  };
  campoCriar('exame_id').addEventListener('change', ajustarColuna);
  function abrirCriar() {
    fCriar.reset();
    ajustarColuna();
    campoCriar('data').value = estado.data;
    campoCriar('intervalo').value = 30;
    campoCriar('vagas').value = 1;
    campoCriar('semanas').value = 0;
    campoCriar('nome_modelo').hidden = true;
    const sel = campoCriar('modelo');
    sel.replaceChildren(Object.assign(el('option', '', '(sem modelo)'), {value: ''}));
    estado.dia.modelos.forEach((m) => sel.append(Object.assign(el('option', '', m.nome), {value: m.id})));
    if (estado.filtro !== 'todos') {
      const a = estado.dia.agendas.find((x) => String(x.id) === estado.filtro);
      if (a) campoCriar('exame').value = a.exame;
    }
    mostrarErro(dlgCriar, '');
    q('#r-convenio').replaceChildren();
    q('#r-inicio').value = '';
    q('#r-qtd').value = 5;
    q('#r-passo').value = 1;
    alternarReserva(false);
    dlgCriar.showModal();
    campoCriar('exame').focus();
  }
  fCriar.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const dados = {};
    new FormData(fCriar).forEach((v, k) => { dados[k] = v; });
    if (!dados.qtd && dados.fim) { calcularQtd(); dados.qtd = campoCriar('qtd').value; }
    const r = await enviar('/agenda/criar', dados);
    if (!r.ok) { mostrarErro(dlgCriar, r.erro || 'Não foi possível criar a agenda.'); return; }
    dlgCriar.close();
    estado.filtro = 'todos';
    await selecionar(r.data);
    let msg = r.criadas > 1 ? `${r.criadas} agendas criadas (repetidas nas semanas seguintes).` : 'Agenda criada.';
    if (r.pulados && r.pulados.length) msg += ` Dias bloqueados ignorados: ${r.pulados.map(dataBR).join(', ')}.`;
    aviso(msg, r.pulados && r.pulados.length ? 'aviso' : 'ok');
  });

  // --- copiar para outro dia
  const dlgCopiar = q('#dlg-copiar');
  const fCopiar = q('#form-copiar');
  function abrirCopiar() {
    fCopiar.reset();
    const sel = fCopiar.elements.namedItem('agenda_id');
    sel.replaceChildren(Object.assign(el('option', '', 'Todas as agendas deste dia'), {value: ''}));
    estado.dia.agendas.forEach((a) => sel.append(Object.assign(el('option', '', `${a.exame} · ${a.inicio}`), {value: a.id})));
    if (estado.filtro !== 'todos') sel.value = estado.filtro;
    fCopiar.elements.namedItem('destino').value = somarDias(estado.data, 1);
    mostrarErro(dlgCopiar, '');
    dlgCopiar.showModal();
  }
  fCopiar.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = fCopiar.elements;
    const destino = f.namedItem('destino').value;
    const resposta = (fCopiar.querySelector('input[name="apagar_origem"]:checked') || {}).value;
    if (!resposta) { mostrarErro(dlgCopiar, 'Responda se deseja apagar o dia atual.'); return; }
    const r = await enviar('/agenda/copiar', {origem: estado.data, destino, agenda_id: f.namedItem('agenda_id').value,
      com_pacientes: f.namedItem('com_pacientes').checked ? '1' : '', apagar_origem: resposta});
    if (!r.ok) { mostrarErro(dlgCopiar, r.erro || 'Não foi possível copiar.'); return; }
    dlgCopiar.close();
    await selecionar(destino);
    let msg = `${r.criadas} agenda(s) ${r.apagou ? 'movida(s)' : 'copiada(s)'} para ${dataBR(destino)}` + (r.pacientes ? ` com ${r.pacientes} paciente(s).` : '.');
    if (r.apagou) msg += ' O dia anterior foi apagado.';
    if (r.puladas && r.puladas.length) msg += ` Já existiam e foram mantidas: ${r.puladas.join(', ')}.`;
    aviso(msg, r.criadas ? 'ok' : 'aviso');
  });

  // --- escolher um horário livre (remarcar e encaixar)
  const dlgHorario = q('#dlg-horario');
  const fHorario = q('#form-horario');
  let contextoHorario = null;
  const carregarLivres = async () => {
    const data = fHorario.elements.namedItem('data').value;
    const sel = fHorario.elements.namedItem('destino');
    const ok = q('[data-confirmar-horario]', fHorario);
    sel.replaceChildren();
    ok.disabled = true;
    if (!data) return;
    let livres = [];
    // horário reservado para um convênio só aparece para pacientes desse convênio
    const sufixo = '?convenio=' + encodeURIComponent(contextoHorario.convenio || '');
    try { livres = (await buscar('/agenda/livres/' + data + sufixo)).livres; } catch (e) { return; }
    const exame = (contextoHorario.exame || '').toLowerCase();
    livres.sort((x, y) => ((y.exame.toLowerCase() === exame) - (x.exame.toLowerCase() === exame)) || x.exame.localeCompare(y.exame) || x.hora.localeCompare(y.hora));
    if (!livres.length) {
      sel.append(Object.assign(el('option', '', 'Não há horário livre neste dia'), {value: ''}));
      return;
    }
    livres.forEach((x) => sel.append(Object.assign(el('option', '', `${x.hora} · ${x.exame}` + (x.reservado ? ' (reservado ' + x.reservado_convenio + ')' : '')), {value: x.id})));
    ok.disabled = false;
  };
  fHorario.elements.namedItem('data').addEventListener('change', carregarLivres);
  const escolherHorario = (cfg) => {
    contextoHorario = cfg;
    q('[data-titulo]', dlgHorario).textContent = cfg.titulo;
    q('[data-texto]', dlgHorario).textContent = cfg.texto;
    q('[data-confirmar-horario]', dlgHorario).textContent = cfg.botaoOk;
    const extra = q('[data-extra]', dlgHorario);
    extra.hidden = !cfg.extra;
    if (cfg.extra) extra.textContent = cfg.extra.rotulo;
    fHorario.elements.namedItem('data').value = cfg.data;
    mostrarErro(dlgHorario, '');
    dlgHorario.showModal();
    carregarLivres();
  };
  q('[data-extra]', dlgHorario).addEventListener('click', async () => {
    if (contextoHorario && contextoHorario.extra) await contextoHorario.extra.acao();
  });
  fHorario.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const destino = fHorario.elements.namedItem('destino').value;
    if (!destino) { mostrarErro(dlgHorario, 'Escolha um horário livre.'); return; }
    const r = await contextoHorario.aoConfirmar(destino);
    if (!r.ok) { mostrarErro(dlgHorario, r.erro || 'Não foi possível concluir.'); return; }
    dlgHorario.close();
    const dia = fHorario.elements.namedItem('data').value;
    if (dia !== estado.data) await selecionar(dia); else await recarregar();
    aviso(contextoHorario.sucesso(r), 'ok');
  });

  // reagendado: falta resgatada com o paciente copiado para outro dia (a origem fica “Reagendado”)
  function abrirRemarcar(a, l, reagendado) {
    if (!l.paciente.trim()) return;
    escolherHorario({
      titulo: reagendado ? `Reagendar ${l.paciente}` : `Marcar o retorno de ${l.paciente}`,
      texto: reagendado
        ? 'Escolha o novo dia e horário. O paciente é copiado com todas as informações; a falta fica como “Reagendado”, registrado no histórico da linha como reagendado por quem fez.'
        : 'Escolha o novo dia e horário. Pergunta o dia e o horário do retorno (ex.: 2ª etapa do MIBI). O horário atual fica como “Retorno”, com o novo horário anotado, e o paciente aparece no outro dia.',
      data: somarDias(estado.data, 1), exame: a.exame, convenio: l.convenio, botaoOk: reagendado ? 'Reagendar para este horário' : 'Marcar retorno neste horário',
      aoConfirmar: (destino) => enviar(`/agenda/horario/${l.id}/${reagendado ? 'reagendar' : 'remarcar'}`, {destino}),
      sucesso: (r) => `Paciente ${reagendado ? 'reagendado' : 'com retorno marcado'} para ${r.quando}.`,
      extra: reagendado ? null : {rotulo: 'Só marcar como “Retorno”', acao: async () => {
        const r = await enviar(`/agenda/horario/${l.id}/status`, {status: 'RETORNO'});
        if (!r.ok) { mostrarErro(dlgHorario, r.erro || 'Não foi possível marcar.'); return; }
        dlgHorario.close();
        await recarregar();
      }}});
  }
  function abrirEncaixe(e) {
    escolherHorario({
      titulo: `Encaixar ${e.nome}`, texto: 'Escolha o dia e o horário livre para encaixar quem está na lista de espera.',
      data: estado.data, exame: e.exame, convenio: e.convenio, botaoOk: 'Encaixar neste horário',
      aoConfirmar: (destino) => enviar(`/agenda/espera/${e.id}/encaixar`, {destino}),
      sucesso: () => `${e.nome} foi encaixado(a) e saiu da lista de espera.`});
  }

  // ------------------------------------------------------------ lista de espera
  const blocoEspera = () => {
    const sec = el('section', 'ag-bloco ag-espera');
    const lista = estado.dia.espera;
    const topo = el('div', 'ag-bloco-topo');
    const tit = el('div', 'ag-bloco-tit');
    tit.append(el('h3', '', `Lista de espera (${lista.length})`), el('small', '', 'Pessoas aguardando uma vaga. “Encaixar” coloca a pessoa em um horário livre.'));
    topo.append(tit);
    const wrap = el('div', 'tabela-wrap ag-wrap');
    const t = el('table', 'ag-grade ag-grade-espera');
    const cab = el('thead');
    const trc = el('tr');
    ['Paciente', 'Exame', 'Convênio', 'Contato', 'Observação', 'Desde', ''].forEach((n) => trc.append(el('th', '', n)));
    cab.append(trc);
    const corpo = el('tbody');
    lista.forEach((e) => {
      const tr = el('tr', 'ag-linha');
      [e.nome, e.exame, e.convenio, e.contato, e.observacao, (e.criado_em || '').slice(0, 10) ? dataBR(e.criado_em.slice(0, 10)) : ''].forEach((v) => tr.append(el('td', 'ag-texto', v)));
      const td = el('td', 'ag-acoes-td');
      td.append(botao('Encaixar', 'btn peq', () => abrirEncaixe(e)),
        botao('✕', 'ag-ico ag-ico-perigo', async () => {
          if (!confirm(`Retirar ${e.nome} da lista de espera?`)) return;
          const r = await enviar(`/agenda/espera/${e.id}/excluir`, {});
          if (!r.ok) { aviso(r.erro || 'Não foi possível retirar.', 'erro'); return; }
          recarregar();
        }));
      tr.append(td);
      corpo.append(tr);
    });
    if (!lista.length) {
      const tr = el('tr');
      const td = el('td', 'vazio', 'Ninguém na lista de espera.');
      td.colSpan = 7;
      tr.append(td);
      corpo.append(tr);
    }
    t.append(cab, corpo);
    wrap.append(t);

    const form = el('form', 'ag-espera-form');
    const campos = {nome: 'Nome do paciente', exame: 'Exame', convenio: 'Convênio', contato: 'Contato', observacao: 'Observação'};
    Object.keys(campos).forEach((k) => {
      const i = el('input');
      i.type = 'text';
      i.name = k;
      i.placeholder = campos[k];
      i.maxLength = k === 'observacao' ? 300 : 120;
      i.setAttribute('aria-label', campos[k]);
      if (k === 'exame') i.setAttribute('list', 'ag-exames');
      form.append(i);
    });
    const alvo = estado.filtro !== 'todos' ? estado.dia.agendas.find((a) => String(a.id) === estado.filtro) : null;
    if (alvo) form.elements.namedItem('exame').value = alvo.exame;
    const enviarBtn = el('button', 'btn', 'Adicionar à espera');
    enviarBtn.type = 'submit';
    form.append(enviarBtn);
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const dados = {};
      new FormData(form).forEach((v, k) => { dados[k] = v; });
      const r = await enviar('/agenda/espera', dados);
      if (!r.ok) { aviso(r.erro || 'Não foi possível adicionar.', 'erro'); return; }
      await recarregar();
      aviso('Adicionado à lista de espera.', 'ok');
    });
    sec.append(topo, wrap, form);
    return sec;
  };

  // ------------------------------------------------------------ carregar e navegar
  function abrirRecortar(a, l) {
    if (!l.paciente.trim()) return;
    escolherHorario({
      titulo: `Recortar ${l.paciente} para outro dia`,
      texto: 'Escolha o dia e o horário livre. O paciente sai deste horário (que fica livre) e vai com todos os dados para o horário escolhido.',
      data: somarDias(estado.data, 1), exame: a.exame, convenio: l.convenio, botaoOk: 'Recortar para este horário',
      aoConfirmar: (destino) => enviar(`/agenda/horario/${l.id}/recortar`, {destino}),
      sucesso: (r) => `Paciente recortado para ${r.quando}. O horário anterior ficou livre.`});
  }

  function abrirCopiarLinha(a, l) {
    if (!l.paciente.trim()) return;
    escolherHorario({
      titulo: `Copiar ${l.paciente} para outro horário`,
      texto: 'Escolha o dia e o horário livre. A linha atual continua igual; a cópia entra no horário escolhido.',
      data: somarDias(estado.data, 1), exame: a.exame, convenio: l.convenio, botaoOk: 'Copiar para este horário',
      aoConfirmar: (destino) => enviar(`/agenda/horario/${l.id}/copiar_linha`, {destino}),
      sucesso: (r) => `Paciente copiado para ${r.quando}.`});
  }

  const editando = () => {
    if (document.querySelector('dialog[open]')) return true;
    const a = document.activeElement;
    return !!a && raiz.contains(a) && ['INPUT', 'SELECT', 'TEXTAREA'].includes(a.tagName);
  };
  async function carregarDia(forcar) {
    const alvo = estado.data;
    const d = await buscar('/agenda/dia/' + alvo, !forcar);
    if (alvo !== estado.data || d.data !== estado.data) return;
    const assinatura = JSON.stringify(d);
    if (!forcar && (assinatura === estado.assinatura || editando())) return;
    estado.dia = d;
    estado.assinatura = assinatura;
    renderDia(forcar && !!forcar);
    if (!forcar) carregarMarcas();
  }
  async function selecionar(iso) {
    estado.data = iso;
    estado.mes = iso.slice(0, 7);
    estado.filtro = 'todos';
    try { history.replaceState(null, '', '?data=' + iso); } catch (e) { /* ignorado */ }
    renderCalendario();
    try { await carregarDia(true); } catch (e) { aviso('Não foi possível carregar o dia. Tente novamente.', 'erro'); }
    carregarMarcas();
  }

  // ------------------------------------------------------------ formatação do texto (tamanho, negrito, itálico, sublinhado)
  // vale para a grade inteira e fica neste navegador (localStorage)
  const CHAVE_FMT = 'nucleleste.agendaTexto';
  const PADRAO_FMT = {tam: 15, neg: false, ita: false, sub: false, caixa: false};
  const principal = q('.ag-principal');
  let fmt = Object.assign({}, PADRAO_FMT);
  try { fmt = Object.assign(fmt, JSON.parse(localStorage.getItem(CHAVE_FMT)) || {}); } catch (e) { /* sem armazenamento */ }
  const aplicarFormato = () => {
    fmt.tam = Math.min(26, Math.max(10, Number(fmt.tam) || PADRAO_FMT.tam));
    principal.style.setProperty('--ag-fs', fmt.tam + 'px');
    ['neg', 'ita', 'sub', 'caixa'].forEach((k) => {
      principal.classList.toggle('ag-' + k, !!fmt[k]);
      const b = q(`[data-fmt="${k}"]`);
      if (b) b.setAttribute('aria-pressed', String(!!fmt[k]));
    });
    try { localStorage.setItem(CHAVE_FMT, JSON.stringify(fmt)); } catch (e) { /* vale só para esta tela */ }
  };
  document.querySelectorAll('[data-fmt]').forEach((b) => b.addEventListener('click', () => {
    const k = b.dataset.fmt;
    if (k === 'mais') fmt.tam += 1;
    else if (k === 'menos') fmt.tam -= 1;
    else if (k === 'limpar') fmt = Object.assign({}, PADRAO_FMT);
    else fmt[k] = !fmt[k];
    aplicarFormato();
  }));
  aplicarFormato();

  // coluna das ações (depois do status): mostrar ou ocultar quando for preciso
  const CHAVE_ACOES = 'nucleleste.agendaSemAcoes';
  const botaoAcoes = q('[data-colunas="acoes"]');
  const mostrarAcoes = (ocultas) => {
    principal.classList.toggle('ag-sem-acoes', ocultas);
    botaoAcoes.setAttribute('aria-pressed', String(!ocultas));
    botaoAcoes.textContent = ocultas ? 'Mostrar ações ▸' : 'Ocultar ações ◂';
    try { localStorage.setItem(CHAVE_ACOES, ocultas ? '1' : '0'); } catch (e) { /* vale só para esta tela */ }
    aplicarTodas();
  };
  botaoAcoes.addEventListener('click', () => mostrarAcoes(!principal.classList.contains('ag-sem-acoes')));
  q('[data-colunas="padrao"]').addEventListener('click', () => { larguras = null; salvarLarguras(); aplicarTodas(); });
  q('[data-colunas="fixar"]').addEventListener('click', () => {
    if (!larguras) { aviso('Nenhuma largura foi alterada: a agenda continua com a largura original.', 'aviso'); return; }
    salvarLarguras();
    aviso('Larguras das colunas guardadas como padrão: a agenda volta assim sempre que for aberta.', 'ok');
  });
  let acoesOcultas = false;
  try { acoesOcultas = localStorage.getItem(CHAVE_ACOES) === '1'; } catch (e) { /* sem armazenamento */ }
  mostrarAcoes(acoesOcultas);

  // coluna da idade (depois do paciente): mostrar ou ocultar; padrão visível
  const CHAVE_IDADE = 'nucleleste.agendaSemIdade';
  const botaoIdade = q('[data-colunas="idade"]');
  const mostrarIdade = (ocultas) => {
    principal.classList.toggle('ag-sem-idade', ocultas);
    botaoIdade.setAttribute('aria-pressed', String(!ocultas));
    botaoIdade.textContent = ocultas ? 'Mostrar idade' : 'Ocultar idade';
    try { localStorage.setItem(CHAVE_IDADE, ocultas ? '1' : '0'); } catch (e) { /* vale só para esta tela */ }
    aplicarTodas();
  };
  botaoIdade.addEventListener('click', () => mostrarIdade(!principal.classList.contains('ag-sem-idade')));
  let idadeOculta = false;
  try { idadeOculta = localStorage.getItem(CHAVE_IDADE) === '1'; } catch (e) { /* sem armazenamento */ }
  mostrarIdade(idadeOculta);

  // aba "Reservar horários para um convênio" (no criar agenda): abre, aumenta a janela e mostra os campos da reserva
  const abaReserva = q('#c-reserva-aba'), corpoReserva = q('#c-reserva-corpo'), ativaReserva = q('#c-reserva-ativa');
  const previaReserva = q('#r-previa');
  const horasDaAgenda = () => {
    const ini = emMinutos(campoCriar('inicio').value), inter = Number(campoCriar('intervalo').value), qtd = Number(campoCriar('qtd').value) || 0;
    if (ini === null || !(inter > 0)) return [];
    const n = qtd || (emMinutos(campoCriar('fim').value) !== null ? Math.floor((emMinutos(campoCriar('fim').value) - ini) / inter) : 0);
    return Array.from({length: Math.max(0, n)}, (_, k) => deMinutos(ini + k * inter)).filter((h) => !h.startsWith('24'));
  };
  const atualizarPrevia = () => {
    if (corpoReserva.hidden) return;
    const de = q('#r-inicio').value || campoCriar('inicio').value;
    const passo = Math.max(1, Number(q('#r-passo').value) || 1), qtd = Math.max(0, Number(q('#r-qtd').value) || 0);
    const todas = horasDaAgenda().filter((h) => h >= de);
    const escolhidas = todas.filter((_, k) => k % passo === 0).slice(0, qtd);
    previaReserva.textContent = escolhidas.length
      ? `Reservará ${escolhidas.length} horário(s): ${escolhidas.slice(0, 14).join(', ')}${escolhidas.length > 14 ? '…' : ''}`
      : 'Preencha o horário, o intervalo e a quantidade da agenda para ver os horários que serão reservados.';
  };
  const alternarReserva = (abrir) => {
    corpoReserva.hidden = !abrir;
    ativaReserva.value = abrir ? '1' : '';
    abaReserva.setAttribute('aria-expanded', String(abrir));
    abaReserva.classList.toggle('aberta', abrir);
    dlgCriar.classList.toggle('ag-largo', abrir);   // a janela de criar agenda aumenta
    if (abrir) {
      const sel = q('#r-convenio');
      if (!sel.options.length) (estado.dia.convenios || []).forEach((nome) => sel.append(Object.assign(el('option', '', nome), {value: nome})));
      if (!q('#r-inicio').value) q('#r-inicio').value = campoCriar('inicio').value;
      atualizarPrevia();
    }
  };
  abaReserva.addEventListener('click', () => alternarReserva(corpoReserva.hidden));
  ['inicio', 'intervalo', 'qtd', 'fim'].forEach((n) => campoCriar(n).addEventListener('input', atualizarPrevia));
  ['#r-inicio', '#r-qtd', '#r-passo'].forEach((sel) => q(sel).addEventListener('input', atualizarPrevia));

  // menu das áreas: os links mantêm as permissões e os destinos das abas do módulo
  const areas = q('#ag-areas'), botaoAreas = q('#ag-areas-botao'), opcoesAreas = q('#ag-areas-opcoes');
  if (areas) {
    const itens = [...opcoesAreas.querySelectorAll('[role="menuitem"]')];
    const fecharAreas = (focar) => {
      opcoesAreas.hidden = true;
      botaoAreas.setAttribute('aria-expanded', 'false');
      if (focar) botaoAreas.focus();
    };
    const abrirAreas = (ultimo) => {
      opcoesAreas.hidden = false;
      botaoAreas.setAttribute('aria-expanded', 'true');
      (ultimo ? itens[itens.length - 1] : itens[0])?.focus();
    };
    botaoAreas.addEventListener('click', () => { if (opcoesAreas.hidden) abrirAreas(false); else fecharAreas(false); });
    botaoAreas.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); e.stopPropagation(); abrirAreas(e.key === 'ArrowUp'); }
    });
    areas.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); fecharAreas(true); return; }
      if (opcoesAreas.hidden) return;
      const i = itens.indexOf(document.activeElement);
      let destino;
      if (e.key === 'ArrowDown') destino = (i + 1) % itens.length;
      else if (e.key === 'ArrowUp') destino = (i - 1 + itens.length) % itens.length;
      else if (e.key === 'Home') destino = 0;
      else if (e.key === 'End') destino = itens.length - 1;
      if (destino !== undefined) { e.preventDefault(); itens[destino]?.focus(); }
      if (e.key === ' ' && i >= 0) { e.preventDefault(); itens[i].click(); }
    });
    document.addEventListener('click', (e) => { if (!areas.contains(e.target)) fecharAreas(false); });
    areas.addEventListener('focusout', (e) => { if (!areas.contains(e.relatedTarget)) fecharAreas(false); });
  }

  // a barra começa recolhida; a preferência fica apenas neste navegador
  const botaoFormato = q('#ag-formato-alternar'), barraFormato = q('#ag-formato');
  const CHAVE_BARRA_FMT = 'nucleleste.agendaFormatoVisivel';
  const mostrarFormato = (mostrar) => {
    barraFormato.hidden = !mostrar;
    botaoFormato.setAttribute('aria-expanded', String(mostrar));
    botaoFormato.querySelector('span').textContent = mostrar ? 'Ocultar formatação' : 'Mostrar formatação';
  };
  let formatoVisivel = false;
  try { formatoVisivel = localStorage.getItem(CHAVE_BARRA_FMT) === '1'; } catch (e) { /* sem armazenamento */ }
  mostrarFormato(formatoVisivel);
  botaoFormato.addEventListener('click', () => {
    mostrarFormato(barraFormato.hidden);
    try { localStorage.setItem(CHAVE_BARRA_FMT, barraFormato.hidden ? '0' : '1'); } catch (e) { /* vale só para esta tela */ }
  });

  // no computador, a agenda ocupa a altura restante; a rolagem fica dentro dos painéis
  const ajustarAltura = () => {
    raiz.style.setProperty('--ag-altura', Math.max(260, window.innerHeight - raiz.getBoundingClientRect().top - 12) + 'px');
  };
  window.addEventListener('resize', ajustarAltura);
  if ('ResizeObserver' in window) new ResizeObserver(ajustarAltura).observe(q('.ag-controles').parentElement);

  renderCalendario();
  renderDia(true);
  ajustarAltura();
  carregarMarcas();
  setInterval(() => { if (!document.hidden) carregarDia(false).catch(() => {}); }, 5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) carregarDia(false).catch(() => {}); });
})();


// vindo do aviso de duplicidade: destaca e rola até as linhas do caso
(() => {
  let ids = [];
  try { ids = JSON.parse(document.getElementById('ag-destacar').textContent) || []; } catch (e) { return; }
  if (!ids.length) return;
  let tentativas = 0;
  const t = setInterval(() => {
    const trs = ids.map((i) => document.querySelector(`tr[data-id="${i}"]`)).filter(Boolean);
    if (trs.length || ++tentativas > 20) {
      clearInterval(t);
      trs.forEach((x) => x.classList.add('ag-destaque-dup'));
      if (trs[0]) trs[0].scrollIntoView({behavior: 'smooth', block: 'center'});
    }
  }, 300);
})();
