'use strict';
/* Chat de treinamento da NucleAI IA (aba IA online): envia ao servidor e desenha as respostas e os cartões. */
(() => {
  const caixa = document.querySelector('[data-nia-treino]');
  if (!caixa) return;
  const fio = caixa.querySelector('[data-nia-fio]');
  const form = caixa.querySelector('[data-nia-form]');
  const campo = form.querySelector('textarea');
  const rotuloTreinador = caixa.querySelector('[data-nia-treinador]');
  const csrf = (document.querySelector('meta[name=csrf]') || {}).content || '';
  let enviando = false;

  const el = (tag, cls, txt) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined && txt !== null) e.textContent = String(txt);
    return e;
  };
  const rolar = () => { fio.scrollTop = fio.scrollHeight; };

  const desenhar = (m) => {
    const b = el('div', 'nia-msg ' + (m.papel === 'treinador' ? 'treinador' : m.papel === 'ia' ? 'ia' : 'sistema'));
    if (m.texto) b.append(m.papel === 'ia' && window.NucleaiFormatar ? window.NucleaiFormatar.render(m.texto) : el('div', '', m.texto));
    if (m.cartao && window.NucleaiCartoes && window.NucleaiCartoes.suporta(m.cartao)) {
      if (m.cartao.tipo === 'IA_ILUSTRACAO') b.classList.add('nia-msg-ilustrar');
      b.append(window.NucleaiCartoes.render(m.cartao, { responder: enviar }));
    }
    const rodape = [m.hora, m.papel === 'treinador' ? m.treinador : m.papel === 'ia' ? 'NucleAI' : ''].filter(Boolean).join(' · ');
    if (m.confianca) b.append(el('small', '', rodape + ' · confiança ' + m.confianca + '/5'));
    else if (rodape && m.papel !== 'sistema') b.append(el('small', '', rodape));
    fio.append(b);
  };

  const digitando = () => {
    const d = el('div', 'nia-digitando');
    d.append(el('i'), el('i'), el('i'));
    fio.append(d);
    rolar();
    return d;
  };

  async function enviar(texto) {
    texto = String(texto || '').trim();
    if (!texto || enviando) return;
    enviando = true;
    form.querySelector('button').disabled = true;
    const espera = digitando();
    try {
      const r = await fetch(caixa.dataset.url, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'X-Requested-With': 'fetch' },
        body: JSON.stringify({ texto }),
      });
      const j = await r.json().catch(() => ({ ok: false, erro: 'Resposta inválida do servidor.' }));
      espera.remove();
      if (!j.ok) { desenhar({ papel: 'sistema', texto: j.erro || 'Não foi possível enviar.' }); return; }
      j.mensagens.forEach(desenhar);
      if (rotuloTreinador && j.treinador) rotuloTreinador.textContent = j.treinador;
    } catch (e) {
      espera.remove();
      desenhar({ papel: 'sistema', texto: 'Sem conexão com o servidor do sistema.' });
    } finally {
      enviando = false;
      form.querySelector('button').disabled = false;
      rolar();
      campo.focus();
    }
  }

  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const t = campo.value;
    campo.value = '';
    enviar(t);
  });
  campo.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event('submit')); }
  });

  try { JSON.parse(document.getElementById('nia-conversa').textContent).forEach(desenhar); } catch (e) { /* sem histórico */ }
  if (!fio.children.length) desenhar({ papel: 'sistema', texto: 'Comece a conversa como se fosse um usuário. Digite /ajuda para ver os comandos do treino.' });
  rolar();

  // nota das respostas na tabela de log
  document.querySelectorAll('[data-nia-nota]').forEach((s) => {
    s.addEventListener('change', async () => {
      if (!s.value) return;
      const corpo = new URLSearchParams({ nota: s.value, _csrf: csrf });
      const r = await fetch(s.dataset.niaNota, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf }, body: corpo });
      s.style.outline = r.ok ? '2px solid #1a7f37' : '2px solid #b42318';
    });
  });
})();
