/* Suporte ao desenvolvedor: o cartão sai da tela com uma animação antes de aceitar/recusar, e o botão "Copiar os textos" da pasta. */
(() => {
  const reduz = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Decisão (aceitar / não aceitar): o cartão desliza para fora e só então o formulário é enviado.
  document.querySelectorAll('form.sp-decisao').forEach((f) => {
    f.addEventListener('submit', (ev) => {
      if (reduz || f.dataset.saindo) return;
      const card = document.getElementById(f.dataset.card);
      if (!card) return;
      ev.preventDefault();
      f.dataset.saindo = '1';
      const botao = ev.submitter;
      card.classList.add('sp-saindo');
      if (botao && botao.value === 'recusar') card.classList.add('recusa');
      // envia pelo próprio formulário, com o botão clicado como campo escondido (o envio programático não leva o botão)
      if (botao && botao.name) {
        const h = document.createElement('input'); h.type = 'hidden'; h.name = botao.name; h.value = botao.value; f.appendChild(h);
      }
      const destino = botao && botao.getAttribute('formaction');
      if (destino) f.action = destino;
      setTimeout(() => f.submit(), 340);
    });
  });

  // Copiar os textos da pasta para a área de transferência
  document.querySelectorAll('[data-copiar]').forEach((b) => b.addEventListener('click', async () => {
    const alvo = document.querySelector(b.dataset.copiar);
    if (!alvo) return;
    const texto = alvo.value || alvo.textContent;
    try { await navigator.clipboard.writeText(texto); } catch (e) { alvo.hidden = false; alvo.select(); document.execCommand('copy'); alvo.hidden = true; }
    const antes = b.lastChild.textContent;
    b.lastChild.textContent = ' Copiado!';
    setTimeout(() => { b.lastChild.textContent = antes; }, 1800);
  }));
})();

// Dados que só o navegador sabe: vão junto do formulário (tela, janela, fuso, aparelho, hora, página de origem) para o desenvolvedor conferir.
(() => {
  const area = document.getElementById('sp-cliente');
  if (!area) return;
  const form = area.closest('form');
  const campo = (nome, valor) => {
    let i = form.querySelector('input[name="cl_' + nome + '"]');
    if (!i) { i = document.createElement('input'); i.type = 'hidden'; i.name = 'cl_' + nome; area.appendChild(i); }
    i.value = String(valor == null ? '' : valor).slice(0, 120);
  };
  const preencher = () => {
    const n = navigator, c = n.connection || {};
    campo('tela', screen.width + 'x' + screen.height);
    campo('janela', innerWidth + 'x' + innerHeight);
    campo('pixel', window.devicePixelRatio || 1);
    try { campo('fuso', Intl.DateTimeFormat().resolvedOptions().timeZone); } catch (e) { campo('fuso', ''); }
    campo('plataforma', n.platform || '');
    campo('toque', n.maxTouchPoints || 0);
    campo('nucleos', n.hardwareConcurrency || '');
    campo('memoria', n.deviceMemory || '');
    campo('online', n.onLine ? 'sim' : 'não');
    campo('hora_local', new Date().toString().slice(0, 33));
    campo('pagina', document.referrer || '');
    campo('tema', document.documentElement.dataset.brilho || 'claro');
    campo('conexao', (c.effectiveType || '') + (c.rtt ? ' ' + c.rtt + 'ms' : ''));
  };
  preencher();
  form.addEventListener('submit', preencher);
})();
