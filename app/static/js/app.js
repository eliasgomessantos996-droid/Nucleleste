// Comportamentos comuns do sistema (sem dependências externas).
(function () {
  'use strict';
  const csrf = document.querySelector('meta[name=csrf]')?.content || '';

  // Menu no celular
  document.querySelector('[data-abrir-menu]')?.addEventListener('click', () => {
    document.querySelector('.menu').classList.toggle('aberto');
  });

  // Confirmação antes de enviar formulários destrutivos
  document.addEventListener('submit', (e) => {
    const msg = e.target.getAttribute('data-confirmar') || e.submitter?.getAttribute('data-confirmar');
    if (msg && !confirm(msg)) e.preventDefault();
  });

  // Maiúsculas automáticas (como o UCase da planilha)
  document.querySelectorAll('[data-maiusculas]').forEach((el) => {
    el.addEventListener('input', () => {
      const p = el.selectionStart;
      el.value = el.value.toUpperCase();
      el.setSelectionRange(p, p);
    });
  });

  // Máscaras
  function mascara(el, fn) { el.addEventListener('input', () => { el.value = fn(el.value); }); }
  document.querySelectorAll('[data-mascara=cpf]').forEach((el) => mascara(el, (v) => {
    v = v.replace(/\D/g, '').slice(0, 11);
    return v.replace(/^(\d{3})(\d)/, '$1.$2').replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3').replace(/\.(\d{3})(\d)/, '.$1-$2');
  }));
  document.querySelectorAll('[data-mascara=cep]').forEach((el) => mascara(el, (v) => {
    v = v.replace(/\D/g, '').slice(0, 8);
    return v.length > 5 ? v.slice(0, 5) + '-' + v.slice(5) : v;
  }));
  document.querySelectorAll('[data-mascara=telefone]').forEach((el) => mascara(el, (v) => {
    // padrão (XX)9XXXX-XXXX, o mesmo da agenda
    const d = v.replace(/\D/g, '').slice(0, 11);
    if (d.length <= 2) return d;
    if (d.length <= 6) return '(' + d.slice(0, 2) + ')' + d.slice(2);
    if (d.length <= 10) return '(' + d.slice(0, 2) + ')' + d.slice(2, 6) + '-' + d.slice(6);
    return '(' + d.slice(0, 2) + ')' + d.slice(2, 7) + '-' + d.slice(7);
  }));

  // Copiar texto para a área de transferência
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-copiar]');
    if (!b) return;
    const texto = b.getAttribute('data-copiar');
    const ok = () => { const t = b.textContent; b.textContent = 'Copiado!'; setTimeout(() => (b.textContent = t), 1200); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(texto).then(ok);
    else {
      const ta = document.createElement('textarea'); ta.value = texto; document.body.appendChild(ta); ta.select();
      document.execCommand('copy'); ta.remove(); ok();
    }
  });

  // Abrir <dialog> a partir de botões: data-dialogo="id" + data-* para preencher campos
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-dialogo]');
    if (!b) return;
    const d = document.getElementById(b.getAttribute('data-dialogo'));
    if (!d) return;
    Object.entries(b.dataset).forEach(([k, v]) => {
      const campo = d.querySelector('[data-campo="' + k + '"]');
      if (!campo) return;
      if ('value' in campo && campo.tagName !== 'SPAN') campo.value = v; else campo.textContent = v;
    });
    d.showModal();
  });
  document.querySelectorAll('dialog [data-fechar]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));

  // ---------------------------------------------------------------- seletor de cliente
  // <div class="seletor" data-seletor-cliente> com input[type=search], input[name=cliente_id] e .resultados
  window.SeletorCliente = function (raiz, aoSelecionar) {
    const busca = raiz.querySelector('input[type=search]');
    const oculto = raiz.querySelector('input[type=hidden]');
    const res = raiz.querySelector('.resultados');
    let timer = null, itens = [], foco = -1;

    function render() {
      res.innerHTML = '';
      if (!itens.length) {
        res.innerHTML = '<div class="item"><small>Nenhum cliente encontrado.</small></div>';
      }
      itens.forEach((c, i) => {
        const div = document.createElement('div');
        div.className = 'item' + (i === foco ? ' foco' : '');
        div.innerHTML = '<strong></strong><br><small></small>';
        div.querySelector('strong').textContent = c.nome;
        div.querySelector('small').textContent = 'Cód. ' + c.id + ' · CPF ' + (c.cpf || '—') + ' · Nasc. ' + (c.data_nasc || '—') + ' · ' + (c.convenio || '');
        div.addEventListener('mousedown', (ev) => { ev.preventDefault(); escolher(c.id); });
        res.appendChild(div);
      });
      res.classList.add('aberto');
    }
    function escolher(id) {
      res.classList.remove('aberto');
      fetch('/api/clientes/' + id).then((r) => r.json()).then((c) => {
        oculto.value = c.id;
        busca.value = c.nome;
        aoSelecionar && aoSelecionar(c);
      });
    }
    busca.addEventListener('input', () => {
      oculto.value = '';
      aoSelecionar && aoSelecionar(null);
      clearTimeout(timer);
      const q = busca.value.trim();
      if (q.length < 2) { res.classList.remove('aberto'); return; }
      timer = setTimeout(() => {
        fetch('/api/clientes?q=' + encodeURIComponent(q)).then((r) => r.json()).then((l) => { itens = l; foco = l.length ? 0 : -1; render(); });
      }, 220);
    });
    busca.addEventListener('keydown', (e) => {
      if (!res.classList.contains('aberto')) return;
      if (e.key === 'ArrowDown') { foco = Math.min(itens.length - 1, foco + 1); render(); e.preventDefault(); }
      if (e.key === 'ArrowUp') { foco = Math.max(0, foco - 1); render(); e.preventDefault(); }
      if (e.key === 'Enter' && foco >= 0) { e.preventDefault(); escolher(itens[foco].id); }
      if (e.key === 'Escape') res.classList.remove('aberto');
    });
    busca.addEventListener('blur', () => setTimeout(() => res.classList.remove('aberto'), 150));
    if (oculto.value) escolher(oculto.value);
    return { escolher };
  };

  window.CSRF = csrf;

  // ================================================================ camada visual/animada global
  const reduz = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const NSV = 'http://www.w3.org/2000/svg';

  // Hero: o topo de toda página (título, subtítulo e ações) vira o mesmo cabeçalho animado do dashboard.
  function montarHero() {
    const c = document.querySelector('.conteudo');
    if (!c || c.querySelector('.dash > .hero') || c.querySelector('.ph-hero')) return;
    const h1 = c.querySelector('h1');
    if (!h1) return;
    let cab = h1.closest('.cabecalho');
    if (!cab) {
      cab = document.createElement('div'); cab.className = 'cabecalho';
      const bloco = document.createElement('div');
      h1.parentNode.insertBefore(cab, h1); cab.appendChild(bloco); bloco.appendChild(h1);
      const prox = bloco.nextSibling; // (h1 já foi movido) procurar o subtítulo logo após o cabeçalho
      const sub = cab.nextElementSibling;
      if (sub && sub.matches('p.sub')) bloco.appendChild(sub);
    }
    const hero = document.createElement('header'); hero.className = 'ph-hero';
    hero.innerHTML = '<div class="ph-fundo" aria-hidden="true"><span class="ph-blob ph-b1"></span><span class="ph-blob ph-b2"></span><span class="ph-blob ph-b3"></span></div>'
      + '<svg class="ph-atomo" viewBox="0 0 200 200" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.4"><ellipse cx="100" cy="100" rx="86" ry="30"/><ellipse cx="100" cy="100" rx="86" ry="30" transform="rotate(60 100 100)"/><ellipse cx="100" cy="100" rx="86" ry="30" transform="rotate(120 100 100)"/></g><circle cx="100" cy="100" r="9" fill="currentColor"/></svg>';
    let grupo = 'Recepção', ativo = document.querySelector('.menu a.ativo');
    for (let el = ativo; el; el = el.previousElementSibling) { if (el.classList.contains('grupo')) { grupo = el.textContent.trim(); break; } }
    const g = document.createElement('p'); g.className = 'ph-grupo'; g.textContent = grupo;
    const bloco = cab.firstElementChild;
    if (bloco && bloco.tagName === 'DIV') bloco.insertBefore(g, bloco.firstChild);
    cab.parentNode.insertBefore(hero, cab); hero.appendChild(cab);
    c.insertBefore(hero, c.firstChild);
  }

  // Revelação em cascata ao rolar (cartões, tabelas, indicadores, atalhos...)
  function contarNumero(el) {
    const txt = el.textContent.trim(), m = txt.match(/^(R\$\s*)?([\d.]+)(?:,(\d{1,2}))?$/);
    if (!m || reduz) return;
    const dec = m[3] ? m[3].length : 0, alvo = parseFloat(m[2].replace(/\./g, '') + (m[3] ? '.' + m[3] : ''));
    if (!alvo) return;
    const fmt = (n) => n.toLocaleString('pt-BR', { minimumFractionDigits: dec, maximumFractionDigits: dec });
    const t0 = performance.now(), dur = 1000;
    (function passo(t) {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 4);
      el.textContent = (m[1] || '') + fmt(alvo * e);
      if (p < 1) requestAnimationFrame(passo);
    })(t0);
  }
  function revelacao() {
    const c = document.querySelector('.conteudo');
    if (!c) return;
    const alvos = [];
    const marcar = (lista) => lista.forEach((el, i) => {
      if (el.closest('.dash') || el.matches('dialog, script, .mensagens, .ph-hero, .oculto')) return;
      el.classList.add('rv'); el.style.setProperty('--i', Math.min(i, 9)); alvos.push(el);
    });
    marcar([...c.children].filter((el) => !el.matches('.ph-hero, .mensagens')));
    c.querySelectorAll('.indicadores, .atalhos').forEach((g) => marcar([...g.children]));
    c.querySelectorAll('.tabela-wrap').forEach((w) => w.querySelectorAll('tbody tr').forEach((tr, i) => tr.style.setProperty('--r', Math.min(i, 24))));
    c.querySelectorAll('.lista-escolha label').forEach((l, i) => l.style.setProperty('--r', Math.min(i, 12)));
    const mostrar = (el) => {
      el.classList.add('visivel');
      el.querySelectorAll('.indicador .n, .n').forEach(contarNumero);
      if (el.matches('.indicador')) el.querySelectorAll('.n').forEach(contarNumero);
      setTimeout(() => el.classList.add('pronto'), 1300);
    };
    if ('IntersectionObserver' in window && !reduz) {
      const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { mostrar(e.target); io.unobserve(e.target); } }),
        { threshold: .08, rootMargin: '0px 0px -24px 0px' });
      // blocos muito altos (listas longas) nunca atingiriam 8% visível: aparecem de imediato
      alvos.forEach((el) => (el.offsetHeight > window.innerHeight * 1.2 ? mostrar(el) : io.observe(el)));
    } else alvos.forEach(mostrar);
  }

  // Onda ao clicar em botões
  document.addEventListener('pointerdown', (e) => {
    const b = e.target.closest('.btn'); if (!b || reduz) return;
    const r = b.getBoundingClientRect(), d = Math.max(r.width, r.height), o = document.createElement('span');
    o.className = 'onda'; o.style.cssText = 'width:' + d + 'px;height:' + d + 'px;left:' + (e.clientX - r.left - d / 2) + 'px;top:' + (e.clientY - r.top - d / 2) + 'px';
    b.appendChild(o); setTimeout(() => o.remove(), 650);
  });

  // Envio de formulário: indicador de carregamento e proteção contra clique duplo
  document.addEventListener('submit', (e) => {
    const f = e.target;
    if (e.defaultPrevented || f.target === '_blank' || f.hasAttribute('data-download') || (f.method || '').toLowerCase() !== 'post') return;
    if (f.dataset.enviado) { e.preventDefault(); return; }
    f.dataset.enviado = '1';
    (e.submitter || f.querySelector('button[type=submit], .btn[type=submit]'))?.classList.add('enviando');
  });
  window.addEventListener('pageshow', () => document.querySelectorAll('form[data-enviado]').forEach((f) => { delete f.dataset.enviado; f.querySelectorAll('.enviando').forEach((b) => b.classList.remove('enviando')); }));

  // Mensagens de sucesso somem sozinhas
  document.querySelectorAll('.msg.ok').forEach((m) => setTimeout(() => { m.classList.add('saindo'); setTimeout(() => m.remove(), 600); }, 6000));

  montarHero();
  revelacao();
})();
