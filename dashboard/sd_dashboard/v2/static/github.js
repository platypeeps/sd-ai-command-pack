// GitHub (sd:5781): the page script. It loads before issues.js, today-github.js and shell.js, which read what it declares.
// Three views: Pull requests (today-github.js, sd:5608), Your issues (sd:4628) and Intake (sd:4840), Today's GitHub and
// Issues views until sd:5781. Your issues and Intake are one read, /api/github/issues (issues.document, issues.intake),
// made when either view first shows and on Read again; issues.js draws them from the issues:read and intake:read events,
// and counts each tab. A failed read is each table's row naming it, never an empty list.
// Sync now (sd:6175): the same read carries shadow-sync-nightly, the job that runs sd shadow sync (issues.sync_job). Sync
// now is the shared Run now (commands.js, jobs.retry), which posts /api/jobs/<name>/retry with the revision the read
// brought, as HOA's Refresh now does. launchd runs it in the background: while it runs the page reads again every
// SYNC_POLL ms, so the read after it ends draws both views from what it stored.
window.PAGE_VIEWS = [{ id: 'pulls', label: 'Pull requests' }, { id: 'issues', label: 'Your issues', key: 'y' },
  { id: 'intake', label: 'Intake' }];
(() => {
  const SYNC_POLL = 15000, JOB = 'job:shadow-sync-nightly';
  let reads = 0, started = false, SYNC = null, polling = 0;
  async function load() {
    const n = ++reads; started = true;
    let detail;
    try { detail = await window.shell.getJSON('/api/github/issues'); } catch (e) { detail = { issues_error: e.message, intake_error: e.message }; }
    if (n !== reads) return; // of overlapping reads only the newest draws
    document.dispatchEvent(new CustomEvent('issues:read', { detail: { issues: detail.issues || [], error: detail.issues_error || '', github: detail.github_error || '', store: detail.store } }));
    document.dispatchEvent(new CustomEvent('intake:read', { detail: { intake: detail.intake || [], error: detail.intake_error || '', store: detail.store } }));
    SYNC = detail.sync || null; drawSync();
    if (SYNC?.state === 'running') poll();
  }
  function poll() { if (!polling) polling = setTimeout(() => { polling = 0; load(); }, SYNC_POLL); }

  // The job's facts in the shape jobs.retry reads; a job not installed or not read is off with its reason.
  const facts = () => ({ name: SYNC?.name || 'shadow-sync-nightly', service: SYNC?.service, failed: SYNC?.state === 'failed', exit: SYNC?.last_exit,
    capability: !SYNC ? { allowed: false, reason: 'the sync job was not read' } : SYNC.error ? { allowed: false, reason: SYNC.error } : SYNC.capabilities?.retry });
  function drawSync() {
    const { html, put } = window.markup;
    if (!SYNC) return ['issues-sync', 'intake-sync'].forEach(id => put(document.getElementById(id), html``));
    window.shell.commands.put({ id: JOB, type: 'job', label: SYNC.name, job: SYNC.name });
    const c = facts().capability, running = SYNC.state === 'running', off = !c?.allowed;
    const said = running ? 'The sync is running in the background; Your issues and Intake read again when it ends.'
      : off ? `Sync now is off: ${c?.reason || 'launchd refuses a run now'}`
        : 'The sync runs in the background; Your issues and Intake read again when it ends.';
    const line = html`<button class="btn quiet sm" type="button" data-cmd="jobs.retry" data-obj="${JOB}"${off ? html` disabled` : ''}>Sync now</button> ${said}`;
    ['issues-sync', 'intake-sync'].forEach(id => put(document.getElementById(id), line));
  }
  document.addEventListener('DOMContentLoaded', () => {
    const retry = window.commands.retry({ job: facts,
      run: () => window.shell.post(`/api/jobs/${encodeURIComponent(SYNC.name)}/retry`, { revision: SYNC.revision }).then(
        out => { poll(); return window.commands.answered(out, SYNC.name, 'started', 'Sync started in the background · Your issues and Intake read again when it ends'); },
        e => { load(); throw e; }) });
    window.shell.commands.register({ ...retry, label: 'Sync now', does: 'Starts sd shadow sync now, in the background.', primary: () => true });
  });
  document.addEventListener('shell:view', e => { if (['issues', 'intake'].includes(e.detail && e.detail.id) && !started) load(); });
  // Read again (sd:5638): every view that has been read reads again; Pull requests is today-github.js's own read.
  window.PAGE_AGAIN = { title: 'Read GitHub again', run: () => Promise.all([window.githubPulls && window.githubPulls.again(), started && load()]) };
  // issues.js reads again after a Hide or Unhide (sd:6175).
  window.githubIssues = { again: () => load() };
})();
