// Prontuário: sugestões clicáveis (chips) e preenchimento do padrão de cada etapa do documento.
(function () {
  // Acrescenta a frase ao campo: área vai em nova linha; texto substitui se vazio, senão acrescenta com "; ".
  function aplicar(alvo, texto) {
    const el = document.getElementById(alvo);
    if (!el) return;
    const atual = el.value.replace(/\s+$/, '');
    if (!atual) el.value = texto;
    else el.value = atual + (el.tagName === 'TEXTAREA' ? '\n' : '; ') + texto;
    marcar(alvo);
  }

  // Chip já usado fica marcado (o texto aparece no campo).
  function marcar(alvo) {
    const el = document.getElementById(alvo);
    if (!el) return;
    document.querySelectorAll('.chip[data-alvo="' + alvo + '"]').forEach((c) => {
      c.classList.toggle('usado', el.value.indexOf(c.dataset.texto) !== -1);
    });
  }

  document.querySelectorAll('.chip[data-alvo]').forEach((c) => {
    c.addEventListener('click', () => aplicar(c.dataset.alvo, c.dataset.texto));
    marcar(c.dataset.alvo);
  });

  // Campo condicional (ex.: justificativa só com SIM): some e não é enviado quando a resposta não bate.
  function atualizarCondicionais() {
    document.querySelectorAll('[data-cond]').forEach((linha) => {
      const ref = document.querySelector('input[name="' + linha.dataset.cond + '"]:checked');
      const ativo = !!ref && ref.value === linha.dataset.condValor;
      linha.hidden = !ativo;
      linha.querySelectorAll('input, textarea').forEach((i) => { i.disabled = !ativo; });
    });
  }
  document.querySelectorAll('input[type=radio]').forEach((r) => r.addEventListener('change', atualizarCondicionais));
  atualizarCondicionais();

  // Campos calculados ao vivo (mesma regra do servidor): escore de cálcio e NEWS.
  function num(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    const v = parseFloat((el.value || '').replace(',', '.'));
    return isNaN(v) ? null : v;
  }
  function calcularEscore() {
    const partes = ['da', 'cx', 'cd'].map(num);
    const el = document.getElementById('escore_total');
    if (!el) return;
    el.value = partes.every((p) => p !== null) ? String(partes.reduce((a, b) => a + b, 0)) : '';
  }
  function pontosNews() {
    const fr = num('fr'), spo2 = num('spo2'), temp = num('temp'), pas = num('pas'), fc = num('fc');
    if ([fr, spo2, temp, pas, fc].some((v) => v === null)) return null;
    const pFr = fr <= 8 ? 3 : fr <= 11 ? 1 : fr <= 20 ? 0 : fr <= 24 ? 2 : 3;
    const pSpo2 = spo2 <= 91 ? 3 : spo2 <= 93 ? 2 : spo2 <= 95 ? 1 : 0;
    const pO2 = (document.querySelector('input[name="o2"]:checked') || {}).value === 'Sim' ? 2 : 0;
    const pTemp = temp <= 35.0 ? 3 : temp <= 36.0 ? 1 : temp <= 38.0 ? 0 : temp <= 39.0 ? 1 : 2;
    const pPas = pas <= 90 ? 3 : pas <= 100 ? 2 : pas <= 110 ? 1 : pas <= 219 ? 0 : 3;
    const pFc = fc <= 40 ? 3 : fc <= 50 ? 1 : fc <= 90 ? 0 : fc <= 110 ? 1 : fc <= 130 ? 2 : 3;
    const pCons = (document.querySelector('input[name="consciencia"]:checked') || {}).value === 'Alerta' ? 0 : 3;
    return [pFr, pSpo2, pO2, pTemp, pPas, pFc, pCons];
  }
  function calcularNews() {
    const pontos = pontosNews();
    const total = document.getElementById('pontuacao'), risco = document.getElementById('risco');
    if (!total || !risco) return;
    if (!pontos) { total.value = ''; risco.value = ''; return; }
    const soma = pontos.reduce((a, b) => a + b, 0);
    total.value = String(soma);
    risco.value = soma >= 7 ? 'Alto' : soma >= 5 ? 'Médio' : pontos.includes(3) ? 'Baixo/médio: avaliar (3 em um parâmetro)' : 'Baixo';
  }
  function recalcular() { calcularEscore(); calcularNews(); }
  document.querySelectorAll('input, select').forEach((i) => i.addEventListener('input', recalcular));
  document.querySelectorAll('input[type=radio]').forEach((r) => r.addEventListener('change', recalcular));
  recalcular();

  // "Preencher com o padrão": aplica a primeira sugestão de cada campo vazio da etapa.
  document.querySelectorAll('[data-preencher-secao]').forEach((b) => {
    b.addEventListener('click', () => {
      const secao = b.closest('.pr-secao');
      if (!secao) return;
      secao.querySelectorAll('.sugestoes').forEach((grupo) => {
        const primeiro = grupo.querySelector('.chip');
        const el = primeiro && document.getElementById(primeiro.dataset.alvo);
        if (el && !el.value.trim()) aplicar(primeiro.dataset.alvo, primeiro.dataset.texto);
      });
    });
  });
})();
