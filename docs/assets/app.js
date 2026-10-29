(function () {
  'use strict';
  const M = window.META;
  const app = document.getElementById('app');
  let TASKS = [];
  const byId = {};

  // ---------- text helpers ----------
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  function md(s) {
    return esc(s)
      .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/«(.+?)»/g, '«<span class="q">$1</span>»')
      .replace(/\[\[([\w-]+)(?:\|(.+?))?\]\]/g, (m, id, label) =>
        `<a href="#/t/${id}">${label || (byId[id] ? esc(byId[id].title) : id)}</a>`);
  }
  // Same as md() but without links: for text that already sits inside a link
  function mdText(s) {
    return md(String(s || '').replace(/\[\[([\w-]+)(?:\|(.+?))?\]\]/g, (m, id, label) =>
      label || (byId[id] ? byId[id].title : id)));
  }
  const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9ñ ]/g, ' ');
  const words = (s) => norm(s).split(/\s+/).filter((w) => w.length > 1 && !M.stop.includes(w));

  // ---------- search ----------
  function expand(ws) {
    const out = new Set(ws);
    ws.forEach((w) => {
      Object.entries(M.synonyms).forEach(([key, list]) => {
        const all = [key, ...list].map(norm);
        if (all.some((a) => a === w || (w.length > 3 && a.startsWith(w)))) all.forEach((a) => a.split(' ').forEach((x) => out.add(x)));
      });
    });
    return [...out];
  }
  let INDEX = [];
  function buildIndex() {
    INDEX = [];
    TASKS.forEach((t) => {
      INDEX.push({kind: 'task', id: t.id, title: t.title, sub: t.summary, href: `#/t/${t.id}`,
        f: [[norm(t.title), 10], [norm((t.tags || []).join(' ')), 7], [norm(t.summary + ' ' + (t.when || '')), 3],
          [norm(t.steps.map((s) => [s.text, ...(s.labels || []), s.tip, s.warn, s.stop].join(' ')).join(' ')), 1]]});
    });
    M.errors.forEach((e, i) => INDEX.push({kind: 'error', title: e.msg, sub: 'Error: ' + e.fix, href: `#/errores/${i}`,
      f: [[norm(e.msg), 9], [norm(e.why + ' ' + e.fix), 2]]}));
    M.glossary.forEach((g) => INDEX.push({kind: 'term', title: g[0], sub: 'Glosario: ' + g[1], href: `#/glosario/${encodeURIComponent(g[0])}`,
      f: [[norm(g[0]), 8], [norm(g[1]), 1]]}));
  }
  function search(q) {
    const raw = words(q);
    if (!raw.length) return [];
    const ws = expand(raw);
    return INDEX.map((it) => {
      let score = 0;
      let hitRaw = 0;
      raw.forEach((w) => { if (it.f.some(([txt]) => txt.includes(w))) hitRaw++; });
      ws.forEach((w) => it.f.forEach(([txt, wt]) => {
        if (new RegExp('(^| )' + w).test(txt)) score += wt;
        else if (w.length > 3 && txt.includes(w)) score += wt / 2;
      }));
      score += hitRaw * 5;
      if (norm(it.title).includes(norm(q).trim())) score += 15;
      return {it, score};
    }).filter((r) => r.score > 2).sort((a, b) => b.score - a.score).map((r) => r.it);
  }
  const kindIcon = {task: '📘', error: '⛔', term: '📖'};

  function wireSearch(input, box, onEnter) {
    let sel = -1;
    let res = [];
    const render = () => {
      res = search(input.value).slice(0, 8);
      if (!input.value.trim()) { box.hidden = true; return; }
      box.innerHTML = res.length ? res.map((r, i) => `<a href="${r.href}" class="${i === sel ? 'on' : ''}">${kindIcon[r.kind]} ${esc(r.title)}<small>${mdText(r.sub)}</small></a>`).join('')
        : `<a href="#/buscar/${encodeURIComponent(input.value)}">No encuentro nada. Prueba con otras palabras (ej.: «presupuesto», «menú», «factura del restaurante»).</a>`;
      box.hidden = false;
    };
    input.addEventListener('input', () => { sel = -1; render(); });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, res.length - 1); render(); e.preventDefault(); }
      if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, -1); render(); e.preventDefault(); }
      if (e.key === 'Escape') { box.hidden = true; }
      if (e.key === 'Enter') {
        e.preventDefault();
        location.hash = sel >= 0 && res[sel] ? res[sel].href : `#/buscar/${encodeURIComponent(input.value)}`;
        box.hidden = true; input.blur(); if (onEnter) onEnter();
      }
    });
    input.addEventListener('blur', () => setTimeout(() => { box.hidden = true; }, 200));
    input.addEventListener('focus', () => { if (input.value) render(); });
  }

  // ---------- views ----------
  const cat = (id) => M.cats.find((c) => c.id === id) || {name: id, icon: '📁'};
  const taskLink = (t) => `<a href="#/t/${t.id}"><span class="n">${cat(t.cat).icon}</span><span>${esc(t.title)}<small>${mdText(t.summary)}</small></span></a>`;

  function viewHome() {
    const popular = M.popular.map((id) => byId[id]).filter(Boolean);
    app.innerHTML = `
      <section class="hero">
        <h1>¿Qué quieres hacer?</h1>
        <p class="lead">Escribe lo que necesitas con tus palabras. Cada tarea va <b>paso a paso, con capturas y números</b> que te dicen dónde pulsar.</p>
        <form class="big search" onsubmit="return false"><input id="q2" type="search" autocomplete="off" placeholder="Ej.: pedir presupuesto a un restaurante"><div id="suggest2" class="suggest" hidden></div></form>
        <div class="chips">${M.quick.map(([q, id]) => `<a href="#/t/${id}">${esc(q)}</a>`).join('')}</div>
      </section>
      <h2>El día a día de un grupo</h2>
      <div class="box">${M.flows.map((f) => `<p><b>${esc(f.name)}</b></p><div class="flow">${f.steps.map((id) => byId[id] ? `<a href="#/t/${id}">${esc(byId[id].short || byId[id].title)}</a>` : '').filter(Boolean).join('<i>→</i>')}</div>`).join('')}</div>
      <h2>Lo más usado</h2>
      <div class="tasklist">${popular.map(taskLink).join('')}</div>
      <h2>Todo, por temas</h2>
      <div class="grid">${M.cats.map((c) => {
        const n = TASKS.filter((t) => t.cat === c.id).length;
        return n ? `<a class="cat" href="#/c/${c.id}"><div class="ico">${c.icon}</div><b>${esc(c.name)}</b><span>${esc(c.desc)} · ${n} ${n === 1 ? 'tarea' : 'tareas'}</span></a>` : '';
      }).join('')}
        <a class="cat" href="#/errores"><div class="ico">⛔</div><b>Me sale un error</b><span>Qué significa cada mensaje y cómo arreglarlo</span></a>
        <a class="cat" href="#/glosario"><div class="ico">📖</div><b>Glosario</b><span>Qué es cada palabra (petición, expediente, hoja de servicio…)</span></a>
      </div>`;
    wireSearch(document.getElementById('q2'), document.getElementById('suggest2'));
  }

  function viewCat(id) {
    const c = cat(id);
    const list = TASKS.filter((t) => t.cat === id);
    app.innerHTML = `<div class="crumbs"><a href="#/">Inicio</a> ›</div>
      <h1>${c.icon} ${esc(c.name)}</h1><p class="lead">${esc(c.desc)}</p>
      ${c.intro ? `<div class="co info">${md(c.intro)}</div>` : ''}
      <div class="tasklist" style="margin-top:16px">${list.map(taskLink).join('')}</div>`;
  }

  function stepHtml(s, i) {
    const marks = (s.marks || []).map((m, j) => m ? `<div class="mk${m.x < 4 ? ' r' : ''}" style="left:${m.x}%;top:${m.y}%;width:${m.w}%;height:${m.h}%"><span class="dot">${j + 1}</span></div>` : '').join('');
    const labels = (s.labels || []).length ? `<ol class="labels">${s.labels.map((l, j) => `<li><span class="dot">${j + 1}</span><span>${md(l)}</span></li>`).join('')}</ol>` : '';
    const co = [['stop', s.stop], ['warn', s.warn], ['tip', s.tip], ['info', s.detail]].filter(([, v]) => v)
      .map(([k, v]) => `<div class="co ${k}">${md(v)}</div>`).join('');
    return `<section class="step" id="paso-${i + 1}">
      <div class="step-head"><div class="step-num">${i + 1}</div><div class="step-text">${md(s.text)}</div></div>
      ${labels}
      ${s.img ? `<div class="shot" data-i="${i}"><img src="${s.img}" width="${s.w}" height="${s.h}" loading="lazy" alt="Paso ${i + 1}">${marks}</div>` : ''}
      ${co ? `<div class="callouts">${co}</div>` : ''}
    </section>`;
  }

  function viewTask(id) {
    const t = byId[id];
    if (!t) { app.innerHTML = '<p class="empty">Esta tarea no existe. <a href="#/">Volver al inicio</a></p>'; return; }
    const c = cat(t.cat);
    const related = (t.next || []).map((n) => byId[n]).filter(Boolean);
    app.innerHTML = `<div class="crumbs"><a href="#/">Inicio</a> › <a href="#/c/${t.cat}">${esc(c.name)}</a> ›</div>
      <h1>${esc(t.title)} ${t.admin ? '<span class="tag admin">Solo administración</span>' : ''}</h1>
      <p class="lead">${md(t.summary)}</p>
      ${t.stop ? `<div class="co stop">${md(t.stop)}</div>` : ''}
      <div class="meta">
        ${t.when ? `<div class="box"><h3>¿Cuándo?</h3>${md(t.when)}</div>` : ''}
        ${(t.before || []).length ? `<div class="box"><h3>Antes de empezar</h3><ul>${t.before.map((b) => `<li>${md(b)}</li>`).join('')}</ul></div>` : ''}
      </div>
      <div class="toc" aria-label="Pasos">${t.steps.map((_, i) => `<a href="#/t/${id}/${i + 1}">${i + 1}</a>`).join('')}</div>
      ${t.steps.map(stepHtml).join('')}
      ${t.result ? `<div class="result"><b>✅ Resultado:</b> ${md(t.result)}</div>` : ''}
      ${(t.notes || []).map((n) => `<div class="co ${n[0]}" style="margin-top:10px">${md(n[1])}</div>`).join('')}
      ${related.length ? `<h2>¿Y ahora?</h2><div class="next">${related.map((r, i) => `<a class="${i ? 'alt' : ''}" href="#/t/${r.id}">${esc(r.title)} →</a>`).join('')}</div>` : ''}`;
    app.querySelectorAll('.shot').forEach((el) => el.addEventListener('click', () => openLightbox(el)));
  }

  function viewSearch(q) {
    const res = search(q);
    app.innerHTML = `<div class="crumbs"><a href="#/">Inicio</a> ›</div><h1>Resultados para «${esc(q)}»</h1>
      ${res.length ? `<div class="tasklist">${res.map((r) => `<a href="${r.href}"><span class="n">${kindIcon[r.kind]}</span><span>${esc(r.title)}<small>${mdText(r.sub)}</small></span></a>`).join('')}</div>`
        : '<p class="empty">No encuentro nada. Prueba con otras palabras, o mira <a href="#/">todos los temas</a>.</p>'}`;
  }

  function viewErrors(focus) {
    app.innerHTML = `<div class="crumbs"><a href="#/">Inicio</a> ›</div><h1>⛔ Me sale un error</h1>
      <p class="lead">Busca el mensaje que te sale (con <b>Ctrl+F</b> o con el buscador de arriba). A la derecha tienes qué hacer.</p>
      <table class="tbl"><thead><tr><th>Mensaje</th><th>Por qué sale</th><th>Qué hacer</th></tr></thead><tbody>
      ${M.errors.map((e, i) => `<tr id="err-${i}"><td><span class="err">${esc(e.msg)}</span></td><td>${md(e.why)}</td><td>${md(e.fix)}${e.task ? `<br><a href="#/t/${e.task}">Ver la tarea paso a paso →</a>` : ''}</td></tr>`).join('')}
      </tbody></table>`;
    if (focus != null) highlight(document.getElementById('err-' + focus));
  }

  function viewGlossary(focus) {
    app.innerHTML = `<div class="crumbs"><a href="#/">Inicio</a> ›</div><h1>📖 Glosario</h1>
      <table class="tbl"><tbody>${M.glossary.map((g) => `<tr id="g-${norm(g[0]).replace(/ /g, '-')}"><th style="width:28%">${esc(g[0])}</th><td>${md(g[1])}</td></tr>`).join('')}</tbody></table>`;
    if (focus) highlight(document.getElementById('g-' + norm(focus).replace(/ /g, '-')));
  }

  function highlight(el) {
    if (!el) return;
    el.scrollIntoView({block: 'center'});
    el.style.background = '#fef3c7';
  }

  // ---------- lightbox ----------
  const lb = document.getElementById('lightbox');
  function openLightbox(el) {
    const fig = lb.querySelector('figure');
    fig.innerHTML = el.innerHTML;
    fig.querySelector('img').removeAttribute('loading');
    lb.hidden = false;
  }
  lb.addEventListener('click', () => { lb.hidden = true; });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') lb.hidden = true; });

  // ---------- router ----------
  function route() {
    const h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
    const [a, b, c] = h.split('/');
    lb.hidden = true;
    if (a === 't') { viewTask(b); document.title = (byId[b] ? byId[b].title + ' · ' : '') + 'Guía Restagrup'; }
    else if (a === 'c') { viewCat(b); document.title = cat(b).name + ' · Guía Alquiler'; }
    else if (a === 'buscar') viewSearch(b || '');
    else if (a === 'errores') viewErrors(b);
    else if (a === 'glosario') viewGlossary(b);
    else { viewHome(); document.title = 'Guía de Restagrup'; }
    if (a === 't' && c) { const el = document.getElementById('paso-' + c); if (el) el.scrollIntoView(); }
    else window.scrollTo(0, 0);
  }

  fetch('data/tasks.json').then((r) => r.json()).then((data) => {
    TASKS = data;
    TASKS.forEach((t) => { byId[t.id] = t; });
    buildIndex();
    wireSearch(document.getElementById('q'), document.getElementById('suggest'));
    window.addEventListener('hashchange', route);
    route();
  }).catch(() => { app.innerHTML = '<p class="empty">No se ha podido cargar la guía. Recarga la página.</p>'; });
})();
