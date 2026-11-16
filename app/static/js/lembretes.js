// Janela de lembretes em checklist: abre uma vez por login (o servidor só põe o <dialog> na página quando há lembretes).
// As caixinhas gravam na hora (POST com o token CSRF); "Desativar" pede confirmação e some da janela.
(function () {
  'use strict';
  const dlg = document.getElementById('dlg-lembretes');
  const lista = document.getElementById('lem-lista');
  if (!dlg || !lista) return;
  const csrf = document.querySelector('meta[name=csrf]')?.content || '';

  // mesma ideia do tutorial: espera as boas-vindas e as telas de espera saírem da frente
  function enviar(url, campos) {
    const f = new FormData();
    f.append('_csrf', csrf);
    Object.entries(campos || {}).forEach(([k, v]) => f.append(k, v));
    return fetch(url, {method: 'POST', body: f, credentials: 'same-origin',
      headers: {'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': csrf}})
      .then((r) => r.json().catch(() => ({ok: false, erro: 'Resposta inesperada do servidor.'}))
        .then((j) => ({ok: r.ok && !!j.ok, erro: j.erro || ''})))
      .catch(() => ({ok: false, erro: 'Sem conexão com o servidor. Tente de novo.'}));
  }

  function bloco(l) {
    const caixa = document.createElement('div');
    caixa.className = 'lembrete-bloco';
    caixa.dataset.lid = l.id;

    const titulo = document.createElement('h3');
    titulo.textContent = l.titulo;
    caixa.append(titulo);
    if (l.para_todos || l.reset_diario) {
      const info = document.createElement('p');
      info.className = 'lem-sub';
      info.textContent = [l.para_todos ? 'Para todos os usuários' : '', l.reset_diario ? 'as marcações zeram todo dia' : ''].filter(Boolean).join(' · ');
      caixa.append(info);
    }

    const ul = document.createElement('ul');
    l.itens.forEach((it) => {
      const li = document.createElement('li');
      const rotulo = document.createElement('label');
      const cx = document.createElement('input');
      cx.type = 'checkbox';
      cx.checked = !!it.marcado;
      const txt = document.createElement('span');
      txt.textContent = it.texto;
      rotulo.append(cx, txt);
      li.append(rotulo);
      if (cx.checked) li.classList.add('feito');
      cx.addEventListener('change', () => {
        const marcado = cx.checked;
        cx.disabled = true;
        enviar('/lembretes/' + l.id + '/item/' + it.id + '/marcar', {valor: marcado ? '1' : '0'}).then((r) => {
          cx.disabled = false;
          if (!r.ok) {
            cx.checked = !marcado;
            aviso(caixa, r.erro || 'Não foi possível gravar a marcação.');
            return;
          }
          li.classList.toggle('feito', marcado);
        });
      });
      ul.append(li);
    });
    caixa.append(ul);

    const acoes = document.createElement('div');
    acoes.className = 'lembrete-acoes';
    const desmarcar = document.createElement('button');
    desmarcar.type = 'button';
    desmarcar.className = 'btn sec peq';
    desmarcar.textContent = 'Desmarcar tudo';
    desmarcar.addEventListener('click', () => {
      enviar('/lembretes/' + l.id + '/desmarcar').then((r) => {
        if (!r.ok) return aviso(caixa, r.erro || 'Não foi possível desmarcar.');
        ul.querySelectorAll('input').forEach((c) => { c.checked = false; });
        ul.querySelectorAll('li').forEach((li) => li.classList.remove('feito'));
      });
    });
    acoes.append(desmarcar);

    if (l.pode_editar) {
      const desativar = document.createElement('button');
      desativar.type = 'button';
      desativar.className = 'btn sec peq';
      desativar.textContent = 'Desativar este lembrete';
      desativar.addEventListener('click', () => {
        if (!confirm('Desativar o lembrete "' + l.titulo + '"? Ele deixa de aparecer ao entrar no sistema.')) return;
        enviar('/lembretes/' + l.id + '/desativar').then((r) => {
          if (!r.ok) return aviso(caixa, r.erro || 'Não foi possível desativar.');
          caixa.remove();
          if (!lista.querySelector('.lembrete-bloco')) fechar();
        });
      });
      acoes.append(desativar);
    }
    caixa.append(acoes);
    return caixa;
  }

  function aviso(caixa, texto) {
    let p = caixa.querySelector('.lembretes-erro');
    if (!p) {
      p = document.createElement('p');
      p.className = 'lembretes-erro';
      p.setAttribute('role', 'alert');
      caixa.prepend(p);
    }
    p.textContent = texto;
  }

  function fechar() {
    if (dlg.open) dlg.close();
  }

  function abrir(dados) {
    lista.replaceChildren();
    if (!dados.length) return;
    dados.forEach((l) => lista.append(bloco(l)));
    try { dlg.showModal(); } catch (e) { dlg.setAttribute('open', ''); }
  }

  dlg.querySelector('[data-lem-fechar]')?.addEventListener('click', fechar);

  let tentativas = 0;
  const espera = setInterval(() => {
    tentativas += 1;
    if (document.querySelector('.boas-vindas, .aguarde, .modal-sessao') && tentativas < 40) return;
    clearInterval(espera);
    fetch('/lembretes/pendentes', {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}})
      .then((r) => (r.ok ? r.json() : {lembretes: []}))
      .then((j) => abrir(j.lembretes || []))
      .catch(() => { /* sem rede: a janela não abre; os lembretes continuam na tela Lembretes */ });
  }, 700);
})();
