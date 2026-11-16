/* Em qualquer tela aberta: faixa com a contagem do aviso de atualização e, na hora H, a tela de espera animada.
   Quando o sistema volta (depois de ficar fora do ar ou em espera), recarrega a página sozinho. */
(function () {
  const URL_ESTADO = '/atualizacao/estado';
  let faltam = 0;              // segundos até a atualização anunciada
  let referencia = 0;          // momento (ms) em que `faltam` foi lido
  let faixa = null;
  let fundo = null;
  let animacao = null;
  let viuQueda = false;        // sistema já ficou fora do ar / em espera: ao voltar, recarrega
  let emEspera = false;
  let desde = 0;

  const rotulo = (s) => Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');

  const mostrarFaixa = (s) => {
    if (!faixa) {
      faixa = document.createElement('div');
      faixa.className = 'aguarde-aviso';
      document.body.append(faixa);
    }
    faixa.textContent = '⚠ O sistema será atualizado em ' + rotulo(s) + '. Salve o que estiver fazendo agora!';
  };
  const esconderFaixa = () => { if (faixa) { faixa.remove(); faixa = null; } };

  const abrirEspera = () => {
    if (fundo) return;
    esconderFaixa();
    emEspera = true;
    desde = Date.now();
    fundo = document.createElement('div');
    fundo.className = 'aguarde-fundo';
    const caixa = document.createElement('div');
    caixa.style.cssText = 'text-align:center;padding:16px';
    caixa.innerHTML = '<h1 style="font:700 24px Segoe UI,system-ui,sans-serif;color:var(--verde,#255f39);margin:0 0 4px">Estamos atualizando o sistema</h1>' +
      '<p style="margin:0 0 18px;color:#5a6b60;font-family:Segoe UI,system-ui,sans-serif">Aguarde um instante. Esta tela some sozinha quando terminar.</p>';
    const palco = document.createElement('div');
    caixa.append(palco);
    fundo.append(caixa);
    document.body.append(fundo);
    animacao = window.Aguarde ? window.Aguarde.montar(palco, 0) : null;
  };
  const fecharEspera = () => {
    if (animacao) animacao.parar();
    if (fundo) fundo.remove();
    fundo = animacao = null;
    emEspera = false;
  };

  // contagem local, segundo a segundo
  setInterval(() => {
    if (faltam <= 0 || emEspera) return;
    const s = Math.max(0, faltam - Math.round((Date.now() - referencia) / 1000));
    if (s > 0) mostrarFaixa(s); else abrirEspera();
  }, 1000);

  const consultar = async () => {
    try {
      const r = await fetch(URL_ESTADO, {cache: 'no-store', credentials: 'same-origin'});
      if (!r.ok) throw new Error('indisponível');
      const d = await r.json();
      if (d.atualizando) {
        viuQueda = true;
        abrirEspera();
      } else if (emEspera) {
        if (viuQueda) {
          // a espera acabou: a página recarregada mostra a mensagem de boas-vindas desta versão
          try { localStorage.setItem('nucleleste.boasVindas', document.body.dataset.versao || ''); } catch (e) { /* ignorado */ }
          location.reload();
          return;
        }
        // anunciou, mas a atualização não aconteceu (instalação cancelada): volta ao normal
        if (Date.now() - desde > 120000) { fecharEspera(); faltam = 0; }
      }
      faltam = d.aviso || 0;
      referencia = Date.now();
      if (!faltam && !emEspera) esconderFaixa();
    } catch (e) {
      // servidor fora do ar: se havia aviso (ou já estamos em espera), é a atualização acontecendo
      if (faltam > 0 || emEspera) { viuQueda = true; abrirEspera(); }
    }
  };

  // mensagem de boas-vindas logo após a espera: aparece uma única vez por versão
  const versaoAtual = document.body.dataset.versao || '';
  let novaVersao = false;
  try {
    novaVersao = !!versaoAtual && localStorage.getItem('nucleleste.boasVindas') === versaoAtual;
    if (novaVersao) localStorage.removeItem('nucleleste.boasVindas');
  } catch (e) { novaVersao = false; }
  if (novaVersao && window.BoasVindas) window.BoasVindas.mostrar(versaoAtual);

  consultar();
  setInterval(consultar, 4000);
})();
