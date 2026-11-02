// Studio (sd:6920, slice 2 of sd:6919): the creative projects, each a folder with a project.json (studio.py). The page reads
// /api/studio through the shell's reader and draws the Documents list grammar: a filter bar, a sorted and paged ledger and
// the one Details pane, where each root's files show as a gallery. Each file is /studio/files/<repo>/<path>, served
// sandboxed; audio and video seek through a Range. Read-only: no command writes here until slices 3 and 4.
(() => {
  const { html, put, plural } = window.markup;
  const projects = n => plural(n, 'project', 'projects');
  const files = n => plural(n, 'file', 'files');
  const $ = id => document.getElementById(id);
  const KINDS = [['shirt', 'shirt'], ['song', 'song'], ['episode', 'episode']];
  const COLS = [[null, html`<span class="sr">State</span>`, 'g'], ['title', 'Project'], ['kind', 'Kind', 'repo'], ['repo', 'Repository', 'kind'],
    ['files', 'Files', 'num']];
  let DOC = null, ROWS = [], SELECTED = null;
  const F = { kind: '', q: '' }, L = { sort: 'title', dir: 1, page: 1, size: 50 };
  const url = f => `/studio/files/${f.repo}/${f.path.split('/').map(encodeURIComponent).join('/')}`;
  const count = r => r.roots.reduce((n, root) => n + root.files.length, 0);
  const state = r => r.error || r.problems.length ? ['caution', '▲', r.error || r.problems[0]] : ['ok', '●', 'reads clean'];
  function shown() {
    const key = { title: r => r.title.toLowerCase(), files: r => count(r) }[L.sort] || (r => String(r[L.sort] || '').toLowerCase());
    const q = F.q.toLowerCase().split(/\s+/).filter(Boolean);
    return ROWS.filter(r => (!F.kind || r.kind === F.kind) && q.every(w => `${r.title} ${r.kind} ${r.repo} ${r.folder} ${r.brief}`.toLowerCase().includes(w)))
      .sort((a, b) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0) * L.dir);
  }
  function row(r) {
    const [g, mark, word] = state(r);
    return html`<tr data-id="${r.id}" aria-selected="${String(r.id === SELECTED)}">
      <td class="g g-${g}" title="${word}"><span aria-hidden="true">${mark}</span><span class="sr">${word}</span></td>
      <td class="what"><button type="button">${r.title}</button><span class="file">${r.folder}</span></td>
      <td class="repo" data-meta="${` · ${r.repo} · ${files(count(r))}`}">${r.kind || '—'}</td>
      <td class="kind">${r.repo}</td>
      <td class="num">${count(r)}</td></tr>`;
  }
  function draw() {
    const L_ = window.shell.list, list = shown(), slice = L_.pageOf(list, L), n = k => ROWS.filter(r => r.kind === k).length;
    const flagged = ROWS.filter(r => state(r)[0] !== 'ok').length;
    put($('sub'), html`${DOC ? `${projects(ROWS.length)}${flagged ? ` · ${flagged} with a problem` : ''}` : 'The projects were not read'}`);
    put($('filters'), L_.fbar(html`${L_.fseg('kind', 'Kind', KINDS.map(([k, w]) => ({ v: k, pressed: F.kind === k, title: `${w}: ${n(k)}`,
      label: html`${w} <span class="n">${n(k)}</span>` })))}`, { clear: !!F.kind }));
    put($('rows-head'), L_.sortHead(COLS, L));
    put($('rows'), html`${slice.map(row)}`);
    const empty = $('empty');
    empty.hidden = !ROWS.length || list.length > 0;
    put(empty, html`No project matches these filters. <button class="linkish" type="button" data-fclear>Clear filters</button>`);
    put($('tally'), html`${DOC ? (list.length === ROWS.length ? projects(ROWS.length) : `${list.length} of ${projects(ROWS.length)}`) : ''}`);
    put($('pager'), L_.pager(list.length, L, 'projects'));
    put($('help'), L_.help('', [[html`<span class="g-ok" aria-hidden="true">●</span>`, 'reads clean'], [html`<span class="g-caution" aria-hidden="true">▲</span>`, 'a problem in its project.json']]));
    window.shell.reconcile({ rows: $('rows').querySelectorAll('tr[data-id]'), current: SELECTED, select: show,
      clear: () => { SELECTED = null; put($('details'), html`<p class="why">No project matches these filters, so nothing is selected.</p>`); } });
  }
  function tile(f) {
    const name = html`<span>${f.name}</span>`;
    if (f.type === 'video') return html`<li class="play"><video controls preload="metadata" src="${url(f)}"></video><a href="${url(f)}">${name}</a></li>`;
    if (f.type === 'audio') return html`<li class="play"><audio controls preload="metadata" src="${url(f)}"></audio><a href="${url(f)}">${name}</a></li>`;
    return html`<li><a href="${url(f)}" target="_blank" rel="noopener"><img loading="lazy" alt="${f.name}" src="${url(f)}">${name}</a></li>`;
  }
  function show(key) {
    const r = ROWS.find(x => x.id === key); if (!r) return;
    SELECTED = key;
    $('rows').querySelectorAll('tr[data-id]').forEach(tr => tr.setAttribute('aria-selected', tr.dataset.id === key));
    const [g, mark, word] = state(r);
    const problems = [r.error, ...r.problems].filter(Boolean);
    put($('details'), html`<p class="kind"><span class="g-${g}" aria-hidden="true">${mark}</span> ${r.kind || 'no kind'} · ${word}</p>
      <h2>${r.title}</h2>
      ${r.brief ? html`<p>${r.brief}</p>` : ''}
      ${problems.length ? html`<h3>Problems</h3><ul class="problems">${problems.map(p => html`<li>${p}</li>`)}</ul>` : ''}
      <h3>Facts</h3>
      <dl><dt>Folder</dt><dd>${r.repo}/${r.folder}</dd>
        <dt>Item</dt><dd>${r.item ? html`<a href="${window.shell.itemHref(r.item)}">#${r.item}</a>` : '— none named'}</dd></dl>
      ${r.roots.length ? r.roots.map(root => html`<section class="root"><h3>${root.role} <span class="n">${root.path} · ${files(root.files.length)}${root.cut ? ', more on disk' : ''}</span></h3>
        ${root.files.length ? html`<ul class="gallery">${root.files.map(f => tile({ ...f, repo: r.repo }))}</ul>` : html`<p class="why">No image, audio or video file in this root yet.</p>`}</section>`)
        : html`<p class="why">This project names no root that reads.</p>`}
      <p class="why">The files are read from disk, not git. Stages and actions come with the next slices.</p>`);
  }
  function unselect() {
    SELECTED = null;
    put($('details'), html`<p class="why">${!DOC ? 'The projects were not read, so nothing is selected.' : !ROWS.length ? 'No project.json is under the repositories yet.' : 'No project matches these filters. Clear them to see the list.'}</p>`);
  }
  let reader = null;
  const start = () => window.shell.read({ source: '/api/studio', what: 'the projects',
    adopt: doc => {
      DOC = doc;
      document.body.dataset.observed = doc.read;
      ROWS = (doc.projects || []).map(r => ({ ...r, type: 'project', label: r.title }));
      return { objects: ROWS,
        state: ROWS.length ? null : { kind: 'empty', text: 'No project.json is under the repositories yet.', source: '/api/studio' } };
    },
    clear: () => { DOC = null; ROWS = []; draw(); },
    draw, current: () => SELECTED, first: () => shown().slice((L.page - 1) * L.size)[0]?.id,
    select: key => show(key), unselect });
  const redraw = () => { L.page = 1; draw(); };
  $('filters').addEventListener('click', e => {
    if (e.target.closest('[data-fclear]')) { F.kind = ''; return redraw(); }
    const c = e.target.closest('[data-f="kind"]'); if (!c) return;
    F.kind = F.kind === c.dataset.v ? '' : c.dataset.v;
    redraw();
  });
  document.addEventListener('shell:filter', e => { if (e.detail.q === F.q) return; F.q = e.detail.q || ''; redraw(); });
  $('empty').addEventListener('click', e => { if (e.target.closest('[data-fclear]')) { F.kind = ''; F.q = ''; window.shell.filter(''); redraw(); } });
  $('rows-head').addEventListener('click', e => { if (window.shell.list.sortBy(e, L)) window.shell.list.keepFocus(e, draw); });
  $('pager').addEventListener('click', e => { if (window.shell.list.paging(e, L)) window.shell.list.keepFocus(e, draw); });
  $('rows').addEventListener('click', e => {
    if (e.target.closest('a')) return;
    const tr = e.target.closest('tr[data-id]'); if (tr) { show(tr.dataset.id); window.shell.openPane('tab-details'); }
  });
  window.PAGE_LIST = { rows: () => $('rows').querySelectorAll('tr[data-id]'), current: () => SELECTED, select: key => show(key) };
  document.addEventListener('DOMContentLoaded', () => {
    reader = start();
    window.PAGE_AGAIN = { title: 'Read the projects again', run: () => reader.load() };
    reader.load();
  });
})();
