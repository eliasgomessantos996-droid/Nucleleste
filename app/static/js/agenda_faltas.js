'use strict';
/* Faltas e reagendamento: cada paciente que faltou ganha um botão do WhatsApp com uma mensagem pronta
   (escolhida no topo) e uma seleção de situação: “Reagendado” (escolhe o novo dia e horário e o paciente é copiado
   com todas as informações) ou “Desistiu”. Quem resgatou fica registrado no servidor.
   A mensagem é só um rascunho: quem envia é a recepção, no WhatsApp. */
(() => {
  // a primeira opção é o texto de reagendamento editado pela gerência (Administração > Mensagens do WhatsApp)
  const MODELOS_WHATS = (() => { try { return JSON.parse(document.getElementById('af-mensagens').textContent); } catch (e) { return {}; } })();
  const preencherModelo = (modelo, p) => {
    const primeiro = ((p.nome || '').trim().split(' ')[0] || '').toLowerCase().replace(/^\p{L}/u, (c) => c.toUpperCase());
    const v = {saudacao: primeiro ? 'Olá, ' + primeiro : 'Olá', nome: primeiro, exame: p.exame || '', data: p.data || '', hora: p.hora || ''};
    return (modelo || '').replace(/\{(\w+)\}/g, (marca, chave) => (chave in v ? v[chave] : marca));
  };
  const MENSAGENS = [
    (p) => preencherModelo(MODELOS_WHATS.reagendamento, p),
    (p) => `Oi, ${p.nome}! 💚 Aqui é a equipe da Nucleleste. Não conseguimos te ver no exame de ${p.exame} do dia ${p.data}, e queremos muito cuidar de você. ` +
           'Quer remarcar? Me diga um dia e horário de preferência que a gente organiza tudo com carinho. 😊',
    (p) => `Olá, ${p.nome}, tudo certo? 🌷 Passando para dizer que sentimos sua falta no exame de ${p.exame} (${p.data}). ` +
           'Se ainda precisar, temos horários disponíveis para você remarcar com o maior prazer. Responda esta mensagem e reagendamos juntos! 😊',
  ];

  const seletor = document.getElementById('af-mensagem');
  const busca = document.getElementById('af-busca');
  const semResultado = document.querySelector('.af-semresultado');
  const dlg = document.getElementById('af-dlg');
  const csrf = (document.querySelector('meta[name=csrf]') || {}).content || '';
  if (!seletor) return;

  const linhas = () => [...document.querySelectorAll('[data-linha]')];
  const grupos = () => [...document.querySelectorAll('[data-grupo]')];
  const dataBR = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  const semAcento = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const primeiroNome = (nome) => {
    const p = (nome || '').trim().split(/\s+/)[0] || '';
    return p.toLowerCase().replace(/(^|\s)\p{L}/gu, (m) => m.toUpperCase());
  };
  const diaSeguinte = (iso) => {
    const d = new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)) + 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };

  const textoDaMensagem = (l) => MENSAGENS[Number(seletor.value)]({
    nome: primeiroNome(l.dataset.nome), exame: l.dataset.exame, data: dataBR(l.dataset.data),
  });

  const atualizarLinks = () => {
    linhas().forEach((l) => {
      const a = l.querySelector('.af-zap');
      if (a) a.href = 'https://wa.me/' + l.dataset.wa + '?text=' + encodeURIComponent(textoDaMensagem(l));
    });
  };

  // contadores (total, com e sem telefone) e quantidade por exame, sempre a partir do que está na tela
  const atualizarContagens = () => {
    const todas = linhas();
    const comContato = todas.filter((l) => l.dataset.wa).length;
    const total = document.querySelector('[data-total]');
    const com = document.querySelector('[data-com-contato]');
    const sem = document.querySelector('[data-sem-contato]');
    if (total) total.textContent = todas.length;
    if (com) com.textContent = comContato;
    if (sem) sem.textContent = todas.length - comContato;
    grupos().forEach((g) => {
      const n = g.querySelectorAll('[data-linha]').length;
      const legenda = g.querySelector('.ag-bloco-tit small');
      if (legenda) legenda.textContent = n + (n === 1 ? ' falta no período' : ' faltas no período');
    });
  };

  // busca por nome: esconde quem não combina e os exames que ficarem vazios
  const filtrar = () => {
    const termo = semAcento(busca.value.trim());
    let achou = 0;
    grupos().forEach((g) => {
      let visiveis = 0;
      g.querySelectorAll('[data-linha]').forEach((l) => {
        const ok = !termo || semAcento(l.dataset.nome).includes(termo);
        l.hidden = !ok;
        if (ok) visiveis += 1;
      });
      g.hidden = visiveis === 0;
      achou += visiveis;
    });
    if (semResultado) semResultado.hidden = achou > 0 || !termo;
  };

  // tira a linha da lista depois que a situação foi registrada
  const sairDaLista = (linha) => {
    const grupo = linha.closest('[data-grupo]');
    linha.remove();
    if (grupo && !grupo.querySelector('[data-linha]')) grupo.remove();
    atualizarContagens();
    if (!linhas().length) document.querySelector('.af-tudo-certo')?.removeAttribute('hidden');
  };

  const enviar = async (url, dados) => {
    const r = await fetch(url, {method: 'POST', body: new URLSearchParams(dados), credentials: 'same-origin',
      headers: {'X-CSRF-Token': csrf, Accept: 'application/json'}});
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) throw new Error(j.erro || 'Não foi possível concluir.');
    return j;
  };

  // --- janela do reagendamento: escolhe o dia e o horário livre
  let atual = null;   // {linha, select, hid}
  const carregarLivres = async () => {
    const sel = document.getElementById('af-horario');
    sel.replaceChildren();
    const dia = document.getElementById('af-dia').value;
    if (!dia) return;
    try {
      const r = await fetch('/agenda/livres/' + dia, {credentials: 'same-origin', headers: {Accept: 'application/json'}});
      const {livres} = await r.json();
      if (!livres.length) sel.append(new Option('Não há horário livre neste dia', ''));
      livres.forEach((x) => sel.append(new Option(`${x.hora} · ${x.exame}`, x.id)));
    } catch (e) {
      sel.append(new Option('Não foi possível carregar os horários', ''));
    }
  };

  const fecharJanela = () => {
    dlg.close();
    if (atual) atual.select.value = '';
    atual = null;
  };

  document.getElementById('af-dia').addEventListener('change', carregarLivres);
  dlg.querySelector('[data-cancelar]').addEventListener('click', fecharJanela);
  dlg.querySelector('[data-confirmar]').addEventListener('click', async () => {
    const destino = document.getElementById('af-horario').value;
    const erro = dlg.querySelector('[data-erro]');
    if (!destino || !atual) { erro.textContent = 'Escolha um horário livre.'; erro.hidden = false; return; }
    try {
      const j = await enviar(`/agenda/horario/${atual.hid}/reagendar`, {destino});
      const linha = atual.linha;
      dlg.close();
      atual = null;
      sairDaLista(linha);
      alert(`Reagendado para ${j.quando}. Ficou no histórico da linha como reagendado por você.`);
    } catch (e) {
      erro.textContent = e.message;
      erro.hidden = false;
    }
  });

  // --- seleção de situação de cada paciente
  document.addEventListener('change', async (ev) => {
    const sel = ev.target.closest('[data-situacao]');
    if (!sel) return;
    const linha = sel.closest('[data-linha]');
    const hid = sel.dataset.situacao;
    if (sel.value === 'DESISTIU') {
      if (!confirm(`Registrar que ${linha.dataset.nome} desistiu?`)) { sel.value = ''; return; }
      try {
        await enviar(`/agenda/horario/${hid}/status`, {status: 'DESISTIU'});
        sairDaLista(linha);
      } catch (e) {
        sel.value = '';
        alert(e.message);
      }
    } else if (sel.value === 'RESGATADO') {
      atual = {linha, select: sel, hid};
      const dia = document.getElementById('af-dia');
      dlg.querySelector('[data-titulo]').textContent = `Reagendar ${linha.dataset.nome}`;
      dlg.querySelector('[data-erro]').hidden = true;
      dia.value = diaSeguinte(linha.dataset.data);
      dlg.showModal();
      carregarLivres();
    }
  });

  // recolher e mostrar um exame
  grupos().forEach((g) => {
    const botao = g.querySelector('[data-recolher]');
    const corpo = g.querySelector('[data-corpo-grupo]');
    if (!botao || !corpo) return;
    botao.addEventListener('click', () => {
      const recolhido = corpo.hidden;
      corpo.hidden = !recolhido;
      botao.textContent = recolhido ? 'Recolher' : 'Mostrar';
    });
  });

  seletor.addEventListener('change', atualizarLinks);
  busca.addEventListener('input', filtrar);
  atualizarLinks();
  atualizarContagens();
})();
