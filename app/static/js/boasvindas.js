/* Boas-vindas da nova versão: aparece logo depois da espera da atualização, com dicas animadas ("fica a dica"). */
(function () {
  const DICAS = [
    'Ficou com dúvida? Clique no botão redondo da NucleAI e escreva a sua pergunta com as suas palavras.',
    'No chat, a lupa pesquisa dentro da conversa e o botão ↩ responde a uma mensagem específica.',
    'Pesquise qualquer tela na barra lateral: basta digitar, ou apertar a tecla /.',
    'Escolha a cor do seu sistema no rodapé do menu. Ela fica salva no seu perfil.',
    'No Mapa de laudos, o botão "Marcar como entregue" da mensagem leva você direto ao laudo.',
    'Os relatórios agora têm o mesmo cabeçalho, rodapé e numeração em todo o sistema.',
    'O caixa avisa às 17h quem ainda está com o caixa aberto. Não esqueça de fechar.',
    'Saúde do sistema: a gerência confere backup, disco e erros em um só lugar.',
  ];
  const EMOJIS = ['🎉', '✨', '🚀', '💚', '⭐', '🎊', '🩺', '📋'];

  window.BoasVindas = {
    mostrar(versao) {
      if (document.querySelector('.boas-vindas')) return;
      const fundo = document.createElement('div');
      fundo.className = 'boas-vindas';
      fundo.setAttribute('role', 'dialog');
      fundo.setAttribute('aria-label', 'Bem-vindo à nova versão');

      const caixa = document.createElement('div');
      caixa.className = 'boas-vindas-caixa';
      const titulo = document.createElement('h2');
      titulo.textContent = 'Bem-vindo à Nova Versão, Aproveite!';
      const sub = document.createElement('p');
      sub.className = 'boas-vindas-sub';
      sub.textContent = 'Versão ' + versao + ' instalada.';
      const dica = document.createElement('div');
      dica.className = 'boas-vindas-dica';
      const rotulo = document.createElement('b');
      rotulo.textContent = 'Dica';
      const texto = document.createElement('span');
      dica.append(rotulo, texto);
      const botao = document.createElement('button');
      botao.type = 'button';
      botao.className = 'boas-vindas-botao';
      botao.textContent = 'Vamos lá!';
      caixa.append(titulo, sub, dica, botao);

      // emojis que sobem ao fundo, em posições e tempos diferentes
      const chuva = document.createElement('div');
      chuva.className = 'boas-vindas-chuva';
      for (let i = 0; i < 18; i++) {
        const e = document.createElement('i');
        e.textContent = EMOJIS[i % EMOJIS.length];
        e.style.left = (Math.random() * 100) + '%';
        e.style.animationDelay = (Math.random() * 3) + 's';
        e.style.animationDuration = (3.5 + Math.random() * 2.5) + 's';
        chuva.append(e);
      }
      fundo.append(chuva, caixa);
      document.body.append(fundo);

      let i = -1;
      const trocar = () => {
        i = (i + 1) % DICAS.length;
        texto.classList.add('sai');
        setTimeout(() => { texto.textContent = DICAS[i]; texto.classList.remove('sai'); }, 300);
      };
      trocar();
      const giro = setInterval(trocar, 2800);

      const fechar = () => {
        clearInterval(giro);
        clearTimeout(fim);
        fundo.classList.add('saindo');
        setTimeout(() => fundo.remove(), 400);
      };
      botao.addEventListener('click', fechar);
      fundo.addEventListener('click', (ev) => { if (ev.target === fundo) fechar(); });
      const fim = setTimeout(fechar, 12000);
    },
  };
})();
