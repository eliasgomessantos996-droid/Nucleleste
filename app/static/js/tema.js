'use strict';
/* Memória do tema para a tela de login. (A luz que seguia o mouse foi retirada: visual corporativo.) */
(() => {
  // a tela de login (sem usuário) usa o último tema deste navegador
  try {
    const salvo = localStorage.getItem('nucleleste.tema');
    if (salvo && !document.documentElement.dataset.tema) document.documentElement.dataset.tema = salvo;
    const brilho = localStorage.getItem('nucleleste.brilho');
    if (brilho && !document.documentElement.dataset.brilho) document.documentElement.dataset.brilho = brilho;
  } catch (e) { /* sem armazenamento */ }
})();
