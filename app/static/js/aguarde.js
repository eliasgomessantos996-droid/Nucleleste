/* Animações da espera da atualização (cenas com frases que brincam com o dia a dia da clínica). */
(function () {
  const CENAS = [
    {c: 'c-dose', f: 'Aplicando a dose do gerador… sem vazar nem um mCi!',
     h: '<i class="seringa">💉</i><i class="frasco">🧪</i><i class="brilho">✨</i>'},
    {c: 'c-eluir', f: 'Eluindo o tecnécio: ordenhando o gerador com carinho…',
     h: '<i class="gerador">⚗️</i><i class="gota">💧</i><i class="gota g2">💧</i><i class="tubo">🧫</i>'},
    {c: 'c-gama', f: 'Calibrando a gama câmara. Ela é sensível, fale baixinho…',
     h: '<i class="engrenagem">⚙️</i><i class="onda">〰️</i><i class="imagem">🩻</i>'},
    {c: 'c-agenda', f: 'Conferindo a agenda e mandando um WhatsApp carinhoso a quem faltou…',
     h: '<i class="cal">📅</i><i class="balao">💬</i><i class="balao b2">💚</i>'},
    {c: 'c-caixa', f: 'Contando o troco do caixa, centavo por centavo…',
     h: '<i class="moeda">🪙</i><i class="moeda m2">🪙</i><i class="moeda m3">🪙</i><i class="cofre">💰</i>'},
    {c: 'c-esteira', f: 'Mandando o paciente do MIBI correr na esteira (estresse, não o seu)…',
     h: '<i class="corredor">🏃</i><i class="suor">💦</i><i class="chao">▬ ▬ ▬ ▬ ▬ ▬ ▬ ▬ ▬ ▬ ▬ ▬</i>'},
    {c: 'c-laudo', f: 'Laudando as imagens… a tinta do laudo ainda está secando!',
     h: '<i class="raiox">🩻</i><span class="scan" style="position:absolute"></span><i class="papel">📄</i>'},
    {c: 'c-meiavida', f: 'A meia-vida do tecnécio é de 6 horas, mas esta espera é só de 1 minuto!',
     h: '<i class="ampulheta">⏳</i><i class="atomo">⚛️</i>'},
    {c: 'c-horas', f: 'Organizando o Banco de Horas. O servidor não faz hora extra!',
     h: '<i class="relogio">⏰</i><i class="zzz">💤</i>'},
    {c: 'c-imprime', f: 'Imprimindo a quitação sem o papel enroscar (cruze os dedos)…',
     h: '<i class="folha">🧾</i><i class="impressora">🖨️</i>'},
  ];

  const embaralhar = (v) => v.map((x) => [Math.random(), x]).sort((a, b) => a[0] - b[0]).map((p) => p[1]);

  // monta a animação em `alvo`; `segundos` (opcional) faz a barra encher nesse tempo
  window.Aguarde = {
    montar(alvo, segundos) {
      alvo.innerHTML = '';
      const raiz = document.createElement('div');
      raiz.className = 'aguarde';
      const palco = document.createElement('div');
      palco.className = 'aguarde-palco';
      const ordem = embaralhar(CENAS);
      const cenas = ordem.map((c) => {
        const d = document.createElement('div');
        d.className = 'aguarde-cena ' + c.c;
        d.innerHTML = c.h;
        palco.append(d);
        return d;
      });
      const frase = document.createElement('div');
      frase.className = 'aguarde-frase';
      const barra = document.createElement('div');
      barra.className = 'aguarde-barra';
      const enche = document.createElement('b');
      barra.append(enche);
      const tempo = document.createElement('div');
      tempo.className = 'aguarde-tempo';
      raiz.append(palco, frase, barra, tempo);
      alvo.append(raiz);

      let i = -1;
      const proxima = () => {
        i = (i + 1) % cenas.length;
        cenas.forEach((c, k) => c.classList.toggle('ativa', k === i));
        frase.classList.add('some');
        setTimeout(() => { frase.textContent = ordem[i].f; frase.classList.remove('some'); }, 350);
      };
      proxima();
      const giro = setInterval(proxima, 4200);

      const inicio = Date.now();
      let cronometro = null;
      if (segundos) {
        const avanco = () => {
          const passou = (Date.now() - inicio) / 1000;
          enche.style.width = Math.min(96, 4 + (passou / segundos) * 92) + '%';
          const falta = Math.max(0, Math.ceil(segundos - passou));
          tempo.textContent = falta > 0 ? 'Mais ou menos ' + falta + ' s…' : 'Quase lá… só mais um instantinho!';
        };
        avanco();
        cronometro = setInterval(avanco, 500);
      } else {
        enche.style.width = '40%';
        tempo.textContent = 'Instalando a versão nova. Já volta!';
      }
      return {
        parar() { clearInterval(giro); if (cronometro) clearInterval(cronometro); alvo.innerHTML = ''; },
      };
    },
  };
})();
