/* Saúde do sistema: anima a nota, o medidor e as barras, e reverifica sozinho a cada minuto. */
(function () {
  const INTERVALO_S = 60;

  // as barras e o medidor começam vazios e enchem depois que a página aparece
  const encher = () => {
    document.querySelectorAll('.sd-barra span[data-largura]').forEach((b) => { b.style.width = b.dataset.largura + '%'; });
    const arco = document.querySelector('.sd-arco[data-arco]');
    if (arco) arco.style.strokeDashoffset = arco.dataset.arco;
  };

  // nota: conta de 0 até o valor
  const contar = () => {
    const el = document.querySelector('[data-contar]');
    if (!el) return;
    const alvo = parseInt(el.dataset.contar, 10) || 0;
    const reduz = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduz) { el.textContent = alvo; return; }
    const inicio = performance.now();
    const duracao = 1500;
    const passo = (t) => {
      const p = Math.min((t - inicio) / duracao, 1);
      el.textContent = Math.round(alvo * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  };

  // contagem regressiva da próxima checagem (a página só recarrega se estiver visível)
  const recarregar = () => {
    const alvo = document.querySelector('[data-contagem]');
    let restante = INTERVALO_S;
    setInterval(() => {
      if (document.hidden) return;
      restante -= 1;
      if (alvo) alvo.textContent = restante;
      if (restante <= 0) window.location.reload();
    }, 1000);
  };

  requestAnimationFrame(() => setTimeout(() => { encher(); contar(); }, 60));
  recarregar();
})();
