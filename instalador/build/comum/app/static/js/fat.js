/* Faturamento: visualizador do PDF do protocolo (abre dentro do sistema), importação com um clique e a prévia ao vivo da glosa. */
(() => {
  // ---------------------------------------------------------------- PDF do protocolo
  const dlg = document.getElementById('dlg-pdf');
  if (dlg) {
    const quadro = document.getElementById('pdf-quadro');
    document.addEventListener('click', (e) => {
      const b = e.target.closest('[data-pdf]');
      if (!b) return;
      document.getElementById('pdf-titulo').textContent = b.dataset.titulo || 'Protocolo';
      document.getElementById('pdf-baixar').href = b.dataset.baixar || '#';
      document.getElementById('pdf-pagina').href = b.dataset.pagina || '#';
      quadro.src = b.dataset.pdf;
      dlg.showModal();
    });
    dlg.addEventListener('close', () => { quadro.src = 'about:blank'; });   // não deixa o PDF carregado em segundo plano
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  }
  // importar o PDF: escolher o arquivo já envia
  document.querySelectorAll('input[type=file][data-auto]').forEach((i) => i.addEventListener('change', () => { if (i.files.length) i.form.submit(); }));

  // ---------------------------------------------------------------- recebimento: bruto, tributos, líquido e glosa
  const form = document.getElementById('form-quitar');
  if (!form) return;
  const num = (s) => { s = String(s || '').replace(/[R$\s]/g, ''); if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.'); const v = parseFloat(s); return isNaN(v) ? 0 : v; };
  const fmt = (v) => v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const faturado = document.getElementById('q-faturado'), bruto = document.getElementById('q-bruto'), liquido = document.getElementById('q-liquido');
  const usar = document.getElementById('q-usar-trib'), campoTrib = document.getElementById('q-trib-campo'), trib = document.getElementById('q-trib');
  const previa = document.getElementById('q-previa');
  let origem = 'bruto';   // o último campo mexido decide quem é calculado: bruto/tributos → líquido; líquido → bruto

  function atualizar() {
    campoTrib.hidden = !usar.checked;
    const t = usar.checked ? num(trib.value) : 0;
    if (origem === 'liquido') bruto.value = fmt(num(liquido.value) + t);
    else liquido.value = fmt(num(bruto.value) - t);
    const f = num(faturado.value), b = num(bruto.value), dif = Math.round((f - b) * 100) / 100;
    previa.className = 'fat-previa ' + (dif > 0.004 ? 'glosa' : dif < -0.004 ? 'acima' : 'sem');
    previa.textContent = dif > 0.004 ? 'Glosa: R$ ' + fmt(dif) + ' (' + fmt(f ? 100 * dif / f : 0) + '% do faturado)'
      : dif < -0.004 ? 'Recebido R$ ' + fmt(-dif) + ' a mais que o faturado' : 'Sem glosa: o bruto recebido é igual ao faturado';
  }
  bruto.addEventListener('input', () => { origem = 'bruto'; atualizar(); });
  trib.addEventListener('input', () => { origem = 'bruto'; atualizar(); });
  liquido.addEventListener('input', () => { origem = 'liquido'; atualizar(); });
  usar.addEventListener('change', () => { origem = 'bruto'; if (!usar.checked) trib.value = ''; atualizar(); });
  // depois que o botão "Lançar recebimento" preenche o diálogo (app.js), recalcula
  document.addEventListener('click', (e) => {
    if (!e.target.closest('[data-dialogo="dlg-quitar"]')) return;
    origem = 'bruto'; usar.checked = false; trib.value = '';
    atualizar();
  });
  form.addEventListener('submit', () => { form.action = '/faturamento/' + document.getElementById('quitar-id').value + '/quitar'; });
})();
