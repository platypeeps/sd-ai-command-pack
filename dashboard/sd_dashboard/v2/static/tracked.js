// GitHub > Tracked (pack sd:7525, Operations > Trackers until then): every open pull request and issue sd shadow sync
// keeps, of every tracker, watched and Jira rows too (/api/github/tracked, trackers_screen.document); the read calls no
// tracker. It reads when the view first shows, on Read again, and after Refresh from GitHub ends (github.js calls
// githubTracked.again()). One row per tracker row, last seen first; its reference links to the tracker when the URL is
// https with a host. Each tracker's sync health is the line under the table. A failed read is the table's one row
// naming it, never an empty list.
(() => {
  const { html, put, plural } = window.markup;
  const $ = id => document.getElementById(id);
  const COLS = 6;
  const KIND = { pull: 'pull request', issue: 'issue' };
  const TRACKER = { github: 'GitHub', jira: 'Jira' };
  let started = false, reads = 0;

  const row = r => html`<tr data-key="${r.key}">
    ${r.url ? html`<td class="ref"><a href="${r.url}" target="_blank" rel="noopener noreferrer">${r.ref}</a></td>` : html`<td class="ref">${r.ref}</td>`}
    <td class="what">${r.title}</td><td class="repo">${r.repo}</td><td class="why">${`${TRACKER[r.tracker] || r.tracker} ${KIND[r.kind] || r.kind}`}</td><td class="who">${r.author}</td>
    <td class="when">${r.last_seen ? html`<time class="rel" datetime="${r.last_seen}"></time>` : html`<span class="ph">not recorded</span>`}</td></tr>`;
  const health = t => html`${t.tracker}: ${t.state === 'never' ? 'never synced' : t.state}${t.last_success_at
    ? html` · last successful sync <time class="rel" datetime="${t.last_success_at}"></time>` : ''}${t.reason ? ` · ${t.reason}` : ''}`;

  function draw(d) {
    window.shell.view?.count?.('tracked', d.error ? null : d.rows.length);
    if (d.error) {
      put($('tracked-tally'), html``);
      put($('tracked'), html`<tr class="empty"><td colspan="${String(COLS)}">The tracked rows were not read: ${d.error}</td></tr>`);
      put($('tracked-health'), html``);
      return;
    }
    put($('tracked-tally'), html`${d.rows.length ? `${plural(d.rows.length, 'open row')}` : ''}`);
    put($('tracked'), d.rows.length ? html`${d.rows.map(row)}`
      : html`<tr class="empty"><td colspan="${String(COLS)}">No open row in the local snapshot.</td></tr>`);
    put($('tracked-health'), html`${d.trackers.map((t, i) => html`${i ? '; ' : ''}${health(t)}`)}`);
  }
  async function load() {
    const n = ++reads; started = true;
    let doc;
    try { doc = await window.shell.getJSON('/api/github/tracked'); } catch (e) { doc = { error: e.message }; }
    if (n !== reads) return; // of overlapping reads only the newest draws
    draw(doc);
  }
  document.addEventListener('shell:view', e => { if (e.detail && e.detail.id === 'tracked' && !started) load(); });
  // github.js reads again after Refresh from GitHub ends and on Read again; a view never shown stays unread.
  window.githubTracked = { again: () => (started ? load() : null) };
})();
