// Your issues (sd:4628), on Issues (pack sd:7682; GitHub from sd:5781, Today from sd:5645, Tasks before): each repo's
// Jira and GitHub issues assigned to or filed by the operator.
// Issue intake (sd:4840), Issues' Issue Intake view (GitHub's Intake until pack sd:7682), is at the end.
// pack sd:7682: only issues.html loads this script, after github.js, so the Issues page's views are declared here.
window.PAGE_VIEWS = [{ id: 'issues', label: 'Your issues', key: 'y' }, { id: 'intake', label: 'Issue Intake' }];
// The rows are /api/github/issues' `issues` (issues.document over sd_db.repos.mine_issues); github.js hands them over
// with an issues:read event after each read, `error` set when the read failed. A failure is a row naming it, never an empty list.
// Markup is html`…` from markup.js: every value is escaped, and only an https address the server kept becomes a link.
// sd:5877: a row of either list, its title or a press on the row, opens its Details in the right pane, as a pull request
// row does (sd:5633): what sd shadow sync stored, said not stored where it keeps nothing, and Open in Jira or Open on
// GitHub and Open item, commands of the row's type the shell runs. The selection is named in ?row= as iss:<key>.
// sd:5899: one Jira and GitHub list: the operator's GitHub issues the Pull requests view listed are here too
// (issues.with_github), and `github` names that read when it failed. State open, the default, hides a closed row; with
// closed (?iss=closed) shows it, as the Pull requests view's State does.
// sd:6175: Hide and Unhide on a row of either list post /api/github/issues/view, the view state Contributions' Hide writes,
// each with Undo. A hidden row leaves its list, the tally and the tab count; Open | Hidden (sd:6701), at the left of
// each list's filter bar and kept as ?hidden=1, lists the hidden rows alone, with Unhide. A view store the read could not read hides nothing and turns
// both commands off with its reason.
// pack sd:7708: local categories for Jira issues, in the same view store; nothing is written to Jira. The Jira rows of Your
// issues group by category, one group open at a time, as GitHub's Pull requests group by repo (today-github.js, sd:7664):
// a press on a group opens it and closes the open one, a press on the open one closes it, and the selected row's group, or
// the first with a row, opens on the first draw. Uncategorized is the last group. pack sd:7753: GitHub rows group by repo,
// one group per repo, before the categories, by repo name with case ignored; the same one open group covers both kinds,
// and a repo group has no Actions. Each row gets an Actions cell (the ⋯ menu); Set category (jira issue.category) and the Category select in
// Details post /api/github/issues/view with the category, each with Undo. New category, in the section head, and a group's
// Rename and Remove post /api/github/issues/categories with the list the page read; Remove asks nothing, offers Undo,
// and leaves the group's issues uncategorized. A view store not read groups nothing: a line says why, and the commands are off.
(() => {
  const { html, put, plural } = window.markup;
  const $ = id => document.getElementById(id);
  let ISSUES = [], STORE = '', CATS = [];
  // The open group, a repo's or a category's: undefined until the first draw picks one, null once every group is closed.
  let OPEN;
  const I = n => html`<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const jira = r => r.tracker === 'Jira';
  const actions = id => window.shell?.commands?.rowActions ? window.shell.commands.rowActions(id) : '';
  // pack sd:7752: the category pickers list by name, case ignored; the groups keep the stored order.
  const byName = () => [...CATS].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
  const repoOf = r => r.repo || r.slug || 'GitHub';
  // pack sd:7754: a registered checkout's row has its short label as repo, a with_github row owner/name, so a repo keys on
  // its GitHub name (slug), case ignored, where the row has one; the group shows a checkout's short label.
  const repoKey = r => `repo:${r.slug ? r.slug.toLowerCase() : repoOf(r)}`;
  const groupOf = r => !jira(r) ? repoKey(r) : r.category && CATS.includes(r.category) ? `cat:${r.category}` : 'none';
  // pack sd:7753: the GitHub rows in view, one group per repo, by repo name with case ignored.
  const repoGroups = rows => [...new Set(rows.map(repoKey))]
    .map(key => { const of = rows.filter(r => repoKey(r) === key); return { key, name: repoOf(of.find(r => r.repo_path) || of[0]), rows: of }; })
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  // The Jira rows in view by category, in the list's order, then Uncategorized; under Hidden an empty category is left out.
  function groups(rows) {
    const G = CATS.map(name => ({ key: `cat:${name}`, name, rows: rows.filter(r => groupOf(r) === `cat:${name}`) }));
    const none = rows.filter(r => groupOf(r) === 'none');
    return [...G.filter(g => g.rows.length || !showHidden()), ...(none.length ? [{ key: 'none', name: 'Uncategorized', rows: none }] : [])];
  }
  const groupRow = g => { const on = OPEN === g.key, at = g.rows.map(r => r.updated_at).filter(Boolean).sort().pop();
    return html`<tr class="repo" data-cat="${g.key}" aria-expanded="${String(on)}">
      <td class="what" colspan="2"><button type="button" class="disc" data-cat-open="${g.key}" aria-expanded="${String(on)}" aria-label="${on ? 'Close' : 'Open'} ${g.name}">${I('chevron-right')}</button><button type="button" class="pick" data-cat-open="${g.key}">${g.name}</button></td>
      <td class="repo"></td><td class="why">${plural(g.rows.length, 'issue')}</td>
      <td class="when">${at ? html`<time class="rel" datetime="${at}"></time>` : ''}</td>
      <td class="act">${g.key.startsWith('cat:') ? actions(`isscat:${g.name}`) : ''}</td></tr>`; };
  const hid = () => window.shell.aside.mode('hidden'), showHidden = () => hid() === 'aside';
  const inView = r => window.shell.aside.shows(hid(), r.hidden);
  // The read's view state: why Hide is off, or '' when it read.
  const storeOff = store => !store ? 'the read carried no view state' : store.available ? '' : store.reason || 'the view store was not read';
  const hiddenSeg = (open, hidden) => window.shell.aside.seg('hidden', 'Hidden', hid(), { open, aside: hidden });
  const oid = r => `iss:${r.key}`;
  const title = r => html`<button type="button" data-iss-open="${oid(r)}">${r.title || r.ref}</button>`;
  const selected = r => html` data-id="${oid(r)}" aria-selected="${String(window.shell?.row?.() === oid(r))}"`;
  let READ = {};
  const isOpen = r => (r.state || 'open') === 'open';
  const closedToo = () => new URLSearchParams(location.search).get('iss') === 'closed';
  const issueRow = r => html`<tr${selected(r)}>
        <td class="ref">${r.url ? html`<a href="${r.url}">${r.tracker} ${r.ref}</a>` : html`${r.tracker} ${r.ref}`}</td>
        <td class="what">${title(r)}</td>
        <td class="repo">${r.repo}</td>
        <td class="why">${isOpen(r) ? r.reason : `${r.state} · ${r.reason}`}</td>
        <td class="when">${r.updated_at ? html`<time class="rel" datetime="${r.updated_at}"></time>` : ph(r)}</td>
        <td class="act">${actions(oid(r))}</td></tr>`;
  // The GitHub repo groups, then the Jira category groups; a view store not read groups no Jira row and says so above them.
  function body(rows) {
    const J = rows.filter(jira), G = [...repoGroups(rows.filter(r => !jira(r))), ...(STORE ? [] : groups(J))];
    const has = k => G.some(g => g.key === k), sel = rowOf(window.shell?.row?.() || '');
    if (OPEN === undefined || (OPEN && !has(OPEN))) OPEN = sel && has(groupOf(sel)) ? groupOf(sel) : (G.find(g => g.rows.length) || G[0] || {}).key;
    const shown = html`${G.map(g => html`${groupRow(g)}${OPEN === g.key ? g.rows.map(issueRow) : ''}`)}`;
    if (STORE) return html`${shown}${J.length ? html`<tr class="empty"><td colspan="6">Categories were not read: ${STORE}. The Jira issues below are not grouped. Read again tries again.</td></tr>` : ''}${J.map(issueRow)}`;
    return shown;
  }
  function draw({ issues = [], error = '', github = '', store, categories = [] } = READ) {
    READ = { issues, error, github, store, categories };
    ISSUES = error ? [] : issues; STORE = storeOff(store); CATS = STORE ? [] : categories;
    objects();
    // Every count below is of the rows in view: the unhidden ones, or the hidden ones under Hidden.
    const pool = ISSUES.filter(inView), open = pool.filter(isOpen), rows = closedToo() ? pool : open, L = window.shell?.list;
    const hiddenN = ISSUES.filter(r => r.hidden && (closedToo() || isOpen(r))).length, openN = ISSUES.filter(r => !r.hidden && (closedToo() || isOpen(r))).length;
    put($('issues'), error ? html`<tr class="empty"><td colspan="6">Issues could not be read: ${error}. Read again tries again.</td></tr>`
      : html`${rows.length || (CATS.length && !showHidden()) ? body(rows)
      : html`<tr class="empty"><td colspan="6">${showHidden() ? `No ${closedToo() ? '' : 'open '}issue is hidden.`
        : `No ${closedToo() ? '' : 'open '}issue is assigned to you or filed by you.`}</td></tr>`}${
        github ? html`<tr class="empty"><td colspan="6">Your GitHub issues outside the repos' issue sources were not read: ${github}. Read again tries again.</td></tr>` : ''}`);
    put($('issues-cats'), error ? html`` : html`<button class="btn quiet sm" type="button" data-cmd="issue categories.add" data-obj="isscats"${STORE ? html` disabled title="${`Categories are off: ${STORE}`}"` : ''}>${I('plus')}<span>New category</span></button>`);
    put($('issues-tally'), pool.length && !error ? html`<span>${open.length} ${showHidden() ? 'hidden' : 'open'}</span>${closedToo() ? html`<span>${pool.length - open.length} closed in 7 d</span>` : ''}` : html``);
    if (L) put($('issues-filters'), error ? html`` : L.fbar(html`${hiddenSeg(openN, hiddenN)}${L.fseg('iss', 'State',
      // pack sd:7084: Open | Hidden already says open; one chip adds the issues closed in 7 days, a second press drops them.
      [{ v: closedToo() ? 'open' : 'closed', pressed: closedToo(), label: html`with closed <span class="n">${String(pool.length - open.length)}</span>` }])}`));
    // The Your issues tab (sd:5080): the open rows not hidden, whichever list shows.
    window.shell?.view?.count('issues', error ? null : ISSUES.filter(r => isOpen(r) && !r.hidden).length);
  }
  document.addEventListener('issues:read', e => draw(e.detail));
  // State: open, or with closed; the param is written around the page's others (shell.url keeps ?row=).
  function pickState(v) {
    const p = new URLSearchParams(location.search);
    if (v === 'closed') p.set('iss', 'closed'); else p.delete('iss');
    window.shell.url(p.toString()); draw();
    $('issues-filters').querySelector?.('[data-f="iss"]')?.focus();
  }
  // Open | Hidden (sd:6175, sd:6701): one ?hidden= for both lists, as Contributions keeps it.
  function pickHidden(bar, v) {
    const p = new URLSearchParams(location.search), param = window.shell.aside.param(v);
    if (param) p.set('hidden', param); else p.delete('hidden');
    window.shell.url(p.toString()); draw(); drawIntake();
    $(bar).querySelector?.(`[data-aside="hidden"][data-v="${v}"]`)?.focus();
  }
  // A Hide or Unhide that landed moves its row at once; the page then reads again (github.js), and a refusal reads again too.
  function landed(key, hidden) {
    [...ISSUES, ...INTAKE].filter(r => r.key === key).forEach(r => { r.hidden = hidden; });
    draw(); drawIntake();
  }
  const NO_VIEW_CLI = 'no CLI: view state; the dashboard writes it (POST /api/github/issues/view)';
  // pack sd:7787: a bulk Hide sends one write per row at once; the page reads again once, when the last of them settles.
  let WRITING = 0;
  const settled = () => { if (--WRITING === 0) window.githubIssues?.again(); };
  const view = (o, hidden) => { WRITING++;
    return window.shell.post('/api/github/issues/view', { key: o.key, hidden })
      .then(v => { landed(o.key, hidden); settled(); return v; }, e => { settled(); throw e; }); };
  // pack sd:7708: a category set or cleared moves its row at once and opens the group it went to; the page then reads again.
  const NO_CAT_CLI = 'no CLI: issue categories are view state; the dashboard writes them';
  const categorize = (key, category) => window.shell.post('/api/github/issues/view', { key, category })
    .then(v => { ISSUES.filter(r => r.key === key).forEach(r => { r.category = category; }); OPEN = category ? `cat:${category}` : 'none';
      draw(); redetail(key); window.githubIssues?.again(); return v; }, e => { window.githubIssues?.again(); throw e; });
  const categories = body => window.shell.post('/api/github/issues/categories', body)
    .then(v => { READ = { ...READ, categories: v.categories }; draw(); window.githubIssues?.again(); return v; }, e => { window.githubIssues?.again(); throw e; });
  // Details showing the row redraw with its new category.
  const redetail = key => { const id = `iss:${key}`; if (window.shell?.commands?.selected?.()?.id === id) details(id, false); };

  // Issue intake (sd:4840), on GitHub: each policy.issues read or ask repo's open third-party issues no item carries (issues.intake over
  // sd_db.repos.intake_issues). File as item posts /api/items with the issue's title, repo and ref, the item `sd task add
  // --ref github:<owner>/<repo>#N` files. pack sd:7787: a filed row leaves the list at once, and a read that still lists
  // it (one begun before the write) keeps it out; the toast names the item. A refusal, such as a ref another item already
  // carries, stays on the row. Rows are keyed by that ref. File as item is the command `github issue.file`: the row's
  // button, Details' Act bar and the shell's bulk bar run it, so each says the same thing.
  // Bulk (pack sd:7787): a checkbox per row and one in the head pick rows into the shell's picked set (commands.pick, as
  // Tasks' boxes do); the shell's bulk bar offers File as item, Hide or Unhide where every picked row allows it, runs each
  // row's own call, and names each row not changed with its reason. The head box picks the rows shown, under Open or
  // Hidden alone, less any the table's column filter or the Shapeshift text hides; a pick no longer listed (filed, hidden,
  // unhidden, or another view shows) is dropped, so a bulk run does not reach a row that left the list.
  let INTAKE = [], FAILED = '';
  const FILED = new Map(), REFUSED = new Map(), BUSY = new Set();
  let PICKED = new Set(); // a mirror of the shell's picked rows (shell:picked)
  function control(r) {
    return html`<button type="button" class="btn quiet sm" data-key="${r.key}"${BUSY.has(r.key) ? html` disabled` : ''}>File as item</button>
      ${REFUSED.has(r.key) ? html`<p class="refused" role="alert">${REFUSED.get(r.key)}</p>` : ''}`;
  }
  const shownIntake = () => FAILED ? [] : INTAKE.filter(r => inView(r) && !FILED.has(r.key));
  const intakeIds = () => new Set(INTAKE.map(oid));
  // The rows the head box picks: those listed, less any the shell's table filter hides (data-tout).
  const onScreen = () => { const out = new Set([...(document.querySelectorAll?.('#intake tr[data-tout]') || [])].map(tr => tr.dataset.id));
    return shownIntake().filter(r => !out.has(oid(r))); };
  // Many picks at once (the head box, a redraw's unpick) paint once, after the last.
  let QUIET = false;
  const picks = ids => { const C = window.shell?.commands; if (!C?.pick || !ids.length) return;
    QUIET = true; try { ids.forEach(id => C.pick(id)); } finally { QUIET = false; } paintIntake(); };
  const pickBox = r => html`<label class="pick"><input type="checkbox" data-intake-pick="${oid(r)}" aria-label="Select GitHub ${r.ref}"${PICKED.has(oid(r)) ? html` checked` : ''}><span></span></label>`;
  // Each intake pick no longer shown leaves the picked set; with `all`, every intake pick does (another view shows).
  function unpick(all = false) {
    const shown = new Set(shownIntake().map(oid)), ours = intakeIds();
    picks([...PICKED].filter(id => ours.has(id) && (all || !shown.has(id))));
  }
  function paintIntake() {
    const rows = shownIntake();
    put($('intake'), FAILED ? html`<tr class="empty"><td colspan="6">Issue intake could not be read: ${FAILED}. Read again tries again.</td></tr>`
      : rows.length ? html`${rows.map(r => html`<tr${selected(r)}${BUSY.has(r.key) ? html` aria-busy="true"` : ''}${PICKED.has(oid(r)) ? html` data-picked` : ''}>
        <td class="sel">${pickBox(r)}</td>
        <td class="ref">${r.url ? html`<a href="${r.url}">GitHub ${r.ref}</a>` : html`GitHub ${r.ref}`}</td>
        <td class="what">${title(r)}</td>
        <td class="repo">${r.repo}</td>
        <td class="why">${r.author}</td>
        <td class="act">${control(r)}</td></tr>`)}`
      : html`<tr class="empty"><td colspan="6">${showHidden() ? 'No intake issue is hidden.' : 'No third-party issue waits for an item in a repo with GitHub issues on.'}</td></tr>`);
    // The head box: on when every row shown is picked, mixed when some are, off with no row to pick.
    const all = $('intake-all'), seen = onScreen(), n = seen.filter(r => PICKED.has(oid(r))).length;
    if (all) { all.checked = !!seen.length && n === seen.length; all.indeterminate = n > 0 && n < seen.length; all.disabled = !seen.length; }
    // A redraw replaced the box that had focus: focus its replacement, so Space can pick the next one.
    const f = document.activeElement?.dataset?.intakePick;
    if (f) [...($('intake').querySelectorAll?.('[data-intake-pick]') || [])].find(b => b.dataset.intakePick === f)?.focus();
  }
  function drawIntake() {
    unpick(); paintIntake();
    const left = INTAKE.filter(r => !FILED.has(r.key)), waiting = left.filter(r => !r.hidden).length, hiddenN = left.length - waiting;
    put($('intake-tally'), INTAKE.length && !FAILED ? html`<span>${showHidden() ? `${hiddenN} hidden` : `${waiting} waiting`}</span>` : html``);
    const L = window.shell?.list;
    if (L) put($('intake-filters'), FAILED ? html`` : L.fbar(hiddenSeg(waiting, hiddenN)));
    window.shell?.view?.count('intake', FAILED ? null : waiting); // the Intake tab
    objects();
  }
  // Files one intake row: resolves to the new item's id, or rejects with why it did not file. An answer that names no
  // item, or no answer at all, is not known to have filed or not: it says so, and the page reads again to settle it.
  function file(key) {
    const r = INTAKE.find(x => x.key === key);
    if (!r) return Promise.reject(new Error('the issue is no longer listed'));
    if (FILED.has(key)) return Promise.reject(new Error(`already filed as sd:${FILED.get(key)}`));
    if (BUSY.has(key)) return Promise.reject(new Error('it is being filed now'));
    BUSY.add(key); REFUSED.delete(key); drawIntake();
    const unknown = why => Object.assign(new Error(`not known if it filed: ${why}; Read again shows whether an item carries it`), { unknown: true });
    return window.shell.post('/api/items', { title: r.title, repo: r.repo_path, ref: r.key })
      .then(out => { const id = out?.item?.id; if (id == null) throw unknown('the answer named no item'); FILED.set(key, id); return id; },
        e => { throw e.status ? e : unknown(e.message); })
      .catch(e => { REFUSED.set(key, e.unknown ? `Not known if it filed: ${e.message.replace(/^not known if it filed: /, '')}` : `Not filed: ${e.message}`);
        if (e.unknown) window.githubIssues?.again(); throw e; })
      .finally(() => { BUSY.delete(key); drawIntake(); });
  }
  let FILE_CMD = null;
  // The row's File as item runs the command, so it toasts as Details and the bulk bar do; without the shell's commands
  // (a page stand-in) it files alone, and its refusal stays on the row.
  function fileRow(key) {
    const C = window.shell?.commands, o = C?.get?.(`iss:${key}`);
    if (FILE_CMD && o && C.run) return C.run(FILE_CMD, o);
    file(key).catch(() => {});
  }
  document.addEventListener('intake:read', e => {
    const { intake = [], error = '', store } = e.detail || {};
    // A filed issue the read no longer lists is done; one it still lists stays out until a read leaves it.
    [...FILED.keys()].filter(k => !intake.some(r => r.key === k)).forEach(k => FILED.delete(k));
    INTAKE = intake; FAILED = error; STORE = storeOff(store); REFUSED.clear(); drawIntake();
  });
  // The shell owns the picked set and its bar; the rows and the head box show it.
  document.addEventListener('shell:picked', e => { PICKED = new Set(e.detail || []); if (!QUIET) paintIntake(); });
  document.addEventListener('shell:view', e => { if (e.detail?.id !== 'intake') unpick(true); });
  document.addEventListener('change', e => {
    const t = e.target, C = window.shell?.commands; if (!t || !C?.pick) return;
    if (t.id === 'intake-all') return picks(onScreen().map(oid).filter(id => PICKED.has(id) !== !!t.checked));
    if (t.dataset?.intakePick) C.pick(t.dataset.intakePick);
  });
  document.addEventListener('click', e => {
    const s = e.target?.closest?.('#issues-filters [data-f="iss"]');
    if (s) return pickState(s.dataset.v);
    const h = e.target?.closest?.('#issues-filters [data-aside="hidden"], #intake-filters [data-aside="hidden"]');
    if (h) return pickHidden(h.closest?.('#intake-filters') ? 'intake-filters' : 'issues-filters', h.dataset.v);
    const b = e.target && e.target.closest && e.target.closest('#intake button[data-key]');
    if (b) return fileRow(b.dataset.key);
    const opened = e.target?.closest?.('[data-iss-open]');
    if (opened) return details(opened.dataset.issOpen);
    // A category group (pack sd:7708): its chevron, name or the rest of its row opens it and closes the open one.
    const g = e.target?.closest?.('[data-cat-open]') || (!e.target?.closest?.('a, button') && e.target?.closest?.('#issues tr.repo'));
    if (g) return toggle(g.dataset.catOpen ?? g.dataset.cat);
    // A press on a row's checkbox picks it (the change listener above); it opens no Details.
    const tr = e.target?.closest && !e.target.closest('a, button, label, input') && e.target.closest('#issues tr[data-id], #intake tr[data-id]');
    if (tr) details(tr.dataset.id);
  });

  function toggle(key) { OPEN = OPEN === key ? null : key; draw(); }
  // Details' Category select runs Set category with the picked value, so it toasts and offers Undo as the command does.
  document.addEventListener('change', e => {
    const s = e.target?.closest?.('[data-iss-cat]'), C = window.shell?.commands, o = s && C?.get(s.dataset.issCat);
    const c = o && REG_CAT; if (!c) return;
    C.run({ ...c, fields: null, run: x => c.run(x, { category: s.value }) }, o);
  });
  let REG_CAT = null;

  // ---------- Details (sd:5877) ----------
  // Both lists' rows by object id; an intake row filed here names its item until the next read.
  const rows = () => [...ISSUES, ...(FAILED ? [] : INTAKE).map(r => ({ ...r, intake: true, ...(FILED.has(r.key) ? { item: FILED.get(r.key) } : {}) }))];
  const rowOf = id => rows().find(r => oid(r) === id);
  const TYPE = { GitHub: 'github issue', Jira: 'jira issue' };
  const typeOf = r => TYPE[r.tracker || 'GitHub'];
  let PUT = new Set();
  // Each draw puts one command object per row; a row no read lists is retired, so no command runs on it.
  function objects() {
    const C = window.shell?.commands; if (!C) return;
    const keep = new Set();
    rows().forEach(r => { keep.add(oid(r)); C.put({ id: oid(r), type: typeOf(r), label: `${r.tracker || 'GitHub'} ${r.ref} ${r.title}`.trim(),
      url: r.url, item: r.item, ref: r.ref, slug: r.slug, key: r.key, hidden: !!r.hidden, category: r.category || null,
      intake: !!r.intake, repo_path: r.repo_path, title: r.title }); });
    // pack sd:7708: each category is an object for its group row's Rename and Remove; isscats holds New category.
    if (!FAILED_ISSUES()) {
      CATS.forEach(name => { keep.add(`isscat:${name}`); C.put({ id: `isscat:${name}`, type: 'issue category', label: name, name }); });
      keep.add('isscats'); C.put({ id: 'isscats', type: 'issue categories', label: 'Issue categories' });
    }
    PUT.forEach(id => { if (!keep.has(id)) C.put({ id, type: 'not listed', label: `${C.get(id)?.label || id} (no longer listed)` }); });
    PUT = keep;
  }
  // A fact the store did not record says so; one it could not read says that.
  const ph = r => html`<span class="ph">${r.unread ? 'not read' : 'not stored'}</span>`;
  const fact = (r, v) => v || ph(r);
  const FAILED_ISSUES = () => !!READ.error;
  // Details' Category (pack sd:7708): a Jira row's select, or why there is none to pick.
  const category = r => !jira(r) ? '' : html`<dt>Category</dt><dd>${STORE ? html`<span class="ph">not read: ${STORE}</span>`
    : !CATS.length ? html`<span class="ph">none yet: New category, in the list's head, adds one</span>`
    : html`<select class="cap-in" data-iss-cat="${oid(r)}" aria-label="Category">${[...byName().map(n => [n, n]), ['', 'None (Uncategorized)']].map(([v, l]) => html`<option value="${v}"${(r.category || '') === v ? html` selected` : ''}>${l}</option>`)}</select>`}</dd>`;
  const stamp = (r, v) => v ? html`<time class="rel" data-long datetime="${v}"></time>` : ph(r);
  function details(id, open = true) {
    const r = rowOf(id); if (!r) return;
    const tracker = r.tracker || 'GitHub';
    document.querySelectorAll('#issues tr[data-id], #intake tr[data-id]').forEach(tr => tr.setAttribute('aria-selected', String(tr.dataset.id === id)));
    put($('details'), html`<p class="kind">${tracker} issue · ${r.state || 'state not stored'}</p>
      <h2>${r.title || r.ref}</h2>
      <dl><dt>Issue</dt><dd>${tracker} ${r.ref}</dd><dt>Repo</dt><dd>${r.repo}${r.slug ? ` · ${r.slug}` : ''}</dd>
        <dt>State</dt><dd>${fact(r, r.state)}${r.status ? ` · ${r.status}` : ''}</dd>
        ${r.reason ? html`<dt>Why</dt><dd>${r.reason}</dd>` : ''}${category(r)}
        <dt>Assignee</dt><dd>${fact(r, r.assignee)}</dd><dt>Reporter</dt><dd>${fact(r, r.reporter || r.author)}</dd>
        <dt>Opened</dt><dd>${stamp(r, r.created_at)}</dd><dt>Updated</dt><dd>${stamp(r, r.updated_at)}</dd>
        <dt>Labels</dt><dd><span class="ph">not stored</span></dd><dt>Priority</dt><dd><span class="ph">not stored</span></dd>
        <dt>Description</dt><dd><span class="ph">not stored: sd shadow sync keeps no labels, priority or description</span></dd>
        <dt>Item</dt><dd>${r.item ? html`<a href="${window.shell.itemHref(r.item)}">sd:${r.item}</a>` : html`<span class="ph">${r.unread ? 'not read' : 'none filed under this issue'}</span>`}</dd></dl>
      ${r.unread ? html`<p class="why">The stored issue was not read: ${r.unread}. Read again tries again.</p>` : ''}
      <h3>Act</h3>${window.shell.commands.bar(id)}`);
    window.shell.commands.select(id);
    if (open) window.shell.openPane('tab-details');
  }
  function register() {
    const C = window.shell.commands, item = on => ({ id: `${on}.item`, on, label: 'Open item', does: 'Opens the work item filed under this issue.',
      key: 'i', risk: 'safe', when: o => !!o.item || 'no item is filed under this issue', cli: o => `sd task show ${o.item}`, run: o => window.shell.openItem(o.item) });
    const opens = (on, label, cli) => ({ id: `${on}.open`, on, label, does: `${label}: the issue in a new tab.`, key: 'o', icon: 'arrow-up-right',
      risk: 'safe', primary: () => true, when: o => !!o.url || 'the stored address is not a web address', cli,
      run: o => { window.open(o.url, '_blank', 'noopener'); return `${label} in a new tab`; } });
    // sd:6175: Hide and Unhide, the view state Contributions' Hide writes; Undo posts the other value. Nothing expires it.
    // pack sd:7787: on a GitHub issue each is a bulk command too, for Issue Intake's picked rows.
    const hides = on => [[true, 'hide', 'Hide', 'Hides this issue from its list and counts; Undo shows it again.', 'eye-off', 'Hidden', '. Hidden lists it.'],
      [false, 'unhide', 'Unhide', 'Shows this issue in its list again; Undo hides it.', 'eye', 'Unhidden', '']].map(([hidden, id, label, does, icon, done, after]) => (
      { id: `${on}.${id}`, on, label, does, key: 'h', icon, risk: 'undo', bulk: on === 'github issue',
        when: o => o.hidden === hidden ? (hidden ? 'already hidden' : 'not hidden') : STORE ? `Hide is off: ${STORE}` : true,
        cli: () => NO_VIEW_CLI,
        run: o => view(o, hidden).then(() => `${done} · ${o.label}${after}`),
        undo: o => view(o, !hidden) }));
    // pack sd:7708: Set category and the category list's commands; every one is a local view-state write with Undo.
    const off = () => STORE ? `Categories are off: ${STORE}` : true;
    REG_CAT = { id: 'jira issue.category', on: 'jira issue', label: 'Set category', key: 'g', risk: 'undo', bar: false,
      does: 'Puts this Jira issue in a category, or in none. Jira is not changed.',
      when: o => off() !== true ? off() : CATS.length ? true : 'no category yet: New category adds one',
      fields: o => [{ name: 'category', label: 'Category', value: o.category || byName()[0],
        options: [...byName().map(n => ({ value: n, label: n })), { value: '', label: 'None (Uncategorized)' }] }],
      cli: () => NO_CAT_CLI,
      run: (o, v) => { const was = o.category || null, to = v?.category || null;
        return categorize(o.key, to).then(() => ({ text: to ? `Category ${to} · ${o.label}` : `Category cleared · ${o.label}`, was })); },
      undo: (o, v) => categorize(o.key, v ? v.was : o.category || null) };
    // pack sd:7787: File as item, the intake row's button, in Details' Act bar and the shell's bulk bar: one POST
    // /api/items per row, as `sd task add --ref` files it in the issue's repo. Filing has no Undo: the item is the record.
    FILE_CMD = { id: 'github issue.file', on: 'github issue', label: 'File as item', key: 'f', risk: 'safe', bulk: true,
      does: 'Adds a task linked to this issue in its repo; the row leaves.',
      when: o => !o.intake ? 'only an Issue Intake row files an item here' : o.item ? `filed as sd:${o.item}`
        : BUSY.has(o.key) ? 'it is being filed now' : true,
      cli: o => `cd ${window.shell.shq(o.repo_path || '')} && sd task add --ref ${window.shell.shq(o.key)} ${window.shell.shq(o.title || '')}`,
      run: o => file(o.key).then(id => `Filed sd:${id} · ${o.label}`) };
    const listOf = w => w.categories;
    C.register(
      opens('jira issue', 'Open in Jira', o => `open ${window.shell.shq(o.url || '')}`), item('jira issue'), ...hides('jira issue'),
      opens('github issue', 'Open on GitHub', o => o.slug ? `gh issue view ${o.ref.replace('#', '')} --repo ${o.slug} --web` : `open ${window.shell.shq(o.url || '')}`),
      item('github issue'), ...hides('github issue'), FILE_CMD,
      REG_CAT,
      { id: 'issue categories.add', on: 'issue categories', label: 'New category', key: 'a', risk: 'undo',
        does: 'Adds a category to group your Jira issues by. Nothing is written to Jira.',
        when: () => off() !== true ? off() : CATS.length < 16 || 'at most 16 categories: remove one first',
        fields: () => [{ name: 'name', label: 'Name', required: true, placeholder: 'Ingestion' }], cli: () => NO_CAT_CLI,
        run: (o, v) => { const before = [...CATS];
          return categories({ categories: [...before, v.name], before }).then(w => ({ text: `Category ${v.name.trim()} added`, before, after: listOf(w) })); },
        undo: (o, v) => categories({ categories: v.before, before: v.after }) },
      { id: 'issue category.rename', on: 'issue category', label: 'Rename', key: 'r', risk: 'undo',
        does: 'Renames this category; its issues stay in it.', when: off,
        fields: o => [{ name: 'to', label: 'New name', required: true, value: o.name }], cli: () => NO_CAT_CLI,
        run: (o, v) => { const at = CATS.indexOf(o.name);
          return categories({ rename: o.name, to: v.to, before: [...CATS] }).then(w => ({ text: `Category ${o.name} renamed ${listOf(w)[at]}`, from: o.name, to: listOf(w)[at], after: listOf(w) })); },
        undo: (o, v) => categories({ rename: v.to, to: v.from, before: v.after }) },
      { id: 'issue category.remove', on: 'issue category', label: 'Remove', key: 'd', risk: 'undo',
        does: 'Removes this category; its issues go to Uncategorized. Undo puts them back.', when: off, cli: () => NO_CAT_CLI,
        run: o => { const before = [...CATS];
          return categories({ categories: before.filter(n => n !== o.name), before }).then(w => ({ text: `Category ${o.name} removed · its issues are uncategorized`, before, after: listOf(w) })); },
        undo: (o, v) => categories({ categories: v.before, before: v.after }) });
  }
  document.addEventListener('DOMContentLoaded', () => {
    register();
    document.addEventListener('shell:open', e => { const id = String(e.detail || ''); if (id.startsWith('iss:')) details(id); });
    // A page opened with ?row=iss:… shows its row once a read lists it.
    ['issues:read', 'intake:read'].forEach(t => document.addEventListener(t, () => { const id = window.shell.row(); if (id?.startsWith('iss:') && rowOf(id)) details(id, false); }));
  });
  window.issues = { file, details, register };
})();
