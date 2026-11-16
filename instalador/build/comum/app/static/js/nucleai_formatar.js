'use strict';
/* Formatação das mensagens da NucleAI.
   O texto chega com marcas simples (como no WhatsApp/Markdown) e vira negrito, itálico, listas, títulos etc.
   Marcas aceitas (qualquer outra coisa aparece como texto normal):
     **negrito**   __itálico__ (ou *itálico*, _itálico_)   ~~riscado~~   ++sublinhado++   `código`
     # Título   ## Subtítulo   - item   1. item   > citação   ---  (divisor)   ``` bloco de código ```
     > [!aviso] texto   (também [!dica] [!ok] [!erro] [!info])   e tabelas com barras | a | b |
   Segurança: nada é inserido como HTML; os elementos são criados um a um e o texto entra por textContent. */
(function (raiz) {
  // ---------------------------------------------------------------- 1) texto -> árvore (sem DOM)
  // A ordem importa: em empate de posição vale o primeiro da lista (o ** vence o * simples).
  const INLINE = [
    { tag: 'code', cru: true, re: /`([^`\n]+)`/ },
    { tag: 'strong', re: /\*\*(?=\S)([^\n]*?\S)\*\*/ },
    { tag: 'em', re: /__(?=\S)([^\n]*?\S)__/ },
    { tag: 's', re: /~~(?=\S)([^\n]*?\S)~~/ },
    { tag: 'u', re: /\+\+(?=\S)([^\n]*?\S)\+\+/ },
    { tag: 'em', re: /\*([^\s*](?:[^*\n]*[^\s*])?)\*/ },
    { tag: 'em', re: /(?<![\w])_([^\s_](?:[^_\n]*[^\s_])?)_(?![\w])/ },
  ];
  const CHAMADAS = ['aviso', 'dica', 'ok', 'erro', 'info'];

  function inline(texto) {
    const saida = [];
    let resto = String(texto == null ? '' : texto);
    while (resto) {
      let melhor = null;
      for (const p of INLINE) {
        const m = p.re.exec(resto);
        if (m && (!melhor || m.index < melhor.m.index)) melhor = { p, m };
      }
      if (!melhor) { saida.push({ t: 'texto', v: resto }); break; }
      const { p, m } = melhor;
      if (m.index) saida.push({ t: 'texto', v: resto.slice(0, m.index) });
      saida.push(p.cru ? { t: p.tag, v: m[1] } : { t: p.tag, f: inline(m[1]) });
      resto = resto.slice(m.index + m[0].length);
    }
    return saida;
  }

  const EH = {
    vazia: (l) => /^\s*$/.test(l),
    codigo: (l) => /^\s*```/.test(l),
    divisor: (l) => /^\s*([-*_])\1{2,}\s*$/.test(l),
    titulo: (l) => /^\s{0,3}#{1,4}\s+\S/.test(l),
    tabela: (l) => /^\s*\|.*\|\s*$/.test(l),
    citacao: (l) => /^\s*>/.test(l),
    marcador: (l) => /^\s*[-*•]\s+\S/.test(l),
    numerada: (l) => /^\s*\d{1,3}[.)]\s+\S/.test(l),
  };
  const INICIO_DE_BLOCO = (l) => EH.vazia(l) || EH.codigo(l) || EH.divisor(l) || EH.titulo(l) || EH.tabela(l)
    || EH.citacao(l) || EH.marcador(l) || EH.numerada(l);

  const celulas = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
  const ehSeparador = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);

  function blocos(texto) {
    const linhas = String(texto == null ? '' : texto).replace(/\r\n?/g, '\n').split('\n');
    const saida = [];
    let i = 0;
    while (i < linhas.length) {
      const l = linhas[i];
      if (EH.vazia(l)) { i++; continue; }
      if (EH.codigo(l)) {
        const cod = [];
        i++;
        while (i < linhas.length && !EH.codigo(linhas[i])) cod.push(linhas[i++]);
        i++;   // fecha a cerca (ou o fim do texto)
        saida.push({ b: 'pre', v: cod.join('\n') });
        continue;
      }
      if (EH.divisor(l)) { saida.push({ b: 'hr' }); i++; continue; }
      if (EH.titulo(l)) {
        const m = /^\s{0,3}(#{1,4})\s+(.+?)\s*#*\s*$/.exec(l);
        saida.push({ b: 'titulo', n: Math.min(m[1].length, 3), f: inline(m[2]) });
        i++;
        continue;
      }
      if (EH.tabela(l)) {
        const ls = [];
        while (i < linhas.length && EH.tabela(linhas[i])) ls.push(linhas[i++]);
        const comCabecalho = ls.length > 1 && ehSeparador(ls[1]);
        const dados = ls.filter((x) => !ehSeparador(x)).map(celulas);
        saida.push({ b: 'tabela', cab: comCabecalho ? dados.shift().map(inline) : null, linhas: dados.map((r) => r.map(inline)) });
        continue;
      }
      if (EH.citacao(l)) {
        const ls = [];
        while (i < linhas.length && EH.citacao(linhas[i])) ls.push(linhas[i++].replace(/^\s*>\s?/, ''));
        let tipo = '';
        const m = /^\[!(\w+)\]\s*/.exec(ls[0]);
        if (m && CHAMADAS.includes(m[1].toLowerCase())) { tipo = m[1].toLowerCase(); ls[0] = ls[0].slice(m[0].length); }
        saida.push({ b: 'citacao', tipo, f: ls.map(inline) });
        continue;
      }
      if (EH.marcador(l) || EH.numerada(l)) {
        const ordenada = EH.numerada(l);
        const itens = [];
        while (i < linhas.length && (ordenada ? EH.numerada(linhas[i]) : EH.marcador(linhas[i]))) {
          itens.push(inline(linhas[i++].replace(ordenada ? /^\s*\d{1,3}[.)]\s+/ : /^\s*[-*•]\s+/, '')));
        }
        saida.push({ b: ordenada ? 'ol' : 'ul', itens });
        continue;
      }
      const par = [];
      while (i < linhas.length && !(par.length && INICIO_DE_BLOCO(linhas[i]))) par.push(inline(linhas[i++]));
      saida.push({ b: 'p', linhas: par });
    }
    return saida;
  }

  // ---------------------------------------------------------------- 2) texto sem as marcas (prévias e cópias)
  function textoSimples(texto) {
    let t = String(texto == null ? '' : texto);
    t = t.replace(/```[^\n]*\n?/g, '').replace(/^\s*#{1,4}\s+/gm, '').replace(/^\s*>\s?(\[!\w+\]\s*)?/gm, '');
    for (let n = 0; n < 3; n++) {
      t = t.replace(/\*\*(?=\S)([^\n]*?\S)\*\*/g, '$1').replace(/__(?=\S)([^\n]*?\S)__/g, '$1')
        .replace(/~~(?=\S)([^\n]*?\S)~~/g, '$1').replace(/\+\+(?=\S)([^\n]*?\S)\+\+/g, '$1')
        .replace(/`([^`\n]+)`/g, '$1').replace(/\*([^\s*](?:[^*\n]*[^\s*])?)\*/g, '$1');
    }
    return t.replace(/^\s*---+\s*$/gm, '').replace(/\n{3,}/g, '\n\n').trim();
  }

  // ---------------------------------------------------------------- 3) árvore -> elementos da página
  function criar(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }

  function desenharInline(nos, pai) {
    for (const n of nos) {
      if (n.t === 'texto') pai.append(document.createTextNode(n.v));
      else if (n.f) { const e = criar(n.t); desenharInline(n.f, e); pai.append(e); }
      else { const e = criar(n.t); e.textContent = n.v; pai.append(e); }
    }
  }
  function desenharLinhas(linhas, pai) {
    linhas.forEach((nos, k) => { if (k) pai.append(criar('br')); desenharInline(nos, pai); });
  }

  function render(texto) {
    const raizEl = criar('div', 'nf');
    for (const b of blocos(texto)) {
      let e;
      if (b.b === 'p') { e = criar('p', 'nf-p'); desenharLinhas(b.linhas, e); }
      else if (b.b === 'titulo') { e = criar('div', 'nf-titulo nf-t' + b.n); desenharInline(b.f, e); }
      else if (b.b === 'hr') e = criar('hr', 'nf-hr');
      else if (b.b === 'pre') { e = criar('pre', 'nf-pre'); const c = criar('code'); c.textContent = b.v; e.append(c); }
      else if (b.b === 'ul' || b.b === 'ol') {
        e = criar(b.b, 'nf-lista');
        for (const it of b.itens) { const li = criar('li'); desenharInline(it, li); e.append(li); }
      } else if (b.b === 'citacao') {
        e = criar('blockquote', 'nf-citacao' + (b.tipo ? ' nf-chamada nf-' + b.tipo : ''));
        desenharLinhas(b.f, e);
      } else if (b.b === 'tabela') {
        const rolagem = criar('div', 'nf-tabela-rolagem');
        e = criar('table', 'nf-tabela');
        if (b.cab) {
          const tr = criar('tr');
          for (const c of b.cab) { const th = criar('th'); desenharInline(c, th); tr.append(th); }
          const th = criar('thead'); th.append(tr); e.append(th);
        }
        const tb = criar('tbody');
        for (const r of b.linhas) {
          const tr = criar('tr');
          for (const c of r) { const td = criar('td'); desenharInline(c, td); tr.append(td); }
          tb.append(tr);
        }
        e.append(tb);
        rolagem.append(e);
        e = rolagem;
      }
      if (e) raizEl.append(e);
    }
    return raizEl;
  }

  const api = { render, blocos, inline, textoSimples };
  raiz.NucleaiFormatar = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
