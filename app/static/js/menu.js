'use strict';
/* Barra lateral: pesquisa no topo e temas que se recolhem (cada tema é um botão com o seu nome).
   A escolha de quais temas ficam ocultos fica neste navegador (localStorage); a pesquisa não grava nada. */
(() => {
  const menu = document.querySelector('.menu');
  if (!menu) return;
  const busca = document.getElementById('busca-menu');
  const semResultado = menu.querySelector('.sem-resultado');
  const CHAVE = 'nucleleste.temasOcultos';

  const lerOcultos = () => {
    try { return JSON.parse(localStorage.getItem(CHAVE)) || []; } catch (e) { return []; }
  };
  const gravarOcultos = (lista) => {
    try { localStorage.setItem(CHAVE, JSON.stringify(lista)); } catch (e) { /* navegador sem armazenamento: vale só para esta tela */ }
  };
  const semAcento = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  // cada bloco de itens tem o botão do tema logo antes (o tema do topo não tem botão)
  const blocos = () => [...menu.querySelectorAll('[data-tema-itens]')].map((itens) => {
    const cab = itens.previousElementSibling && itens.previousElementSibling.matches('button.grupo') ? itens.previousElementSibling : null;
    // o nome é só o texto do tema (o ícone é outro elemento dentro do mesmo span)
    const nome = cab ? [...cab.querySelector('span').childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim() : '';
    return {itens, cab, nome};
  });

  const marcarQuantidade = (b) => {
    const qtd = b.itens.querySelectorAll('a').length;
    let n = b.cab.querySelector('.qtd');
    if (!n) { n = document.createElement('small'); n.className = 'qtd'; b.cab.insertBefore(n, b.cab.querySelector('.seta')); }
    n.textContent = b.itens.hidden ? '(' + qtd + ')' : '';
  };

  const aplicar = (b, recolhido) => {
    b.itens.hidden = recolhido;
    b.cab.setAttribute('aria-expanded', String(!recolhido));
    marcarQuantidade(b);
  };

  // entrada em sequência dos módulos (cada item entra um pouco depois do anterior)
  menu.querySelectorAll('.tema-itens').forEach((lista) => lista.querySelectorAll('a').forEach((a, i) => a.style.setProperty('--i', Math.min(i, 12))));

  // destaque do tema onde a página aberta está (o ícone de cada tema já vem desenhado no HTML)
  blocos().forEach((b) => { if (b.cab) b.cab.classList.toggle('com-ativo', !!b.itens.querySelector('a.ativo')); });

  // estado salvo; o tema da página aberta nunca fica recolhido.
  // Logo depois do login (data-menu-recolher) todos os temas começam recolhidos, inclusive o da página inicial.
  const recolherTudo = document.body.hasAttribute('data-menu-recolher');
  let ocultos = recolherTudo
    ? blocos().filter((b) => b.cab).map((b) => b.nome)
    : lerOcultos();
  if (recolherTudo) gravarOcultos(ocultos);
  blocos().forEach((b) => {
    if (!b.cab) return;
    const temAtivo = !!b.itens.querySelector('a.ativo');
    if (!recolherTudo && temAtivo && ocultos.includes(b.nome)) ocultos = ocultos.filter((n) => n !== b.nome);
    aplicar(b, ocultos.includes(b.nome));
    b.cab.addEventListener('click', () => {
      const recolhido = !ocultos.includes(b.nome);
      ocultos = recolhido ? [...ocultos, b.nome] : ocultos.filter((n) => n !== b.nome);
      gravarOcultos(ocultos);
      aplicar(b, recolhido);
    });
  });

  // pesquisa: mostra só os itens que combinam, em todos os temas (inclusive os recolhidos)
  const filtrar = () => {
    const termo = semAcento(busca.value.trim());
    if (!termo) {
      blocos().forEach((b) => {
        if (b.cab) { b.cab.hidden = false; aplicar(b, ocultos.includes(b.nome)); }
        b.itens.querySelectorAll('a').forEach((a) => { a.hidden = false; });
        b.itens.hidden = b.cab ? ocultos.includes(b.nome) : false;
      });
      if (semResultado) semResultado.hidden = true;
      return;
    }
    let achou = 0;
    blocos().forEach((b) => {
      let visiveis = 0;
      b.itens.querySelectorAll('a').forEach((a) => {
        const ok = semAcento(a.textContent).includes(termo);
        a.hidden = !ok;
        if (ok) visiveis += 1;
      });
      b.itens.hidden = visiveis === 0;
      if (b.cab) { b.cab.hidden = visiveis === 0; b.cab.setAttribute('aria-expanded', String(visiveis > 0)); }
      achou += visiveis;
    });
    if (semResultado) semResultado.hidden = achou > 0;
  };

  // ocultar/mostrar a barra lateral (a escolha fica neste navegador)
  const alternar = document.getElementById('menu-alternar');
  if (alternar) {
    const CHAVE_MENU = 'nucleleste.menuOculto';
    const mostrar = () => {
      const oculto = document.body.classList.contains('menu-oculto');
      alternar.title = oculto ? 'Mostrar a barra lateral' : 'Ocultar a barra lateral';
      alternar.setAttribute('aria-label', alternar.title);
      alternar.setAttribute('aria-expanded', String(!oculto));
    };
    alternar.addEventListener('click', () => {
      const oculto = document.body.classList.toggle('menu-oculto');
      try { localStorage.setItem(CHAVE_MENU, oculto ? '1' : '0'); } catch (e) { /* vale só para esta tela */ }
      mostrar();
      window.dispatchEvent(new Event('resize'));
    });
    mostrar();
  }

  // tema de cor do perfil: aplica na hora e grava no perfil do usuário
  const tema = document.getElementById('tema-escolha');
  if (tema) {
    const csrf = (document.querySelector('meta[name=csrf]') || {}).content || '';
    tema.addEventListener('change', async () => {
      document.body.dataset.tema = tema.value;
      document.documentElement.dataset.tema = tema.value;   // as variáveis de cor vivem no <html>: o sistema inteiro muda
      try { localStorage.setItem('nucleleste.tema', tema.value); } catch (e) { /* ignorado */ }
      try {
        await fetch('/meu-tema', {method: 'POST', body: new URLSearchParams({tema: tema.value}), credentials: 'same-origin',
          headers: {'X-CSRF-Token': csrf}});
      } catch (e) { /* sem conexão: o tema fica só nesta tela até a próxima vez */ }
    });
  }

  if (busca) {
    busca.addEventListener('input', filtrar);
    busca.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        const primeiro = menu.querySelector('nav a:not([hidden])');
        if (primeiro) location.href = primeiro.href;
      } else if (ev.key === 'Escape') {
        busca.value = '';
        filtrar();
        busca.blur();
      }
    });
    // tecla "/" leva o cursor para a pesquisa (fora de campos de texto)
    document.addEventListener('keydown', (ev) => {
      const alvo = ev.target;
      const digitando = alvo && (alvo.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName));
      if (ev.key === '/' && !digitando && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
        ev.preventDefault();
        busca.focus();
        busca.select();
      }
    });
  }
})();
