// GitHub > Dependabot (pack sd:7515): each managed repository's open Dependabot alerts, from what sd shadow sync stored
// (/api/github/dependabot, health_screen.dependabot_document); the read calls no GitHub API. It reads when the view first
// shows, on Read again, and after Refresh from GitHub ends (github.js calls githubDependabot.again()).
// One ledger, one band per repository, worst severity first: the band names the repo, its open count ("100+" past
// GitHub's first page) and its worst severity, and the shell's table grammar makes it a fold (data-band keys it, so a
// count that moves keeps it shut). Its Fix is Health's (commands.js dependabotFix): it files or reuses the repo's
// dependabot:<owner>/<repo> item and starts a builder on it. Under the band, one row per stored alert, critical first:
// severity, package, advisory and Open, the alert's own page on GitHub in a new tab. Repositories with alerts off, not
// read or archived are one note under the table, never groups. A failed read is the state slot's, never an empty list.
(() => {
  const { html, put, plural } = window.markup;
  const $ = id => document.getElementById(id);
  const COLS = 5;
  // design.md's state glyphs: critical and high are warning, medium and low caution, anything else unknown.
  const STATE = { critical: 'warning', high: 'warning', medium: 'caution', low: 'caution' };
  const GLYPH = { warning: '■', caution: '▲', unknown: '▨' };
  const RANK = ['critical', 'high', 'medium', 'low', 'unknown'];
  const stateOf = level => STATE[level] || 'unknown';
  const mark = level => html`<span class="g-${stateOf(level)}" aria-hidden="true">${GLYPH[stateOf(level)]}</span>`;
  let started = false, reads = 0, DOC = null;

  function alertRow(g, a) {
    const ids = [a.ghsa, a.cve].filter(Boolean).join(' · ');
    const fixed = a.patched ? `fixed in ${a.patched}` : 'no patched version yet';
    const rank = RANK.indexOf(a.severity);
    return html`<tr data-alert="${`${g.name}#${a.number}`}">
      <td class="sev" data-sort-value="${String(rank < 0 ? RANK.length : rank)}">${mark(a.severity)} ${a.severity}</td>
      <td class="pkg"><span class="name">${a.package || 'package not stored'}</span><span class="file">${[a.ecosystem, a.manifest].filter(Boolean).join(' · ') || '—'}</span></td>
      <td class="adv"><span>${a.summary || 'no advisory summary stored'}</span><span class="file">${ids ? `${ids} · ` : ''}${fixed}</span></td>
      <td class="when">${a.created_at ? html`<time class="rel" datetime="${a.created_at}"></time>` : html`<span class="ph">not stored</span>`}</td>
      <td class="acts">${a.url ? html`<a class="btn quiet sm" href="${a.url}" target="_blank" rel="noopener" aria-label="${`Open ${g.name} alert ${a.number} on GitHub`}">Open</a>`
        : html`<span class="ph">no link</span>`}</td></tr>`;
  }
  function band(g) {
    const counts = Object.entries(g.severity || {}).map(([level, n]) => `${n} ${level}`).join(' · ');
    return html`<tr class="band" data-band="${g.id}"><td colspan="${String(COLS)}">${mark(g.worst)} ${g.name}<span class="n">${g.shown} open · worst ${g.worst}${counts ? ` · ${counts}` : ''}${g.more ? ' · first page only' : ''}</span><button class="btn quiet sm" type="button" data-tkeep="" data-cmd="dependabot alerts.fix" data-obj="${g.id}">Fix</button></td></tr>`;
  }
  function group(g) {
    if (!g.alerts) return html`${band(g)}<tr class="empty"><td colspan="${String(COLS)}">The alerts' details are not stored yet; the next sd shadow sync stores them. Fix works from the counts.</td></tr>`;
    // A count past the page read (more) lists the first page's alerts only; the band says so.
    return html`${band(g)}${g.alerts.map(a => alertRow(g, a))}`;
  }
  function notes(d) {
    const said = [];
    if (d.off.length) said.push(`Alerts off in ${plural(d.off.length, 'repo')}: ${d.off.join(', ')}.`);
    if (d.unread.length) said.push(`Not read in ${plural(d.unread.length, 'repo')}: ${d.unread.join('; ')}.`);
    if (d.clean) said.push(`No open alert in ${plural(d.clean, 'repo')}.`);
    if (d.archived) said.push(`Archived ${plural(d.archived, 'repo')} left out.`);
    return said.join(' ');
  }
  function draw() {
    const d = DOC;
    const count = d && !d.error ? d.groups.reduce((n, g) => n + g.open, 0) : null;
    window.shell.view?.count?.('dependabot', count);
    if (!d) return;
    if (d.error) {
      put($('dependabot-tally'), html``);
      put($('dependabot'), html`<tr class="empty"><td colspan="${String(COLS)}">The alerts were not read: ${d.error}</td></tr>`);
      put($('dependabot-notes'), html``);
      return;
    }
    d.groups.forEach(g => window.shell.commands.put({ ...g, label: g.name }));
    const more = d.groups.some(g => g.more) ? '+' : '';
    put($('dependabot-tally'), html`${d.groups.length ? `${count}${more} open in ${plural(d.groups.length, 'repo')}` : ''}`);
    put($('dependabot'), d.groups.length ? html`${d.groups.map(group)}`
      : html`<tr class="empty"><td colspan="${String(COLS)}">${d.managed ? 'No open Dependabot alert in a managed repo that was read.' : 'No managed repository: sd shadow sync reads alerts for managed repositories only.'}</td></tr>`);
    put($('dependabot-notes'), html`${notes(d)}${d.at ? html` Alerts read <time class="rel" datetime="${d.at}"></time>.` : ''}`);
  }
  async function load() {
    const n = ++reads; started = true;
    let doc;
    try { doc = await window.shell.getJSON('/api/github/dependabot'); } catch (e) { doc = { error: e.message }; }
    if (n !== reads) return; // of overlapping reads only the newest draws
    DOC = doc; draw();
  }
  document.addEventListener('DOMContentLoaded', () => window.shell.commands.register(window.commands.dependabotFix()));
  document.addEventListener('shell:view', e => { if (e.detail && e.detail.id === 'dependabot' && !started) load(); });
  // github.js reads again after Refresh from GitHub ends and on Read again; a view never shown stays unread.
  window.githubDependabot = { again: () => (started ? load() : null) };
})();
