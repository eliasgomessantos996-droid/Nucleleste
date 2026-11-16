'use strict';
/* Mensagens ao vivo e avisos em qualquer tela.
   O servidor não mantém conexões abertas: o navegador faz consultas curtas e frequentes (cabeçalho X-Passivo). Mensagens ficam gravadas no banco até serem lidas,
   então quem estava ausente as vê ao abrir o sistema. */
(() => {
  const corpo = document.body;
  const url = corpo.dataset.chatUrl;
  if (!url) return;

  const pagina = document.querySelector('[data-chat-pagina]');
  const fio = document.getElementById('chat-fio');
  const form = document.getElementById('chat-form');
  const estado = document.querySelector('[data-chat-estado]');
  const lista = document.querySelector('[data-chat-contatos]');
  const filtro = document.querySelector('[data-chat-filtro]');
  const csrf = (document.querySelector('meta[name=csrf]') || {}).content || '';
  const tituloBase = document.title;
  const com = pagina ? pagina.dataset.com : '';
  const normalizar = (v) => v.normalize('NFD').replace(/[̀-ͯ]/g, '').toLocaleLowerCase('pt-BR');

  let ultimo = Number(corpo.dataset.chatUltimo || 0);          // última mensagem recebida já conhecida (avisos)
  let depoisConv = pagina ? Number(pagina.dataset.ultimo || 0) : 0; // última mensagem da conversa aberta
  let primeiro = pagina ? Number(pagina.dataset.primeiro || 0) : 0;
  let falhas = 0, timer = null, parado = false, piscando = null;
  const exibidas = new Set();
  const chaveResumo = 'nl_chat_resumo_' + csrf.slice(0, 16);
  let resumoPendente = false;
  try { resumoPendente = !sessionStorage.getItem(chaveResumo); } catch (e) { resumoPendente = false; }

  // ------------------------------------------------------------ utilidades
  const dataLocal = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const rotuloDia = (iso) => {
    const hoje = new Date();
    const ontem = new Date(hoje.getTime() - 86400000);
    if (iso === dataLocal(hoje)) return 'Hoje';
    if (iso === dataLocal(ontem)) return 'Ontem';
    return `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  };
  const el = (tag, classe, texto) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined) e.textContent = texto;
    return e;
  };

  const definirEstado = (texto, ok) => {
    if (!estado) return;
    estado.textContent = texto;
    estado.classList.toggle('desligado', !ok);
  };
  const definirNaoLidas = (n) => {
    document.querySelectorAll('[data-msg-badge]').forEach((b) => {
      const mudou = b.textContent !== String(n);
      b.textContent = n;
      b.hidden = !n;
      if (mudou && n) { b.classList.remove('pulsa'); void b.offsetWidth; b.classList.add('pulsa'); }
    });
    if (!piscando) document.title = n ? `(${n}) ${tituloBase}` : tituloBase;
  };

  // ------------------------------------------------------------ presença (online/offline em qualquer tela)
  // Cada página aberta é uma "aba": bate no servidor a cada 20 s. Ao sair (fechar, trocar de página ou sair do sistema)
  // avisa na hora, pelo sendBeacon; o servidor tira a aba da lista de online sem esperar o prazo de 90 s.
  const aba = Math.random().toString(36).slice(2, 12) + Date.now().toString(36).slice(-4);
  let mapaPresenca = {};
  const textoStatus = (s) => (s.online ? '● online' : '● offline' + (s.visto ? ' · visto por último ' + s.visto : ''));
  const aplicarPresenca = (mapa) => {
    if (!mapa) return;
    mapaPresenca = mapa;
    document.querySelectorAll('[data-presenca]').forEach((e) => {
      const s = mapa[e.dataset.presenca];
      if (!s) return;
      e.classList.toggle('online', s.online);
      e.title = s.online ? 'Online' : 'Offline · visto por último ' + s.visto;
    });
    document.querySelectorAll('[data-presenca-texto]').forEach((e) => {
      const s = mapa[e.dataset.presencaTexto];
      if (s) e.textContent = s.online ? 'Online agora' : 'Offline';
    });
    if (estado && com && mapa[com]) {
      estado.textContent = textoStatus(mapa[com]);
      estado.classList.toggle('online', mapa[com].online);
      estado.classList.remove('desligado');
    }
  };
  const bater = async () => {
    try {
      const r = await fetch('/sessao/batida', {method: 'POST', credentials: 'same-origin',
        headers: {Accept: 'application/json', 'X-CSRF-Token': csrf, 'X-Passivo': '1'}, body: new URLSearchParams({aba})});
      if (window.nuclelesteSessao && window.nuclelesteSessao(r)) { clearInterval(pulso); parar(); }
    } catch (e) { /* sem rede: tenta de novo na próxima batida */ }
  };
  const pulso = setInterval(bater, 20000);
  bater();
  window.addEventListener('pagehide', () => {
    const dados = new FormData();
    dados.append('_csrf', csrf);
    dados.append('aba', aba);
    try { navigator.sendBeacon('/sessao/saida', dados); } catch (e) { /* ignorado */ }
  });

  // ------------------------------------------------------------ avisos (toast, som, notificação do navegador)
  let contexto = null;
  const bipe = () => {
    try {
      contexto = contexto || new (window.AudioContext || window.webkitAudioContext)();
      const o = contexto.createOscillator(), g = contexto.createGain();
      o.type = 'sine'; o.frequency.setValueAtTime(880, contexto.currentTime);
      o.frequency.exponentialRampToValueAtTime(1320, contexto.currentTime + 0.12);
      g.gain.setValueAtTime(0.0001, contexto.currentTime);
      g.gain.exponentialRampToValueAtTime(0.12, contexto.currentTime + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, contexto.currentTime + 0.32);
      o.connect(g); g.connect(contexto.destination); o.start(); o.stop(contexto.currentTime + 0.35);
    } catch (e) { /* o navegador pode bloquear som antes de qualquer clique */ }
  };
  const piscarTitulo = (texto) => {
    if (!document.hidden) return;
    clearInterval(piscando);
    let alterna = false;
    piscando = setInterval(() => {
      document.title = alterna ? tituloBase : `💬 ${texto}`;
      alterna = !alterna;
    }, 1000);
  };
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { clearInterval(piscando); piscando = null; document.title = tituloBase; consultarJa(); }
  });
  window.addEventListener('focus', () => { clearInterval(piscando); piscando = null; });

  let caixaToasts = null;
  const aviso = ({titulo, texto, href, id}) => {
    if (!caixaToasts) {
      caixaToasts = el('div', 'chat-toasts');
      caixaToasts.setAttribute('aria-live', 'polite');
      document.body.appendChild(caixaToasts);
    }
    const t = el('a', 'chat-toast');
    t.href = href;
    const avatar = el('span', 'chat-toast-icone', '💬');
    const bloco = el('span', 'chat-toast-texto');
    bloco.append(el('strong', '', titulo), el('small', '', texto));
    const fechar = el('button', 'chat-toast-fechar', '×');
    fechar.type = 'button';
    fechar.setAttribute('aria-label', 'Fechar aviso');
    fechar.addEventListener('click', (ev) => { ev.preventDefault(); ev.stopPropagation(); sair(); });
    t.append(avatar, bloco, fechar);
    const sair = () => { t.classList.add('saindo'); setTimeout(() => t.remove(), 350); };
    caixaToasts.appendChild(t);
    while (caixaToasts.children.length > 4) caixaToasts.firstElementChild.remove();
    setTimeout(sair, 9000);
    bipe();
    piscarTitulo(titulo);
    if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
      try {
        const n = new Notification(titulo, {body: texto, tag: id ? 'chat-' + id : undefined});
        n.onclick = () => { window.focus(); location.href = href; n.close(); };
      } catch (e) { /* ignorado */ }
    }
  };

  const botaoNotificar = document.querySelector('[data-chat-notificar]');
  if (botaoNotificar && 'Notification' in window && window.isSecureContext && Notification.permission === 'default') {
    botaoNotificar.hidden = false;
    botaoNotificar.addEventListener('click', () => Notification.requestPermission().then(() => { botaoNotificar.hidden = true; }));
  }

  // ------------------------------------------------------------ tela de conversa
  let diaAtual = '';
  const somenteLeitura = !!pagina && pagina.dataset.leitura === '1';   // contatos do sistema: não se responde nem se cita
  const nomeParceiro = pagina ? (pagina.dataset.nome || '') : '';
  let definirResposta = () => {};                                       // ligado dentro da tela de conversa
  let respondendo = null;                                               // mensagem que está sendo respondida: {id, corpo}
  const formAcao = (acao, rotulo, classe, campos) => {
    const f = el('form', 'chat-laudo-acao');
    f.method = 'POST';
    f.action = acao;
    const t = el('input'); t.type = 'hidden'; t.name = '_csrf'; t.value = csrf;
    f.append(t);
    campos.forEach(([nome, valor, texto, cls]) => {
      const bt = el('button', cls || classe, texto || rotulo);
      bt.type = 'submit';
      if (nome) { bt.name = nome; bt.value = valor; }
      f.append(bt);
    });
    return f;
  };
  // Cartão especial do sistema (cápsulas): só o servidor cria; o texto de uma mensagem comum nunca vira cartão, então não dá para imitar.
  const NS_SVG = 'http://www.w3.org/2000/svg';
  const iconeSvg = (nome, tam) => {
    const s = document.createElementNS(NS_SVG, 'svg');
    s.setAttribute('class', 'ic'); s.setAttribute('width', tam || 14); s.setAttribute('height', tam || 14); s.setAttribute('aria-hidden', 'true');
    const u = document.createElementNS(NS_SVG, 'use');
    u.setAttribute('href', '/static/img/icones.svg#i-' + nome);
    s.append(u);
    return s;
  };
  const capsula = (icone, rotulo, valor, cls) => {
    const c = el('span', 'cc-cap' + (cls ? ' ' + cls : ''));
    if (icone) c.append(iconeSvg(icone));
    if (rotulo) c.append(el('small', '', rotulo));
    c.append(el('b', '', valor));
    return c;
  };
  const dataBr = (t) => t ? `${t.slice(8, 10)}/${t.slice(5, 7)}/${t.slice(0, 4)} às ${t.slice(11, 16)}` : '';
  const cartaoSistema = (c) => {
    const card = el('div', 'chat-cartao-sis');
    const topo = el('div', 'cc-topo');
    const selo = el('span', 'cc-selo');
    selo.append(iconeSvg('shield-check', 16), el('b', '', 'Mensagem automática do sistema'));
    topo.append(selo, capsula('circle-x', '', 'NÃO ACEITA', 'nao'));
    card.append(topo);
    card.append(el('p', 'cc-intro', `Sua ${c.item_tipo.toLowerCase()} abaixo não foi aceita pelo desenvolvedor.`));
    const linha = el('div', 'cc-linha');
    linha.append(capsula(c.item_tipo === 'Correção de bug' ? 'bug' : 'lightbulb', 'Tipo', c.item_tipo), capsula('layout-grid', 'Tema', c.tema),
                 capsula('user-round', 'Enviada por', c.autor), capsula('clock', 'Em', dataBr(c.enviado_em)));
    if (c.tela) linha.append(capsula('file-text', 'Tela', c.tela));
    card.append(linha);
    card.append(el('div', 'cc-titulo', c.titulo));
    const cit = el('blockquote', 'cc-citacao');
    cit.append(el('span', 'cc-aspas', '“'), el('p', '', c.citacao), el('span', 'cc-aspas fim', '”'));
    card.append(cit);
    const pe = el('div', 'cc-linha cc-pe');
    pe.append(capsula('badge-check', 'Decidido por', c.decidido_por), capsula('clock', 'Em', dataBr(c.decidido_em)), capsula('', 'Ref.', '#' + c.item_id));
    card.append(pe);
    card.append(el('p', 'cc-nota', 'O desenvolvedor vai explicar o motivo nas mensagens abaixo.'));
    return card;
  };
  const balao = (m) => {
    const linha = el('div', m.minha ? 'chat-msg minha' : 'chat-msg dele');
    linha.dataset.id = m.id;
    const b = el('div', 'chat-balao');
    if (m.responde) {
      // citação da mensagem respondida; o clique leva até ela
      const q = el('button', 'chat-citacao');
      q.type = 'button';
      q.append(el('strong', '', m.responde.minha ? 'Você' : (nomeParceiro || 'Mensagem')), el('span', '', m.responde.corpo));
      q.addEventListener('click', () => irPara(m.responde.id));
      b.append(q);
    }
    if (m.imagem) {
      // imagem enviada pelo chat: abre em tamanho real numa aba; some 24 h depois do envio
      const a = el('a', 'chat-img');
      a.href = m.imagem;
      a.target = '_blank';
      a.rel = 'noopener';
      const img = el('img');
      img.src = m.imagem;
      img.alt = 'Imagem enviada';
      img.loading = 'lazy';
      img.addEventListener('load', () => { if (fio && Math.abs(fio.scrollHeight - fio.scrollTop - fio.clientHeight) < 400) fio.scrollTop = fio.scrollHeight; });
      a.append(img);
      b.append(a);
      b.append(el('small', 'chat-img-aviso', m.imagem_expira ? 'Imagem disponível até ' + m.imagem_expira + ' de amanhã' : 'Imagem disponível por 24 horas'));
    } else if (m.imagem_apagada) {
      b.append(el('div', 'chat-img-apagada', '🖼 Imagem apagada (o prazo de 24 horas acabou)'));
    }
    if (m.arquivo) {
      b.append(el('div', 'chat-arquivo-badge', '📎 ' + (m.arquivo.nome || 'Arquivo')));
    }
    if (m.cartao && m.cartao.tipo === 'SUPORTE_RECUSA') b.append(cartaoSistema(m.cartao));
    else if (m.cartao && !m.minha && window.NucleaiCartoes && window.NucleaiCartoes.suporta(m.cartao)) {
      // resultado visual da NucleAI IA (ilustração fora do balão comum, ou cartão padrão)
      b.classList.add(m.cartao.tipo === 'IA_ILUSTRACAO' ? 'chat-balao-ilustrar' : 'chat-balao-ia');
      b.append(window.NucleaiCartoes.render(m.cartao));
    }
    else if (!m.so_imagem) {
      // só as mensagens da NucleAI são formatadas (**negrito**, listas...); o que as pessoas digitam continua texto puro
      if (m.ia && window.NucleaiFormatar) b.append(window.NucleaiFormatar.render(m.corpo));
      else b.append(el('div', 'chat-texto', m.corpo));
    }
    if (m.acao === 'CHAMADO_FALAR' && !m.minha && m.chamado_id) {
      // pedido de ajuda enviado pela NucleAI: abre a conversa com o usuário, com a pergunta pronta
      b.append(formAcao(`/ajuda/chamado/${m.chamado_id}/contatar`, '💬 Falar com o usuário', 'chat-laudo-botao zap', [[null, null]]));
    }
    if (m.acao === 'CHAMADO_CONFIRMA' && m.chamado_id) {
      if (m.acao_resp) {
        b.append(el('div', 'chat-acao-resp', m.acao_resp === 'SIM' ? '✔ Confirmado: é essa a dúvida' : '✖ Respondido: não é essa a dúvida'));
      } else if (!m.minha) {
        b.append(formAcao(`/ajuda/chamado/${m.chamado_id}/confirmar`, '', 'chat-laudo-botao', [
          ['resposta', 'SIM', '✔ Sim, é isso', 'chat-laudo-botao'], ['resposta', 'NAO', '✖ Não, é outra coisa', 'chat-laudo-botao nao']]));
      }
    }
    if ((m.acao === 'CMD_CONFIRMA' || m.acao === 'CMD_CONFIRMA_ABRE') && m.chamado_id) {
      // pedido da NucleAI que espera Sim ou Não (também dá para responder escrevendo)
      if (m.acao_resp) {
        b.append(el('div', 'chat-acao-resp', m.acao_resp === 'SIM' ? '✔ Você permitiu' : '✖ Você negou'));
      } else if (!m.minha) {
        const linhaBotoes = el('div', 'chat-laudo-acao');
        const forma = (resposta, rotulo, classe, novaAba) => {
          const f = formAcao(`/ajuda/comando/${m.chamado_id}/responder`, '', classe, [['resposta', resposta, rotulo, classe]]);
          if (novaAba) f.target = '_blank';   // Sim com tela para abrir: abre em outra aba e o chat continua aqui
          f.addEventListener('submit', () => { setTimeout(() => { linhaBotoes.replaceChildren(el('div', 'chat-acao-resp', resposta === 'SIM' ? '✔ Você permitiu' : '✖ Você negou')); }, 60); });
          return f;
        };
        linhaBotoes.append(forma('SIM', '✔ Sim, pode fazer', 'chat-laudo-botao', m.acao === 'CMD_CONFIRMA_ABRE'), forma('NAO', '✖ Não', 'chat-laudo-botao nao', false));
        b.append(linhaBotoes);
      }
    }
    if ((m.acao === 'AVALIACAO_VER' || m.acao === 'AGENDA_VER') && m.acao_url && !m.minha) {
      const ROT = m.acao === 'AGENDA_VER'
        ? {sim: '✔ Sim, abrir a agenda', ja: '✔ Agenda aberta', nao: '✖ Não abriu a agenda agora'}
        : {sim: '✔ Sim, abrir a avaliação', ja: '✔ Avaliação aberta', nao: '✖ Não abriu a avaliação agora'};
      // aviso de nova avaliação da pesquisa: Sim abre a avaliação; Não só fecha a pergunta
      const linha = el('div', 'chat-laudo-acao');
      const responder = (resposta) => {
        const dados = new URLSearchParams({resposta});
        return fetch(`/mensagens/${m.id}/acao`, {method: 'POST', credentials: 'same-origin', body: dados,
          headers: {Accept: 'application/json', 'X-CSRF-Token': csrf}}).then((r) => (r.ok ? r.json() : null));
      };
      if (m.acao_resp) {
        linha.append(el('div', 'chat-acao-resp', m.acao_resp === 'SIM' ? ROT.ja : ROT.nao));
      } else {
        const sim = el('button', 'chat-laudo-botao', ROT.sim);
        sim.type = 'button';
        sim.addEventListener('click', async () => {
          const r = await responder('SIM');
          if (r && r.url) window.location.href = r.url;
        });
        const nao = el('button', 'chat-laudo-botao nao', '✖ Não');
        nao.type = 'button';
        nao.addEventListener('click', async () => {
          await responder('NAO');
          linha.replaceChildren(el('div', 'chat-acao-resp', ROT.nao));
        });
        linha.append(sim, nao);
      }
      b.append(linha);
    }
    if (m.acao === 'CMD_ABRIR' && m.acao_resp && /^\/(?!\/)/.test(m.acao_resp)) {
      const a = el('a', 'chat-laudo-botao zap', '↗ Abrir agora');
      a.href = m.acao_resp;
      a.target = '_blank';
      a.rel = 'noopener';
      b.append(a);
    }
    if (m.laudo_id && !m.minha) {
      // aviso de laudo liberado: um clique marca como entregue e leva ao laudo no mapa
      const f = el('form', 'chat-laudo-acao');
      f.method = 'POST';
      f.action = `/laudos/${m.laudo_id}/entregar`;
      const t = el('input'); t.type = 'hidden'; t.name = '_csrf'; t.value = csrf;
      const bt = el('button', 'chat-laudo-botao', '✔ Marcar como entregue e ver no mapa');
      bt.type = 'submit';
      f.append(t, bt);
      b.append(f);
    }
    const rodape = el('div', 'chat-rodape');
    if (!somenteLeitura && form) {
      const resp = el('button', 'chat-responder', '↩');
      resp.type = 'button';
      resp.title = 'Responder a esta mensagem';
      resp.setAttribute('aria-label', 'Responder a esta mensagem');
      resp.addEventListener('click', () => definirResposta(m));
      rodape.append(resp);
    }
    rodape.append(el('time', '', m.hora));
    if (m.minha) {
      const tick = el('span', m.lida ? 'chat-tick lida' : 'chat-tick', m.lida ? '✓✓' : '✓');
      tick.title = m.lida ? 'Lida' : 'Enviada';
      rodape.append(tick);
    }
    b.append(rodape);
    linha.append(b);
    return linha;
  };
  const acrescentar = (m, rolar) => {
    if (!fio || exibidas.has(m.id)) return;
    exibidas.add(m.id);
    depoisConv = Math.max(depoisConv, m.id);
    if (!primeiro) primeiro = m.id;
    const perto = fio.scrollHeight - fio.scrollTop - fio.clientHeight < 140;
    fio.querySelectorAll('.chat-vazio').forEach((n) => n.remove());
    if (m.dia && m.dia !== diaAtual) {
      diaAtual = m.dia;
      fio.append(el('div', 'chat-dia', rotuloDia(m.dia)));
    }
    fio.append(balao(m));
    if (rolar || perto || m.minha) fio.scrollTop = fio.scrollHeight;
  };
  // leva até uma mensagem da conversa (se estiver carregada) e a destaca; devolve false se ela não estiver na tela
  const irPara = (id) => {
    const alvo = fio && fio.querySelector(`.chat-msg[data-id="${id}"]`);
    if (!alvo) return false;
    alvo.scrollIntoView({behavior: 'smooth', block: 'center'});
    alvo.classList.remove('achada');
    void alvo.offsetWidth;
    alvo.classList.add('achada');
    return true;
  };
  const marcarLidas = (ids) => {
    if (!fio) return;
    ids.forEach((id) => {
      const t = fio.querySelector(`.chat-msg[data-id="${id}"] .chat-tick:not(.lida)`);
      if (t) { t.textContent = '✓✓'; t.classList.add('lida'); t.title = 'Lida'; }
    });
  };

  if (fio) {
    let iniciais = [];
    try { iniciais = JSON.parse(document.getElementById('chat-inicial').textContent); } catch (e) { iniciais = []; }
    iniciais.forEach((m) => acrescentar(m, true));
    if (!iniciais.length) fio.append(el('p', 'chat-vazio', 'Nenhuma mensagem ainda. Escreva a primeira abaixo.'));
    fio.scrollTop = fio.scrollHeight;
    const texto = form.elements.namedItem('corpo');
    texto.focus({preventScroll: true});
    const crescer = () => { texto.style.height = 'auto'; texto.style.height = Math.min(140, texto.scrollHeight) + 'px'; };
    texto.addEventListener('input', crescer);

    // ---- "digitando…": avisa a outra pessoa (no máximo a cada 3 s enquanto escreve)
    let ultimoAviso = 0;
    texto.addEventListener('input', () => {
      if (!texto.value.trim() || somenteLeitura || !com || Date.now() - ultimoAviso < 3000) return;
      ultimoAviso = Date.now();
      fetch('/mensagens/digitando', {method: 'POST', credentials: 'same-origin', body: new URLSearchParams({para: com}),
        headers: {'X-CSRF-Token': csrf, 'X-Passivo': '1'}}).catch(() => { /* ignorado */ });
    });

    // ---- responder a uma mensagem (citação)
    const barraResp = document.getElementById('chat-resposta');
    const textoResp = barraResp ? barraResp.querySelector('[data-resp-texto]') : null;
    const fecharResposta = () => { respondendo = null; if (barraResp) barraResp.hidden = true; };
    definirResposta = (m) => {
      if (!barraResp) return;
      respondendo = {id: m.id, corpo: m.corpo};
      textoResp.textContent = (m.minha ? 'Você: ' : (nomeParceiro ? nomeParceiro + ': ' : '')) + m.corpo.replace(/\s+/g, ' ').slice(0, 120);
      barraResp.hidden = false;
      texto.focus();
    };
    if (barraResp) barraResp.querySelector('[data-resp-fechar]').addEventListener('click', fecharResposta);

    // ---- imagem (outros usuários) ou arquivo .xlsx/.xls/.csv/.txt (NucleAI)
    const ehNucleai = form.dataset.nucleai === '1';
    const LIMITE_IMG = 5 * 1024 * 1024;
    const TIPOS_IMG = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
    const EXTS_ARQ = ['.xlsx', '.xls', '.csv', '.txt'];
    const entradaImg = document.getElementById('chat-img');
    const botaoImg = document.getElementById('chat-anexar');
    const previa = document.getElementById('chat-img-previa');
    let imagemEscolhida = null;
    let urlPrevia = '';
    const tirarImagem = () => {
      imagemEscolhida = null;
      if (urlPrevia) URL.revokeObjectURL(urlPrevia);
      urlPrevia = '';
      if (previa) previa.hidden = true;
      if (entradaImg) entradaImg.value = '';
    };
    const usarImagem = (arq) => {
      const erroImg = form.querySelector('[data-chat-erro]');
      if (!arq) return;
      if (ehNucleai) {
        const nomeLower = (arq.name || '').toLowerCase();
        if (!EXTS_ARQ.some((ext) => nomeLower.endsWith(ext))) {
          erroImg.textContent = 'Envie um arquivo .xlsx, .xls, .csv ou .txt.';
          erroImg.hidden = false;
          return;
        }
        if (arq.size > LIMITE_IMG) { erroImg.textContent = 'O arquivo pode ter no máximo 5 MB.'; erroImg.hidden = false; return; }
        erroImg.hidden = true;
        tirarImagem();
        imagemEscolhida = arq;
        const rotulo = previa.querySelector('[data-arq-nome]');
        if (rotulo) rotulo.textContent = '📎 ' + arq.name + ' (apagado com a conversa)';
        previa.hidden = false;
        texto.focus();
        return;
      }
      if (!TIPOS_IMG.includes(arq.type)) { erroImg.textContent = 'Envie uma imagem JPG, PNG, GIF ou WebP.'; erroImg.hidden = false; return; }
      if (arq.size > LIMITE_IMG) { erroImg.textContent = 'A imagem pode ter no máximo 5 MB.'; erroImg.hidden = false; return; }
      erroImg.hidden = true;
      tirarImagem();
      imagemEscolhida = arq;
      urlPrevia = URL.createObjectURL(arq);
      previa.querySelector('img').src = urlPrevia;
      previa.hidden = false;
      texto.focus();
    };
    if (botaoImg && entradaImg && !somenteLeitura) {
      botaoImg.addEventListener('click', () => entradaImg.click());
      entradaImg.addEventListener('change', () => usarImagem(entradaImg.files[0]));
      previa.querySelector('[data-img-remover]').addEventListener('click', tirarImagem);
      if (!ehNucleai) {
        texto.addEventListener('paste', (ev) => {
          const item = [...(ev.clipboardData ? ev.clipboardData.items : [])].find((i) => i.kind === 'file' && i.type.startsWith('image/'));
          if (!item) return;
          ev.preventDefault();
          const arq = item.getAsFile();
          usarImagem(arq ? new File([arq], 'imagem-colada.' + (arq.type.split('/')[1] || 'png'), {type: arq.type}) : null);
        });
      }
    } else if (botaoImg) {
      botaoImg.hidden = true;
    }
    texto.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') fecharResposta(); });

    // ---- pesquisar dentro da conversa
    const abrirBusca = document.querySelector('[data-chat-buscar-abrir]');
    const painelBusca = document.getElementById('chat-busca-conv');
    if (abrirBusca && painelBusca) {
      const campoBusca = painelBusca.querySelector('input');
      const resultados = painelBusca.querySelector('[data-busca-resultados]');
      let esperaBusca = null;
      const destacar = (t, termo) => {
        const frag = document.createDocumentFragment();
        const alvo = normalizar(termo);
        const base = normalizar(t);
        let i = 0, j;
        while (alvo && (j = base.indexOf(alvo, i)) !== -1) {
          frag.append(t.slice(i, j));
          frag.append(el('mark', '', t.slice(j, j + alvo.length)));
          i = j + alvo.length;
        }
        frag.append(t.slice(i));
        return frag;
      };
      const buscar = async () => {
        const termo = campoBusca.value.trim();
        resultados.replaceChildren();
        if (normalizar(termo).length < 2) { resultados.append(el('p', 'chat-busca-aviso', 'Digite pelo menos 2 letras.')); return; }
        try {
          const r = await fetch(`/mensagens/buscar?com=${encodeURIComponent(com)}&q=${encodeURIComponent(termo)}`,
            {credentials: 'same-origin', headers: {Accept: 'application/json', 'X-Passivo': '1'}});
          const d = await r.json();
          if (!d.resultados.length) { resultados.append(el('p', 'chat-busca-aviso', 'Nenhuma mensagem encontrada.')); return; }
          resultados.append(el('p', 'chat-busca-aviso', d.resultados.length + (d.resultados.length >= d.limite ? '+' : '') + ' mensagem(ns). Toque para ir até ela.'));
          d.resultados.forEach((m) => {
            const item = el('button', 'chat-busca-item');
            item.type = 'button';
            const cab = el('small', '', `${m.minha ? 'Você' : (nomeParceiro || 'Mensagem')} · ${m.dia.slice(8, 10)}/${m.dia.slice(5, 7)}/${m.dia.slice(0, 4)} ${m.hora}`);
            const corpoItem = el('span', 'chat-busca-texto');
            corpoItem.append(destacar(m.corpo.replace(/\s+/g, ' ').slice(0, 200), termo));
            item.append(cab, corpoItem);
            item.addEventListener('click', () => {
              if (irPara(m.id)) { if (window.matchMedia('(max-width: 700px)').matches) painelBusca.hidden = true; }
              else cab.textContent += ' · mensagem antiga (fora das últimas carregadas)';
            });
            resultados.append(item);
          });
        } catch (e) { resultados.append(el('p', 'chat-busca-aviso', 'Não foi possível pesquisar agora.')); }
      };
      abrirBusca.addEventListener('click', () => {
        painelBusca.hidden = !painelBusca.hidden;
        if (!painelBusca.hidden) campoBusca.focus(); else { campoBusca.value = ''; resultados.replaceChildren(); }
      });
      campoBusca.addEventListener('input', () => { clearTimeout(esperaBusca); esperaBusca = setTimeout(buscar, 300); });
      campoBusca.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') abrirBusca.click(); });
      document.addEventListener('keydown', (ev) => {
        if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'f' && painelBusca.hidden && fio) { ev.preventDefault(); abrirBusca.click(); }
      });
    }
    texto.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); form.requestSubmit(); }
    });
    const erro = form.querySelector('[data-chat-erro]');
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      if (!texto.value.trim() && !imagemEscolhida) return;
      const botao = form.querySelector('.chat-enviar');
      botao.disabled = true;
      erro.hidden = true;
      try {
        const corpoEnvio = new FormData(form);
        if (respondendo) corpoEnvio.append('responde_id', respondendo.id);
        if (imagemEscolhida) corpoEnvio.append(ehNucleai ? 'arquivo' : 'imagem', imagemEscolhida, imagemEscolhida.name || 'anexo');
        const r = await fetch(form.action, {method: 'POST', body: corpoEnvio, credentials: 'same-origin',
          headers: {Accept: 'application/json', 'X-CSRF-Token': csrf}});
        if (window.nuclelesteSessao && window.nuclelesteSessao(r)) { parar(); return; }
        if (r.redirected) { parar(); throw new Error('Sua sessão terminou. Recarregue a página.'); }
        const dados = await r.json();
        if (!r.ok) throw new Error(dados.erro || 'Não foi possível enviar.');
        texto.value = '';
        tirarImagem();
        fecharResposta();
        crescer();
        if (dados.encerrado) {
          // a NucleAI encerrou a conversa e apagou o histórico: mostra só a despedida
          fio.replaceChildren();
          exibidas.clear();
          diaAtual = '';
        } else {
          acrescentar(dados.mensagem, true);
        }
        (dados.respostas || []).forEach((m) => {
          acrescentar(m, true);
          // pedido confirmado escrevendo "sim": abre a tela/impressão logo (se o navegador bloquear, o botão "Abrir agora" fica na conversa)
          if (m.acao === 'CMD_ABRIR' && m.acao_resp && /^\/(?!\/)/.test(m.acao_resp)) window.open(m.acao_resp, '_blank');
        });
      } catch (problema) {
        erro.textContent = problema instanceof SyntaxError ? 'Não foi possível enviar. Recarregue a página.' : problema.message;
        erro.hidden = false;
      } finally {
        botao.disabled = false;
        texto.focus();
      }
    });
  }

  // ------------------------------------------------------------ lista de conversas
  const aplicarFiltro = () => {
    if (!lista || !filtro) return;
    const q = normalizar(filtro.value.trim());
    lista.querySelectorAll('li[data-nome]').forEach((i) => { i.hidden = !normalizar(i.dataset.nome).includes(q); });
  };
  const desenharLista = (contatos) => {
    if (!lista) return;
    lista.replaceChildren(...contatos.map((c) => {
      const li = el('li');
      li.dataset.nome = c.nome;
      const a = el('a', String(c.id) === com ? 'chat-item ativo' : 'chat-item');
      a.href = `?com=${c.id}`;
      const avatar = el('span', `chat-avatar cor${c.cor}`, c.avatar ? '' : c.iniciais);
      if (c.avatar) { const img = el('img', 'chat-avatar-img'); img.src = c.avatar; img.alt = ''; avatar.append(img); }
      const bolinha = el('span', c.online ? 'chat-bolinha online' : 'chat-bolinha');
      bolinha.dataset.presenca = c.id;
      avatar.append(bolinha);
      const corpoItem = el('span', 'chat-item-corpo');
      const nome = el('strong', '', c.nome);
      if (c.gestao) nome.append(' ', el('em', 'chat-tag', 'Gestão'));
      corpoItem.append(nome, el('small', '', (c.ultima_minha ? 'Você: ' : '') + (c.previa || 'Toque para conversar')));
      const meta = el('span', 'chat-item-meta');
      const selo = el('span', 'selo-menu', c.nao_lidas);
      selo.hidden = !c.nao_lidas;
      meta.append(el('time', '', c.ultima_em), selo);
      a.append(avatar, corpoItem, meta);
      li.append(a);
      return li;
    }));
    aplicarFiltro();
  };
  if (filtro) filtro.addEventListener('input', aplicarFiltro);

  // ------------------------------------------------------------ consulta periódica
  // Tempo real: com a aba visível, a consulta fica "segurada" no servidor (até 12 s) e só volta quando chega algo novo;
  // ao voltar, o navegador já pergunta de novo. Aba escondida ou servidor sem vaga de espera: consulta curta.
  const ESPERA_S = 12;           // curto de propósito: o servidor não sabe quando o navegador desiste, então a espera abandonada acaba logo
  let atrasoVisivel = 150;       // pausa entre uma consulta que esperou e a seguinte
  let voo = null;                // consulta em andamento (para cancelar ao trocar de aba ou sair da página)
  let lidasN = pagina ? Number(pagina.dataset.lidasN || 0) : 0;   // quantas mensagens minhas já foram lidas (acorda a espera quando muda)
  let outroDigitando = false;
  const intervalo = () => (document.hidden ? 8000 : atrasoVisivel);
  const agendar = () => {
    clearTimeout(timer);
    if (parado) return;
    timer = setTimeout(consultar, falhas ? Math.min(30000, Math.max(intervalo(), 1000) * 2 ** falhas) : intervalo());
  };
  const consultarJa = () => { if (!parado) { clearTimeout(timer); consultar(); } };
  const parar = () => { parado = true; if (voo) voo.abort(); definirEstado('● desconectado: recarregue a página', false); };
  window.addEventListener('pagehide', () => { if (voo) voo.abort(); });

  async function consultar() {
    if (parado) return;
    if (voo) voo.abort();                       // nunca duas consultas ao mesmo tempo
    const meu = voo = new AbortController();
    const p = new URLSearchParams({depois: ultimo});
    if (com) {
      p.set('com', com); p.set('depois_conv', depoisConv); p.set('desde', primeiro || 0);
      p.set('visivel', document.hidden ? '0' : '1');
      p.set('lidas_n', lidasN); p.set('dig', outroDigitando ? '1' : '0');
    }
    if (lista) p.set('lista', '1');
    if (resumoPendente) p.set('resumo', '1');
    const esperando = !document.hidden && !resumoPendente;   // a primeira consulta (resumo de não lidas) responde na hora
    if (esperando) p.set('espera', ESPERA_S);
    try {
      const r = await fetch(`${url}?${p}`, {headers: {Accept: 'application/json', 'X-Passivo': '1'}, credentials: 'same-origin', signal: meu.signal});
      if (window.nuclelesteSessao && window.nuclelesteSessao(r)) { parar(); return; }
      if (r.redirected || r.status === 403) { parar(); return; }
      if (!r.ok) throw new Error(String(r.status));
      const d = await r.json();
      falhas = 0;
      atrasoVisivel = (esperando && d.espera === false) ? 2000 : 150;   // sem vaga de espera no servidor: consulta mais espaçada
      (d.conversa || []).forEach((m) => acrescentar(m, false));
      if (d.lidas) marcarLidas(d.lidas);
      if (d.lidas_n !== undefined) lidasN = d.lidas_n;
      if (d.contatos) desenharLista(d.contatos);
      aplicarPresenca(d.presenca);
      outroDigitando = !!d.digitando;
      if (estado && com && outroDigitando) { estado.textContent = '✍️ digitando…'; estado.classList.add('online'); }
      (d.novas || []).forEach((m) => {
        const lendo = com && String(m.de_id) === com && !document.hidden;
        if (!lendo) aviso({titulo: m.de_nome, texto: m.previa, href: `/mensagens?com=${m.de_id}`, id: m.id});
      });
      ultimo = Math.max(ultimo, d.ultimo || 0);
      if (resumoPendente && d.resumo) {
        resumoPendente = false;
        try { sessionStorage.setItem(chaveResumo, '1'); } catch (e) { /* ignorado */ }
        const pendentes = d.resumo.filter((i) => !(d.novas || []).some((m) => m.de_id === i.de_id));
        if (pendentes.length && !pagina) {
          const total = pendentes.reduce((s, i) => s + i.n, 0);
          const quem = pendentes.slice(0, 3).map((i) => i.de_nome).join(', ') + (pendentes.length > 3 ? ' e outros' : '');
          aviso({titulo: total === 1 ? 'Você tem 1 mensagem não lida' : `Você tem ${total} mensagens não lidas`, texto: `De: ${quem}`,
            href: `/mensagens?com=${pendentes[0].de_id}`});
        }
      } else if (resumoPendente && d.resumo !== undefined) {
        resumoPendente = false;
      }
      definirNaoLidas(d.nao_lidas || 0);
    } catch (e) {
      if (e && e.name === 'AbortError') return;   // trocada por uma consulta mais nova (ou a página está saindo)
      falhas += 1;
      definirEstado('● reconectando…', false);
    }
    if (voo === meu) voo = null;
    agendar();
  }
  setTimeout(consultarJa, 600); // verifica logo ao abrir qualquer tela (a primeira consulta responde na hora; as seguintes esperam)
})();
