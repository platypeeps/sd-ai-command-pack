// Studio (sd:6920, sd:6921; slices 2 and 3 of sd:6919): the creative projects, each a folder with a project.json
// (studio.py). The page reads /api/studio through the shell's reader and draws the Documents list grammar: a filter bar, a
// sorted and paged ledger and the one Details pane, where each root's files show as a gallery. Each file is
// /studio/files/<repo>/<path>, served sandboxed; audio and video seek through a Range. Details draws the kind's stage strip;
// Next stage posts /api/items/<n>/stage with the revision the page read, as Watches' moves do. Each file's Pin and Hide post
// /api/studio/view, Documents' view state: a pinned file leads its root, a hidden one folds under Hidden.
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
  const url = f => `/studio/files/${f.file.split('/').map(encodeURIComponent).join('/')}`;
  const count = r => r.roots.reduce((n, root) => n + root.files.length, 0);
  // Each gallery file is a command object, so Pin and Hide are the shell's commands; its id names the file it serves.
  const fileId = (r, f) => `file:${r.repo}/${f.path}`;
  const storeOff = () => DOC && DOC.store && !DOC.store.available ? `the view store was not read: ${DOC.store.reason}` : true;
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
    const name = html`<span>${f.pinned ? html`<b class="pinmark">pinned · </b>` : ''}${f.name}</span>`;
    const acts = window.shell.commands.rowActions(f.id, { icons: true });
    if (f.media === 'video') return html`<li class="play"><video controls preload="metadata" src="${url(f)}"></video><a href="${url(f)}">${name}</a>${acts}</li>`;
    if (f.media === 'audio') return html`<li class="play"><audio controls preload="metadata" src="${url(f)}"></audio><a href="${url(f)}">${name}</a>${acts}</li>`;
    return html`<li><a href="${url(f)}" target="_blank" rel="noopener"><img loading="lazy" alt="${f.name}" src="${url(f)}">${name}</a>${acts}</li>`;
  }
  // The kind's stage strip: each stage in order, the item's own marked, then the Act bar with Next stage.
  function strip(r) {
    if (!r.kind) return '';
    if (!r.item) return html`<h3>Stage</h3><p class="why">This project names no sd item, so it has no stage. Add <code>"item": "sd:N"</code> to its project.json.</p>`;
    const at = r.strip.indexOf(r.stage);
    return html`<h3>Stage</h3><ol class="strip" aria-label="${r.kind} stages">${r.strip.map((s, i) => html`<li class="${i < at ? 'done' : i === at ? 'now' : ''}" aria-current="${i === at ? 'step' : 'false'}">${s.replace(/_/g, ' ')}</li>`)}</ol>
      <div>${window.shell.commands.bar(r.id)}</div>`;
  }
  // A root's files, pinned first; the hidden ones fold under Hidden, each with its Unhide.
  function gallery(r, root) {
    const all = root.files.map(f => window.shell.commands.get(fileId(r, f)) || { ...f, media: f.type, id: fileId(r, f), file: `${r.repo}/${f.path}` });
    const open = all.filter(f => !f.hidden).sort((a, b) => b.pinned - a.pinned), aside = all.filter(f => f.hidden);
    return html`<section class="root"><h3>${root.role} <span class="n">${root.path} · ${files(root.files.length)}${root.cut ? ', more on disk' : ''}</span></h3>
      ${open.length ? html`<ul class="gallery">${open.map(tile)}</ul>` : html`<p class="why">${all.length ? 'Every file in this root is hidden.' : 'No image, audio or video file in this root yet.'}</p>`}
      ${aside.length ? html`<details class="aside"><summary>Hidden <span class="n">${aside.length}</span></summary><ul class="gallery">${aside.map(tile)}</ul></details>` : ''}</section>`;
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
      ${strip(r)}
      ${r.roots.length ? r.roots.map(root => gallery(r, root)) : html`<p class="why">This project names no root that reads.</p>`}
      <p class="why">The files are read from disk, not git. Pin and Hide change this page only; no file moves.</p>`);
    window.shell.commands.select(r.id);
  }
  function unselect() {
    SELECTED = null;
    put($('details'), html`<p class="why">${!DOC ? 'The projects were not read, so nothing is selected.'
      : !ROWS.length ? (DOC.problems || []).length ? 'The scan named a problem, so nothing is selected. The note above names each one.'
        : 'No project.json is under the repositories yet.' : 'No project matches these filters. Clear them to see the list.'}</p>`);
  }
  let reader = null;
  const start = () => window.shell.read({ source: '/api/studio', what: 'the projects',
    adopt: doc => {
      DOC = doc;
      document.body.dataset.observed = doc.read;
      ROWS = (doc.projects || []).map(r => ({ ...r, type: 'project', label: r.title }));
      const FILES = ROWS.flatMap(r => r.roots.flatMap(root => root.files.map(f => ({ ...f, media: f.type, id: fileId(r, f), type: 'studio file',
        label: f.name, file: `${r.repo}/${f.path}`, pinned: !!f.pinned, hidden: !!f.hidden }))));
      // sd:7151: a scan that could not read a folder says so first; only a clean scan with no project says there is none.
      const problems = doc.problems || [];
      return { objects: [...ROWS, ...FILES],
        state: problems.length ? { kind: 'partial', text: `${problems.map(p => p.replace(/\.$/, '')).join(' · ')}. ${ROWS.length
          ? 'The list holds the projects the scan read.' : 'No project was read, so this is not a sign that none exists.'}`, source: '/api/studio' }
          : ROWS.length ? null : { kind: 'empty', text: 'No project.json is under the repositories yet.', source: '/api/studio' } };
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
  const view = (o, change) => window.shell.post('/api/studio/view', { file: o.file, ...change }).then(v => reader.reread().then(() => v));
  const NO_CLI = 'no CLI: view state; the dashboard writes it (POST /api/studio/view)';
  const flag = (id, label, icon, key, field, to, does, already) => ({ id, on: 'studio file', label, icon, key, does, risk: 'undo', executes: true,
    when: o => o[field] === to ? already : storeOff(),
    cli: () => NO_CLI, sends: o => `POST /api/studio/view {file: ${o.file}, ${field}: ${to}}`,
    run: o => view(o, { [field]: to }).then(() => `${label} · ${o.label}`), undo: o => view(o, { [field]: !to }) });
  // Slice 4 (sd:6922): each runs one fixed row of /api/actions/run for the project; the server finds it again.
  const ran = (o, action, ids) => window.commands.runAction(o, action, { project: o.id, ...ids });
  const tool = (kind, verb, risk) => ({ id: `studio.${kind}-${verb}`, on: 'project', label: `${kind === 'song' ? 'Song' : 'Episode'} ${verb}`,
    icon: 'play', risk, executes: true, does: `Runs the ${kind} tool's ${verb} on this project and shows its output in Details.`,
    when: o => o.kind === kind || `it is ${o.kind ? 'a ' + o.kind : 'a project of no kind'}, not ${kind === 'episode' ? 'an' : 'a'} ${kind}`,
    cli: o => `${kind === 'song' ? 'tools/song_pipeline.py' : 'tools/episode.py'} ${verb} ${o.folder}`,
    sends: o => `POST /api/actions/run {action: studio.${kind}, project: ${o.id}, verb: ${verb}}`,
    consequence: o => `This runs ${verb} on ${o.title}; it may write files in the project.`,
    run: o => ran(o, `studio.${kind}`, { verb }) });
  const register = () => window.shell.commands.register(
    { id: 'studio.check', on: 'project', label: 'Check', key: 'c', icon: 'check', risk: 'safe', executes: true,
      does: 'Runs make check in the project\'s repository and shows its output in Details.', when: () => true,
      cli: () => 'make check', sends: o => `POST /api/actions/run {action: studio.check, project: ${o.id}}`, run: o => ran(o, 'studio.check') },
    tool('episode', 'check', 'safe'), tool('episode', 'pack', 'confirm'),
    tool('song', 'validate', 'safe'), tool('song', 'suno-export', 'confirm'), tool('song', 'assemble', 'confirm'),
    { id: 'studio.session', on: 'project', label: 'Brief session', key: 'n', icon: 'terminal', risk: 'confirm', executes: true,
      does: 'Starts claude in herdr in the project\'s repository, told to read its brief; a note on its item names the pane.',
      when: () => true, consequence: o => `This starts a claude session for ${o.title}. It orders, uploads and buys nothing.`,
      cli: () => 'no sd verb: the dashboard starts claude in herdr, as Run starts a skill',
      sends: o => `POST /api/actions/run {action: studio.session, project: ${o.id}}`, run: o => ran(o, 'studio.session') },
    { id: 'studio.stage', on: 'project', label: 'Next stage', key: 's', icon: 'chevron-right', risk: 'confirm', executes: true, primary: () => true,
      does: o => o.next ? `Moves #${o.item} from ${o.stage || 'no stage'} to ${o.next}, with a note.` : 'Moves the project\'s item one stage along its strip.',
      when: o => !o.kind ? 'its project.json names no kind' : !o.item ? 'its project.json names no sd item'
        : !o.revision ? `item sd:${o.item} was not read` : o.next ? true
        : o.strip.includes(o.stage) ? `${o.stage} is the last ${o.kind} stage` : `item sd:${o.item} is at ${o.stage}, off the ${o.kind} strip: move it from the shell`,
      consequence: o => `This moves #${o.item} (${o.title}) from ${o.stage || 'no stage'} to ${o.next} and notes it. The page moves one stage at a time and never back; the shell moves it back.`,
      cli: o => `no sd verb: the dashboard moves #${o.item}'s stage, as Watches moves a watch`, sends: o => `POST /api/items/${o.item}/stage {revision, stage: ${o.next}}`,
      run: o => window.shell.post(`/api/items/${o.item}/stage`, { revision: o.revision, stage: o.next })
        .then(out => reader.reread().then(() => `${o.title} · stage ${out.item.stage}`),
          e => { if (e.stale) reader.reread(); throw e; }) },
    flag('studio.pin', 'Pin', 'pin', 'p', 'pinned', true, 'Pins the file to the front of its root; Undo unpins it.', 'already pinned'),
    flag('studio.unpin', 'Unpin', 'pin-off', 'p', 'pinned', false, 'Unpins the file; Undo pins it again.', 'not pinned'),
    flag('studio.hide', 'Hide', 'eye-off', 'h', 'hidden', true, 'Hides the file under its root\'s Hidden fold; no file moves. Undo shows it.', 'already hidden'),
    flag('studio.unhide', 'Unhide', 'eye', 'h', 'hidden', false, 'Shows the file in its root again; Undo hides it.', 'not hidden'));
  window.PAGE_LIST = { rows: () => $('rows').querySelectorAll('tr[data-id]'), current: () => SELECTED, select: key => show(key) };
  document.addEventListener('DOMContentLoaded', () => {
    reader = start();
    register();
    window.PAGE_AGAIN = { title: 'Read the projects again', run: () => reader.load() };
    reader.load();
  });
})();
