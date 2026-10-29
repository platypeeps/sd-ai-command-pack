// Your issues (sd:4628), on GitHub (sd:5781; Today drew them from sd:5645, Tasks before): each repo's Jira and GitHub
// issues assigned to or filed by the operator.
// Issue intake (sd:4840), GitHub's Intake view, is at the end.
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
// each with Undo. A hidden row leaves its list, the tally and the tab count; Open | Hidden | All (sd:6701), at the left of
// each list's filter bar and kept as ?hidden=1 or ?hidden=all, lists the hidden rows alone, with Unhide, or every row. A view store the read could not read hides nothing and turns
// both commands off with its reason.
(() => {
  const { html, put } = window.markup;
  const $ = id => document.getElementById(id);
  let ISSUES = [], STORE = '';
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
  function draw({ issues = [], error = '', github = '', store } = READ) {
    READ = { issues, error, github, store };
    ISSUES = error ? [] : issues; STORE = storeOff(store);
    // Every count below is of the rows in view: the unhidden ones, the hidden ones under Hidden, or both under All.
    const pool = ISSUES.filter(inView), open = pool.filter(isOpen), rows = closedToo() ? pool : open, L = window.shell?.list;
    const hiddenN = ISSUES.filter(r => r.hidden && (closedToo() || isOpen(r))).length, openN = ISSUES.filter(r => !r.hidden && (closedToo() || isOpen(r))).length;
    put($('issues'), error ? html`<tr class="empty"><td colspan="4">Issues could not be read: ${error}. Read again tries again.</td></tr>`
      : html`${rows.length ? rows.map(r => html`<tr${selected(r)}>
        <td class="ref">${r.url ? html`<a href="${r.url}">${r.tracker} ${r.ref}</a>` : html`${r.tracker} ${r.ref}`}</td>
        <td class="what">${title(r)}</td>
        <td class="repo">${r.repo}</td>
        <td class="why">${isOpen(r) ? r.reason : `${r.state} · ${r.reason}`}</td></tr>`)
      : html`<tr class="empty"><td colspan="4">${showHidden() ? `No ${closedToo() ? '' : 'open '}issue is hidden.`
        : `No ${closedToo() ? '' : 'open '}issue is assigned to you or filed by you.`}</td></tr>`}${
        github ? html`<tr class="empty"><td colspan="4">Your GitHub issues outside the repos' issue sources were not read: ${github}. Read again tries again.</td></tr>` : ''}`);
    put($('issues-tally'), pool.length && !error ? html`<span>${open.length} ${showHidden() ? 'hidden' : 'open'}</span>${closedToo() ? html`<span>${pool.length - open.length} closed in 7 d</span>` : ''}` : html``);
    if (L) put($('issues-filters'), error ? html`` : L.fbar(html`${hiddenSeg(openN, hiddenN)}${L.fseg('iss', 'State', [['open', open.length], ['closed', pool.length]].map(([v, n]) =>
      ({ v, pressed: closedToo() === (v === 'closed'), label: html`${v === 'open' ? 'open' : 'with closed'} <span class="n">${String(n)}</span>` })))}`));
    // The Your issues tab (sd:5080): the open rows not hidden, whichever list shows.
    window.shell?.view?.count('issues', error ? null : ISSUES.filter(r => isOpen(r) && !r.hidden).length);
    objects();
  }
  document.addEventListener('issues:read', e => draw(e.detail));
  // State: open, or with closed; the param is written around the page's others (shell.url keeps ?row=).
  function pickState(v) {
    const p = new URLSearchParams(location.search);
    if (v === 'closed') p.set('iss', 'closed'); else p.delete('iss');
    window.shell.url(p.toString()); draw();
    $('issues-filters').querySelector?.(`[data-v="${v}"]`)?.focus();
  }
  // Open | Hidden | All (sd:6175, sd:6701): one ?hidden= for both lists, as Contributions keeps it.
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
  const view = (o, hidden) => window.shell.post('/api/github/issues/view', { key: o.key, hidden })
    .then(v => { landed(o.key, hidden); window.githubIssues?.again(); return v; }, e => { window.githubIssues?.again(); throw e; });

  // Issue intake (sd:4840), on GitHub: each github_issues repo's open third-party issues no item carries (issues.intake over
  // sd_db.repos.intake_issues). File as item posts /api/items with the issue's title, repo and ref, the item `sd task add
  // --ref github:<owner>/<repo>#N` files; the row then names the item until the next read leaves it out. A refusal, such as
  // a ref another item already carries, stays on the row. Rows are keyed by that ref.
  let INTAKE = [], FAILED = '';
  const FILED = new Map(), REFUSED = new Map(), BUSY = new Set();
  function control(r) {
    if (FILED.has(r.key)) return html`<a href="${window.shell.itemHref(FILED.get(r.key))}">Filed #${FILED.get(r.key)}</a>`;
    return html`<button type="button" class="btn quiet sm" data-key="${r.key}"${BUSY.has(r.key) ? html` disabled` : ''}>File as item</button>
      ${REFUSED.has(r.key) ? html`<p class="refused" role="alert">Not filed: ${REFUSED.get(r.key)}</p>` : ''}`;
  }
  function drawIntake() {
    put($('intake'), FAILED ? html`<tr class="empty"><td colspan="5">Issue intake could not be read: ${FAILED}. Read again tries again.</td></tr>`
      : INTAKE.filter(inView).length ? html`${INTAKE.filter(inView).map(r => html`<tr${selected(r)}${BUSY.has(r.key) ? html` aria-busy="true"` : ''}>
        <td class="ref">${r.url ? html`<a href="${r.url}">GitHub ${r.ref}</a>` : html`GitHub ${r.ref}`}</td>
        <td class="what">${title(r)}</td>
        <td class="repo">${r.repo}</td>
        <td class="why">${r.author}</td>
        <td class="act">${control(r)}</td></tr>`)}`
      : html`<tr class="empty"><td colspan="5">${showHidden() ? 'No intake issue is hidden.' : 'No third-party issue waits for an item in a repo with GitHub issues on.'}</td></tr>`);
    const waiting = INTAKE.filter(r => !FILED.has(r.key) && !r.hidden).length, hiddenN = INTAKE.filter(r => r.hidden).length;
    put($('intake-tally'), INTAKE.length && !FAILED ? html`<span>${showHidden() ? `${hiddenN} hidden` : `${waiting} waiting`}</span>` : html``);
    const L = window.shell?.list;
    if (L) put($('intake-filters'), FAILED ? html`` : L.fbar(hiddenSeg(INTAKE.length - hiddenN, hiddenN)));
    window.shell?.view?.count('intake', FAILED ? null : waiting); // the Intake tab
    objects();
  }
  function file(key) {
    const r = INTAKE.find(x => x.key === key);
    if (!r || BUSY.has(key) || FILED.has(key)) return;
    BUSY.add(key); REFUSED.delete(key); drawIntake();
    window.shell.post('/api/items', { title: r.title, repo: r.repo_path, ref: r.key })
      .then(out => { FILED.set(key, out.item.id); }, e => { REFUSED.set(key, e.message); })
      .finally(() => { BUSY.delete(key); drawIntake(); });
  }
  document.addEventListener('intake:read', e => {
    const { intake = [], error = '', store } = e.detail || {};
    INTAKE = intake; FAILED = error; STORE = storeOff(store); FILED.clear(); REFUSED.clear(); BUSY.clear(); drawIntake();
  });
  document.addEventListener('click', e => {
    const s = e.target?.closest?.('#issues-filters [data-f="iss"]');
    if (s) return pickState(s.dataset.v);
    const h = e.target?.closest?.('#issues-filters [data-aside="hidden"], #intake-filters [data-aside="hidden"]');
    if (h) return pickHidden(h.closest?.('#intake-filters') ? 'intake-filters' : 'issues-filters', h.dataset.v);
    const b = e.target && e.target.closest && e.target.closest('#intake button[data-key]');
    if (b) return file(b.dataset.key);
    const opened = e.target?.closest?.('[data-iss-open]');
    if (opened) return details(opened.dataset.issOpen);
    const tr = e.target?.closest && !e.target.closest('a, button') && e.target.closest('#issues tr[data-id], #intake tr[data-id]');
    if (tr) details(tr.dataset.id);
  });

  // ---------- Details (sd:5877) ----------
  // Both lists' rows by object id; an intake row filed here names its item until the next read.
  const rows = () => [...ISSUES, ...(FAILED ? [] : INTAKE).map(r => FILED.has(r.key) ? { ...r, item: FILED.get(r.key) } : r)];
  const rowOf = id => rows().find(r => oid(r) === id);
  const TYPE = { GitHub: 'github issue', Jira: 'jira issue' };
  const typeOf = r => TYPE[r.tracker || 'GitHub'];
  let PUT = new Set();
  // Each draw puts one command object per row; a row no read lists is retired, so no command runs on it.
  function objects() {
    const C = window.shell?.commands; if (!C) return;
    const keep = new Set();
    rows().forEach(r => { keep.add(oid(r)); C.put({ id: oid(r), type: typeOf(r), label: `${r.tracker || 'GitHub'} ${r.ref} ${r.title}`.trim(),
      url: r.url, item: r.item, ref: r.ref, slug: r.slug, key: r.key, hidden: !!r.hidden }); });
    PUT.forEach(id => { if (!keep.has(id)) C.put({ id, type: 'not listed', label: `${C.get(id)?.label || id} (no longer listed)` }); });
    PUT = keep;
  }
  // A fact the store did not record says so; one it could not read says that.
  const ph = r => html`<span class="ph">${r.unread ? 'not read' : 'not stored'}</span>`;
  const fact = (r, v) => v || ph(r);
  const stamp = (r, v) => v ? html`<time class="rel" data-long datetime="${v}"></time>` : ph(r);
  function details(id, open = true) {
    const r = rowOf(id); if (!r) return;
    const tracker = r.tracker || 'GitHub', where = tracker === 'Jira' ? 'in Jira' : 'on GitHub';
    document.querySelectorAll('#issues tr[data-id], #intake tr[data-id]').forEach(tr => tr.setAttribute('aria-selected', String(tr.dataset.id === id)));
    put($('details'), html`<p class="kind">${tracker} issue · ${r.state || 'state not stored'}</p>
      <h2>${r.title || r.ref}</h2>
      <dl><dt>Issue</dt><dd>${tracker} ${r.ref}</dd><dt>Repo</dt><dd>${r.repo}${r.slug ? ` · ${r.slug}` : ''}</dd>
        <dt>State</dt><dd>${fact(r, r.state)}${r.status ? ` · ${r.status}` : ''}</dd>
        ${r.reason ? html`<dt>Why</dt><dd>${r.reason}</dd>` : ''}
        <dt>Assignee</dt><dd>${fact(r, r.assignee)}</dd><dt>Reporter</dt><dd>${fact(r, r.reporter || r.author)}</dd>
        <dt>Opened</dt><dd>${stamp(r, r.created_at)}</dd><dt>Updated</dt><dd>${stamp(r, r.updated_at)}</dd>
        <dt>Labels</dt><dd><span class="ph">not stored</span></dd><dt>Priority</dt><dd><span class="ph">not stored</span></dd>
        <dt>Description</dt><dd><span class="ph">not stored: sd shadow sync keeps no labels, priority or description</span></dd>
        <dt>Item</dt><dd>${r.item ? html`<a href="${window.shell.itemHref(r.item)}">sd:${r.item}</a>` : html`<span class="ph">${r.unread ? 'not read' : 'none filed under this issue'}</span>`}</dd></dl>
      ${r.unread ? html`<p class="why">The stored issue was not read: ${r.unread}. Read again tries again.</p>` : ''}
      ${r.url ? html`<p><a href="${r.url}" target="_blank" rel="noopener noreferrer">Open ${r.ref} ${where}</a></p>` : ''}
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
    const hides = on => [[true, 'hide', 'Hide', 'Hides this issue from its list and counts; Undo shows it again.', 'eye-off', 'Hidden', '. Hidden lists it.'],
      [false, 'unhide', 'Unhide', 'Shows this issue in its list again; Undo hides it.', 'eye', 'Unhidden', '']].map(([hidden, id, label, does, icon, done, after]) => (
      { id: `${on}.${id}`, on, label, does, key: 'h', icon, risk: 'undo',
        when: o => o.hidden === hidden ? (hidden ? 'already hidden' : 'not hidden') : STORE ? `Hide is off: ${STORE}` : true,
        cli: () => NO_VIEW_CLI,
        run: o => view(o, hidden).then(() => `${done} · ${o.label}${after}`),
        undo: o => view(o, !hidden) }));
    C.register(
      opens('jira issue', 'Open in Jira', o => `open ${window.shell.shq(o.url || '')}`), item('jira issue'), ...hides('jira issue'),
      opens('github issue', 'Open on GitHub', o => o.slug ? `gh issue view ${o.ref.replace('#', '')} --repo ${o.slug} --web` : `open ${window.shell.shq(o.url || '')}`),
      item('github issue'), ...hides('github issue'));
  }
  document.addEventListener('DOMContentLoaded', () => {
    register();
    document.addEventListener('shell:open', e => { const id = String(e.detail || ''); if (id.startsWith('iss:')) details(id); });
    // A page opened with ?row=iss:… shows its row once a read lists it.
    ['issues:read', 'intake:read'].forEach(t => document.addEventListener(t, () => { const id = window.shell.row(); if (id?.startsWith('iss:') && rowOf(id)) details(id, false); }));
  });
  window.issues = { file, details, register };
})();
