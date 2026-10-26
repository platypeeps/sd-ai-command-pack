// Queue (sd:2585): /api/queue (queue_screen.py). One ledger row per active lane (sd:5921): a merging · next · blocked pip
// strip, the head of lane and its one primary action. The open lane's entries show in Details, one row per item in its
// state: merging, next, building, blocked, cancelled, landed. Lanes with no row to draw fold into one Idle line under the
// ledger. Up, down, top, hold, release and cancel post /api/queue/move with the lane's
// revision; the server runs sd-ship lane move|hold|release|cancel|retry, refuses a stale revision, and the page reads again.
// Cancel asks first (sd:3012). A cancelled row offers Re-queue (sd:3398) when the installed pack's retry takes a cancelled
// entry (DOC.requeue, pack sd:3389): it posts action `requeue` with the head the row showed, and the server runs
// `lane retry --expected-head`, which refuses a moved branch, a newer entry or a merged head. It runs at once, as Retry
// does: Cancel takes it back. Without the pack's support the row says why Re-queue is off (DOC.requeue_off).
// A running row with a claim offers Release (sd:3337, D3 of pack sd:3174): it asks first, naming the holder, claim age and
// what the pack does at that step, then posts action `reclaim` with the claim the row showed (`<holder token>:<step>`);
// the server runs `lane cancel --expected-claim`, so a claim that moved on since the read releases nothing.
// A blocked row offers Retry (lane retry) and, on a runner_merge=manual repo, Approve (lane retry --manual), only when the
// installed pack's retry takes --expected-head (DOC.retry). Each button carries the head its row showed, and the server
// passes it on, so neither acts on an entry that ended at another head since the read. Retry runs at once: Cancel takes
// the new entry back. Approve asks first: it grants the runner the merge to the default branch, which nothing takes back.
// Show draws the active rows by default: merging, next (a held one keeps its place), building and blocked, each still
// waiting on the runner, a builder or the operator. All adds the ended ones, cancelled and landed; ?show=all keeps it.
// Each lane's counts read every row, whatever Show draws (Queue has no rail badge since sd:5921).
(() => {
  const { html, put, plural } = window.markup;
  const $ = id => document.getElementById(id);
  const G = { live: ['live', '●'], ok: ['ok', '●'], caution: ['caution', '▲'], warning: ['warning', '■'], queued: ['queued', '◌'], unknown: ['unknown', '▨'] };
  const ICON = n => html`<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const HM = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const at = s => s ? HM.format(new Date(s)) : 'not recorded';
  const dur = s => s == null ? 'not recorded' : s < 3600 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}m`;
  const TREND = { rising: '↑ rising', falling: '↓ falling', steady: '→ steady' };
  const ACTIVE = ['merging', 'next', 'building', 'blocked'];
  let DOC = null, busy = false, show = 'active', open = null; // open: the lane path Details shows
  const drawn = l => show === 'all' ? l.rows : l.rows.filter(r => ACTIVE.includes(r.state));
  const said = {}; // lane path -> { ok, text }: the last write's result, shown in its lane until the next one
  // Builds (pack sd:6095): /api/queue/builds, read beside the lanes; BUILT is its document, BUILT_ERR why it was not read.
  let BUILT = null, BUILT_ERR = '', builtSaid = null;

  const btn = (lane, r, act, label, icon, off) => html`<button class="btn quiet sm" type="button" data-act="${act}" data-item="${String(r.item)}" data-repo="${lane.path}" aria-label="${label} sd:${String(r.item)}" title="${label}"${off || busy ? html` disabled` : ''}>${ICON(icon)}</button>`;
  function controls(lane, r, last) {
    return html`<div class="ctl" role="group" aria-label="Order of sd:${String(r.item)}">${btn(lane, r, 'up', 'Move up', 'arrow-up', r.position === 1)}${btn(lane, r, 'down', 'Move down', 'arrow-down', r.position === last)}<button class="btn quiet sm" type="button" data-act="top" data-item="${String(r.item)}" data-repo="${lane.path}" aria-label="Move sd:${String(r.item)} to the top"${r.position === 1 || busy ? html` disabled` : ''}>Top</button><button class="btn quiet sm" type="button" data-act="${r.held ? 'release' : 'hold'}" data-item="${String(r.item)}" data-repo="${lane.path}"${busy ? html` disabled` : ''}>${r.held ? 'Release' : 'Hold'}</button><button class="btn quiet sm" type="button" data-act="cancel" data-item="${String(r.item)}" data-repo="${lane.path}" aria-label="Cancel sd:${String(r.item)} in this lane"${busy ? html` disabled` : ''}>Cancel…</button></div>`;
  }
  const one = (lane, r, act, label, aria) => html`<button class="btn quiet sm" type="button" data-act="${act}" data-item="${String(r.item)}" data-head="${r.expected_head}" data-repo="${lane.path}" aria-label="${aria}"${busy ? html` disabled` : ''}>${label}</button>`;
  const retry = (lane, r) => one(lane, r, 'retry', 'Retry', `Retry sd:${r.item}: queue it again at the same head`);
  function again(lane, r) {
    if (!DOC.retry) return html`<span></span>`;
    return html`<div class="ctl" role="group" aria-label="Unblock sd:${String(r.item)}">${retry(lane, r)}${lane.runner_merge === 'manual' ? one(lane, r, 'approve', 'Approve…', `Approve sd:${r.item}: queue it again with the merge granted`) : ''}</div>`;
  }
  function back(lane, r) {
    if (!DOC.requeue) return html`<span></span>`;
    return html`<div class="ctl" role="group" aria-label="Cancel of sd:${String(r.item)}"><button class="btn quiet sm" type="button" data-act="requeue" data-item="${String(r.item)}" data-head="${r.expected_head}" data-repo="${lane.path}" aria-label="Re-queue sd:${String(r.item)} at head ${r.head}"${busy ? html` disabled` : ''}>Re-queue</button></div>`;
  }
  function free(lane, r) {
    if (!r.claim) return html`<span></span>`;
    return html`<div class="ctl" role="group" aria-label="Claim of sd:${String(r.item)}"><button class="btn quiet sm" type="button" data-act="reclaim" data-item="${String(r.item)}" data-claim="${r.claim}" data-repo="${lane.path}" aria-label="Release sd:${String(r.item)} from ${r.host || 'its holder'}"${busy ? html` disabled` : ''}>Release…</button></div>`;
  }
  // Each state's glyph, label and fact line. A state's glyph carries it; colour only repeats it. A cancelled row borrows
  // queued's glyph (the foundation has five) and names itself to a screen reader as cancelled.
  const VIEW = {
    merging: r => [r.lease_passed ? G.caution : G.live, 'MERGING', html`<b>${r.step || 'step not recorded'}</b> on <b>${r.host || 'host not recorded'}</b> · claimed ${r.claim_age == null ? 'at a time not recorded' : `${dur(r.claim_age)} ago`} · ${r.lease_until ? `lease ${r.lease_passed ? 'passed' : 'to'} ${at(r.lease_until)}` : 'lease not recorded'} · head ${r.head || 'not recorded'}`],
    next: r => [r.held ? G.caution : G.queued, `${r.held ? 'HELD' : 'NEXT'} ${r.position}`, html`gate <b>${r.gate}</b>${r.gate_summary ? ` (${r.gate_summary})` : ''} · head ${r.head || 'not recorded'}${r.held ? ' · skipped until released' : ''}`],
    building: r => [{ running: G.live, pass: G.ok, fail: G.warning }[r.gate] || G.unknown, 'BUILDING', html`gate <b>${r.gate}</b>${r.summary ? ` · ${r.summary}` : ''}${r.head ? ` · head ${r.head}` : ''} · log changed ${at(new Date(r.changed * 1000).toISOString())}`],
    blocked: r => [G.caution, 'BLOCKED', html`<b>${r.who} acts</b> · ${r.status}${r.step ? ` at ${r.step}` : ''} · ${r.reason} · head ${r.head || 'not recorded'}`],
    cancelled: r => [[...G.queued, 'cancelled'], 'CANCELLED', html`cancelled at ${at(r.finished)} · head ${r.head || 'not recorded'}${DOC.requeue ? '' : ` · Re-queue off: ${DOC.requeue_off || 'not known whether the pack takes it'}`}`],
    landed: r => [G.ok, 'LANDED', html`${r.pr ? `PR #${r.pr}` : 'PR not named'} · merge ${r.commit || 'not recorded'} · ${at(r.finished)}`],
  };
  // Each entry row is a command object (sd:5064): its menu offers Adversarial review of the worktree the lane recorded.
  // A building row is a builder's gate log, not an entry, so it has none.
  const entryId = (lane, r) => `entry:${lane.path}:${r.item}`;
  function putEntries() {
    const C = window.shell.commands;
    DOC.lanes.forEach(l => l.rows.filter(r => r.state !== 'building').forEach(r => C.put({ id: entryId(l, r), type: 'entry', label: `sd:${r.item}`, item: r.item, worktree: r.worktree, repo: l.repo })));
  }
  function row(lane, r, last) {
    const [g, st, facts] = VIEW[r.state](r);
    const subject = r.state === 'building' ? html`<code>${r.builder}</code>` : html`<code>sd:${String(r.item)}</code>${r.title}`;
    const ctl = r.state === 'next' ? controls(lane, r, last) : r.state === 'blocked' ? again(lane, r) : r.state === 'cancelled' ? back(lane, r) : r.state === 'merging' ? free(lane, r) : html``;
    const id = r.state === 'building' ? null : entryId(lane, r);
    return html`<li class="qrow" data-state="${r.state}"${r.held ? html` data-held=""` : ''}><span class="g g-${g[0]}" aria-hidden="true">${g[1]}</span><span class="st">${st}</span><span class="s"><span><span class="sr">${g[2] || g[0]} · </span>${subject}</span><small>${facts}</small></span><span class="ends">${ctl}${id ? window.shell.commands.rowActions(id) : ''}</span></li>`;
  }
  const count = (l, st) => l.rows.filter(r => r.state === st).length;
  function lane(l) {
    const last = count(l, 'next'), s = said[l.path], rows = drawn(l), n = st => count(l, st);
    return html`<section class="lane" aria-labelledby="lane-${l.repo}"><header><h2 id="lane-${l.repo}">${l.repo}</h2><span class="host">lane on ${l.host}</span><span class="n">${n('merging')} merging · ${last} next · ${n('blocked')} blocked · ${n('landed')} landed today</span><span class="src">${l.lane}</span></header>
      ${s ? (s.ok ? html`<p class="done" role="status">${s.text}</p>` : html`<p class="fail" role="alert">${s.text}</p>`) : ''}
      ${rows.length ? html`<ul class="qrows">${rows.map(r => row(l, r, last))}</ul>` : html`<p class="done">${l.rows.length ? 'Nothing active in this lane; All shows its ended rows.' : 'Nothing queued, gating or landed today in this lane.'}</p>`}</section>`;
  }
  // A lane row (sd:5921): the head of lane is its first blocked entry, else the one merging, else the next ones, else a
  // builder; the primary action is that entry's Retry or Release, else Entries, which opens the lane in Details.
  function head(l) {
    const first = st => l.rows.find(r => r.state === st), b = first('blocked'), m = first('merging'), g = first('building');
    const next = l.rows.filter(r => r.state === 'next');
    if (b) return [G.warning, `sd:${b.item} blocked${b.step ? ` at ${b.step}` : ''}: ${b.reason}`, DOC.retry ? retry(l, b) : null];
    if (m) return [m.lease_passed ? G.caution : G.live, `sd:${m.item} merging · ${m.step || 'step not recorded'} on ${m.host || 'host not recorded'}`, m.claim ? free(l, m) : null];
    if (next.length) return [G.queued, `next: ${next.map(r => `sd:${r.item}${r.held ? ' (held)' : ''}`).join(', ')}`, null];
    if (g) return [G.live, `building: ${g.builder}`, null];
    return [G.ok, `${count(l, 'landed')} landed, ${count(l, 'cancelled')} cancelled today`, null];
  }
  const pip = (n, on) => html`<span class="pip${n ? on : ''}">${String(n)}</span>`;
  function laneRow(l) {
    const [g, line, primary] = head(l), [m, n, b] = ['merging', 'next', 'blocked'].map(st => count(l, st));
    return html`<tr data-lane="${l.path}"${open === l.path ? html` aria-selected="true"` : ''}><td class="g g-${g[0]}" title="${g[0]}">${g[1]}</td><td class="what"><button type="button" class="pick" data-open="${l.path}">${l.repo}</button><small>${l.host}</small></td><td class="pipe" aria-label="${m} merging, ${n} next, ${b} blocked">${pip(m, ' on')}${pip(n, ' on')}${pip(b, ' warn')}</td><td class="why">${line}</td><td class="num">${String(count(l, 'landed'))}</td><td class="act">${primary || html`<button class="btn quiet sm" type="button" data-open="${l.path}">Entries</button>`}</td></tr>`;
  }
  const IDLE_NAMED = 6; // idle lanes that landed today, by name, before "N more"
  function idleLine(idle) {
    const landed = idle.filter(l => count(l, 'landed')), quiet = idle.length - landed.length;
    const named = landed.slice(0, IDLE_NAMED).map(l => `${l.repo} ${count(l, 'landed')}`).join(' · ');
    return [landed.length ? `Idle, landed today: ${named}${landed.length > IDLE_NAMED ? ` · ${landed.length - IDLE_NAMED} more` : ''}.` : '',
      quiet ? `Idle, quiet: ${plural(quiet, 'lane')}.` : ''].filter(Boolean).join(' ');
  }
  // Times (pack sd:6006): each lane's last 7 days from its history rows, median wait (enqueue to claim) and gate time
  // (speculative gate plus prepare), and its slowest entry, enqueue to end. A lane with no entry folds into one line; a
  // read that failed is its own row. A median wait past an hour says the lane run files the parallel-lanes question.
  const mins = s => s == null ? 'none ended' : dur(Math.round(s));
  function timesTable() {
    const read = DOC.lanes.filter(l => l.times && (l.times.error || l.times.entries)), quiet = DOC.lanes.length - read.length;
    const days = (read.find(l => l.times.days) || { times: { days: 7 } }).times.days;
    if (!read.length) return html`<p class="idle">No lane ran an entry in the last ${String(days)} days.</p>`;
    const cells = l => l.times.error ? html`<td colspan="4" class="why">▨ not read: ${l.times.error}</td>`
      : html`<td class="num">${String(l.times.entries)}</td><td class="num"${l.times.over ? html` data-over=""` : ''}>${mins(l.times.wait)}</td><td class="num">${mins(l.times.gate)}</td><td class="why">${l.times.slowest ? html`<code>sd:${String(l.times.slowest.item)}</code> ${l.times.slowest.title} · ${mins(l.times.slowest.total)}` : 'none ended'}</td>`;
    const over = read.filter(l => l.times.over);
    return html`<h2 class="times-h">Last ${String(days)} days</h2><table class="ledger times" aria-label="Wait and gate time per lane, last ${String(days)} days"><thead><tr><th scope="col">Lane</th><th scope="col" class="num">Entries</th><th scope="col" class="num">Median wait</th><th scope="col" class="num">Median gate</th><th scope="col">Slowest entry</th></tr></thead>
      <tbody>${read.map(l => html`<tr><td class="what">${l.repo}</td>${cells(l)}</tr>`)}</tbody></table>
      ${over.map(l => html`<p class="over">▲ ${l.repo}: median wait past 1 h. The lane run files the parallel-lanes question.</p>`)}${quiet ? html`<p class="idle">No entry in ${String(days)} days: ${plural(quiet, 'lane')}.</p>` : ''}`;
  }
  // Builds panel (pack sd:6095): one row per open build run, above the lanes. Its state is one of four: working; waiting
  // on me (the run is held, or an open question note asks); stalled (the builder's log has not grown for 15 min, shown
  // only); lost (no supervisor beat for 3 min, which the dispatcher's next reap settles). Cancel asks first and posts the
  // assignment cancel route; Log copies a `tail -f` of the run's log. Under them, the runs that ended in the last 24 hours
  // with their outcome, and Retry and Send to builder on a blocked or cancelled bundle (below).
  const BSTATE = { working: [G.live, 'WORKING'], waiting: [G.warning, 'WAITING ON ME'], stalled: [G.caution, 'STALLED'], lost: [G.unknown, 'LOST'] };
  const usd = n => `$${Number(n || 0).toFixed(2)}`;
  const names = r => r.items.length ? html`${r.items.map((m, i) => html`${i ? '; ' : ''}<code>sd:${String(m.item)}</code> ${m.title}`)}` : 'no items recorded';
  const bbtn = (act, r, label, aria, off) => html`<button class="btn quiet sm" type="button" data-build="${act}" data-run="${r.run}" aria-label="${aria}"${off ? html` disabled title="${off}"` : busy ? html` disabled` : ''}>${label}</button>`;
  const logBtn = r => r.log ? html`<button class="btn quiet sm" type="button" data-copy="${`tail -f ${window.shell.shq(r.log)}`}" aria-label="Copy the command that follows the log of run ${r.run}">Log</button>` : html`<span class="why">no log yet</span>`;
  function buildRow(r) {
    const [g, st] = BSTATE[r.state] || [G.unknown, r.state.toUpperCase()];
    const out = r.quiet == null ? 'no output yet' : `output ${dur(r.quiet)} ago`;
    return html`<li class="qrow" data-state="${r.state}"><span class="g g-${g[0]}" aria-hidden="true">${g[1]}</span><span class="st">${st}</span><span class="s"><span><span class="sr">${st.toLowerCase()} · </span>${names(r)}</span><small><b>${r.name}</b> · ${r.model || 'model not recorded'} · step <b>${r.step}</b> · ${dur(r.elapsed)} · ${out} · ${usd(r.usd)} so far${r.why ? ` · ${r.why}` : ''}</small></span><span class="ends"><div class="ctl" role="group" aria-label="Run ${r.run}">${bbtn('cancel', r, 'Cancel…', `Cancel build run ${r.run}`, r.cancel.allowed ? '' : r.cancel.reason || 'cancel is off')}${logBtn(r)}</div></span></li>`;
  }
  // A blocked or cancelled bundle keeps its worktree: Retry queues it again at once; Send to builder (pack sd:6020) asks
  // for a finding first, notes it on each item, and queues it again, so the next builder resumes that worktree with it.
  const AGAIN = ['blocked', 'cancelled'];
  function endedRow(r) {
    const g = r.outcome === 'done' ? G.ok : r.retry.bundle === 'blocked' ? G.warning : G.queued;
    const off = r.retry.allowed ? '' : r.retry.reason;
    return html`<li class="qrow" data-state="ended"><span class="g g-${g[0]}" aria-hidden="true">${g[1]}</span><span class="st">${(r.retry.bundle === 'blocked' ? 'BLOCKED' : r.outcome || 'ended').toUpperCase()}</span><span class="s"><span>${names(r)}</span><small><b>${r.name}</b> · ${r.outcome} at ${r.step} · ended ${at(r.ended)} · ${usd(r.usd)}${r.detail ? ` · ${r.detail}` : ''}</small></span><span class="ends"><div class="ctl" role="group" aria-label="Run ${r.run}">${AGAIN.includes(r.retry.bundle) ? html`${bbtn('retry', r, 'Retry', `Retry build run ${r.run}: queue its items again`, off)}${bbtn('send', r, 'Send to builder…', `Send a finding to the builder of run ${r.run}`, off)}` : ''}${logBtn(r)}</div></span></li>`;
  }
  function drawBuilds() {
    const head = html`<h2 id="builds-h" class="times-h">Builds</h2>`;
    const note = builtSaid ? (builtSaid.ok ? html`<p class="done" role="status">${builtSaid.text}</p>` : html`<p class="fail" role="alert">${builtSaid.text}</p>`) : '';
    if (!BUILT) { put($('builds'), html`${head}${note}<p class="fail" role="alert">▨ The builds were not read: ${BUILT_ERR || 'no answer yet'}.</p>`); return; }
    if (BUILT.error) { put($('builds'), html`${head}${note}<p class="fail" role="alert">▨ The builds were not read: ${BUILT.error}.</p>`); return; }
    put($('builds'), html`${head}${note}${BUILT.runs.length ? html`<ul class="qrows builds">${BUILT.runs.map(buildRow)}</ul>` : html`<p class="idle">No build runs now. Build on Tasks queues one.</p>`}
      ${BUILT.recent.length ? html`<details class="ended"><summary>Ended in the last ${String(BUILT.hours)} hours <span class="n">${String(BUILT.recent.length)}</span></summary><ul class="qrows">${BUILT.recent.map(endedRow)}</ul></details>` : ''}`);
  }
  async function loadBuilds() {
    try { BUILT = await window.shell.getJSON('/api/queue/builds'); BUILT_ERR = ''; }
    catch (err) { BUILT = null; BUILT_ERR = err.message; }
    drawBuilds();
  }
  async function buildAct(b) {
    if (busy || !BUILT) return;
    const S = window.shell, act = b.dataset.build, r = BUILT.runs.concat(BUILT.recent).find(x => x.run === b.dataset.run);
    if (!r) return;
    const what = r.items.map(m => `sd:${m.item}`).join(', ');
    if (act === 'cancel' && !(await S.confirm({ title: `Cancel build run ${r.run} (${what})?`,
      body: `The supervisor stops the ${r.step} step at its next beat, keeps the worktree, ends the bundle cancelled and moves ${r.items.length > 1 ? 'its items' : 'the item'} back to ready. Nothing is enqueued.`,
      cli: `sd assignments cancel ${r.cancel.assignment} --if-revision ${r.cancel.revision}`, ok: 'Cancel build', keep: 'Keep it running' }))) return;
    let finding = '';
    if (act === 'send') {
      const { yes, values } = await S.ask({ title: `Send to builder: run ${r.run} (${what})?`, ok: 'Send', keep: 'Cancel', danger: false,
        body: `The finding goes on ${r.items.length > 1 ? 'each item' : 'the item'} as a note, and the bundle queues again. Its next builder resumes ${r.worktree || 'the same worktree'} on its branch and fixes the finding first.`,
        fields: [{ name: 'finding', label: 'Finding', required: true, placeholder: 'What the builder should fix' }] });
      finding = (values && values.finding || '').trim();
      if (!yes || !finding) return;
    }
    const done = act === 'cancel' ? 'cancelled' : act === 'send' ? 'sent to the builder' : 'retried';
    busy = true; drawBuilds();
    try {
      if (act === 'cancel') await S.post(`/api/assignments/${r.cancel.assignment}/cancel`, { revision: r.cancel.revision });
      else await S.post('/api/queue/builds/retry', { assignment: r.retry.assignment, revision: r.retry.revision, ...(finding ? { finding } : {}) });
      builtSaid = { ok: true, text: act === 'cancel' ? `Run ${r.run} (${what}): cancel requested; it stops at its next beat.`
        : act === 'send' ? `${what} sent to the builder with your finding.` : `${what} queued again for build.` };
    } catch (err) {
      builtSaid = { ok: false, text: err.status >= 400 && err.status < 500 ? `Run ${r.run} not ${done}: ${err.message}`
        : `Not known whether run ${r.run} was ${done}: ${err.message} Read the panel before you act again.` };
    }
    busy = false;
    await loadBuilds();
  }
  window.queueBuildAct = buildAct; // for the page test
  function details() {
    const l = DOC && DOC.lanes.find(x => x.path === open);
    put($('details'), l ? lane(l) : html`<p class="why">${DOC ? 'No lane is open: no lane has a row to show.' : 'No lane is open: the lanes were not read.'}</p>`);
  }
  function draw() {
    if (!DOC) { put($('readings'), html``); put($('show'), html``); put($('lanes'), html``); put($('idle'), html``); put($('times'), html``); details(); return; }
    putEntries();
    const L = DOC.load, gates = DOC.gates;
    put($('readings'), html`<div><dt>load5</dt><dd>${L.load5.toFixed(1)}<small>1m ${L.load1.toFixed(1)} · 15m ${L.load15.toFixed(1)} · ${TREND[L.trend]}</small></dd></div>
      <div><dt>gates running / cap</dt><dd>${gates.error ? html`▨ <small>${gates.error}</small>` : html`${gates.running} / ${gates.cap}<small>${gates.waiting} waiting</small>`}</dd></div>
      <div><dt>read</dt><dd>${at(DOC.read)}<small>${DOC.read.replace('T', ' ').replace('Z', ' UTC')}</small></dd></div>`);
    $('edits').textContent = DOC.edits;
    const every = DOC.lanes.flatMap(l => l.rows), chip = (v, n) => html`<button type="button" class="chip" data-show="${v}" aria-pressed="${String(show === v)}">${v} <span class="n">${String(n)}</span></button>`;
    put($('show'), html`<span class="label">Show</span><div class="chips">${chip('active', every.filter(r => ACTIVE.includes(r.state)).length)}${chip('all', every.length)}</div>`);
    // A lane with nothing to show (and no write result) folds into the Idle line (sd:5640, sd:5921).
    const busyLanes = DOC.lanes.filter(l => drawn(l).length || said[l.path]), idle = DOC.lanes.filter(l => !busyLanes.includes(l));
    busyLanes.sort((a, b) => (count(b, 'blocked') > 0) - (count(a, 'blocked') > 0) || (count(b, 'merging') > 0) - (count(a, 'merging') > 0));
    if (!busyLanes.some(l => l.path === open)) open = busyLanes.length ? busyLanes[0].path : null;
    put($('lanes'), html`${DOC.problems.map(p => html`<p class="fail" role="alert">▨ ${p.repo}: lane not read. ${p.error}</p>`)}${busyLanes.length
      ? html`<table class="ledger lanes" aria-label="Active lanes"><thead><tr><th scope="col"><span class="sr">State</span></th><th scope="col">Lane</th><th scope="col">Merging · Next · Blocked</th><th scope="col">Head of lane</th><th scope="col" class="num">Landed</th><th scope="col"><span class="sr">Act</span></th></tr></thead>
      <tbody>${busyLanes.map(laneRow)}</tbody></table>`
      : !DOC.lanes.length ? html`<p class="done">No managed repository's lane was read. sd-db repo managed PATH yes adds one.</p>`
      : html`<p class="done">No lane has a row to show.</p>`}`);
    put($('idle'), html`${idleLine(idle)}`);
    put($('times'), timesTable());
    details();
  }

  async function load() {
    const S = window.shell;
    loadBuilds();
    if (!DOC) S.state({ kind: 'loading', text: 'Reading the lanes. Rows appear when /api/queue answers.', source: '/api/queue' });
    try {
      DOC = await S.getJSON('/api/queue');
      S.state(DOC.problems.length ? { kind: 'partial', text: `${plural(DOC.problems.length, 'lane')} not read; the others are current.`, source: '/api/queue' } : null);
      put($('subhead'), html`${plural(DOC.managed, 'managed repository', 'managed repositories')} · read ${at(DOC.read)}`);
    } catch (err) {
      DOC = null;
      S.state({ kind: 'error', text: `The lanes were not read: ${err.message}. Read again retries it.`, source: '/api/queue' });
      put($('subhead'), html`The lanes could not be read.`);
    }
    draw();
  }

  const DONE = { up: 'moved up', down: 'moved down', top: 'moved to the top', hold: 'held', release: 'released', cancel: 'cancelled',
    retry: 'queued again', approve: 'approved and queued again', requeue: 're-queued', reclaim: 'released from its holder' };
  // Cancel and Approve are the writes no verb undoes; each dialog names the entry and the command it runs.
  function grant(l, item, head) {
    const r = l.rows.find(x => x.state === 'blocked' && x.item === item), S = window.shell;
    return S.confirm({ title: `Approve sd:${item}${r && r.title ? ` · ${r.title}` : ''} in ${l.repo}?`,
      body: `The entry is queued again at head ${head.slice(0, 12)}, and the runner may merge it to the default branch. A merge is not taken back.`,
      cli: `sd-ship -C ${S.shq(l.path)} lane retry ${item} --expected-head ${head} --manual`, ok: 'Approve merge', keep: 'Leave it blocked' });
  }
  function sure(l, item) {
    const r = l.rows.find(x => x.state === 'next' && x.item === item), S = window.shell;
    return S.confirm({ title: `Cancel sd:${item}${r && r.title ? ` · ${r.title}` : ''} in ${l.repo}?`,
      body: `The entry leaves the queue and the runner never ships it. ${DOC.requeue
        ? 'Re-queue on its cancelled row puts it back, last, while its branch stays at this head.'
        : 'To ship it later, enqueue it again from its worktree.'}`,
      cli: `sd-ship -C ${S.shq(l.path)} lane cancel ${item}`, ok: 'Cancel entry', keep: 'Keep it queued' });
  }
  // Release names what the pack's reclaim does at the step the row showed; the claim binds it to that step.
  function letGo(l, item, claim) {
    const r = l.rows.find(x => x.state === 'merging' && x.item === item && x.claim === claim) || {}, S = window.shell;
    const host = r.host || 'a host not recorded', age = r.claim_age == null ? 'at a time not recorded' : `${dur(r.claim_age)} ago`;
    const outcome = r.step === 'prepare'
      ? 'The entry goes back to pending at its place and runs again; its third reclaim fails it instead.'
      : 'The entry fails with the release as its reason. A merge it already started may still land, so read its pull request before you enqueue it again.';
    return S.confirm({ title: `Release sd:${item}${r.title ? ` · ${r.title}` : ''} from ${host}?`,
      body: `${host} claimed it ${age}, at ${r.step || 'a step not recorded'}. ${outcome} The holder's next queue write is refused. If the entry moved on since this read, nothing is released. sd-ship refuses the release when the holder runs alive on this machine.`,
      cli: `sd-ship -C ${S.shq(l.path)} lane cancel ${item} --expected-claim ${S.shq(claim)}`, ok: 'Release entry', keep: 'Keep it running' });
  }
  async function act(b) {
    const l = DOC && DOC.lanes.find(x => x.path === b.dataset.repo);
    if (!l || busy) return;
    const item = Number(b.dataset.item), action = b.dataset.act, head = b.dataset.head || '', claim = b.dataset.claim || '';
    if (action === 'cancel' && !(await sure(l, item))) return;
    if (action === 'reclaim' && !(await letGo(l, item, claim))) return;
    if (action === 'approve' && !(await grant(l, item, head))) return;
    busy = true; draw();
    try {
      const body = { repo: l.path, item, action, revision: l.revision };
      if (action === 'retry' || action === 'approve' || action === 'requeue') body.head = head;
      if (action === 'reclaim') body.claim = claim;
      const out = await window.shell.post('/api/queue/move', body);
      const order = out.pending ? ` Order now: ${out.pending.map(n => `sd:${n}`).join(', ')}.` : '';
      said[l.path] = { ok: true, text: `sd:${item} ${DONE[action]}.${order} ${out.edits || ''}` };
    } catch (err) {
      // Only a 4xx wrote nothing (queue_screen.move); a 502, another status or no answer may follow a landed write (sd:3339).
      said[l.path] = { ok: false, text: err.status >= 400 && err.status < 500
        ? `sd:${item} not ${DONE[action]}: ${err.message}${err.stale ? '' : ' The queue is unchanged.'}`
        : `Not known whether sd:${item} was ${DONE[action]}: ${err.message} The lane below was read again; check sd:${item} there before you act again.` };
    }
    busy = false;
    await load();
  }
  window.queueAct = act; // for the page test

  // The last entry a review started for shows its run in Details; commands.js reads the run every 10 s until it settles.
  document.addEventListener('adversarial:run', e => {
    if (e.detail.key.startsWith('change:')) put($('adv'), html`${window.commands.reviewPane('change', e.detail.key.slice('change:'.length))}`);
  });

  window.PAGE_ATTENTION = { state: 'ok', n: 0, what: 'blocked' };
  document.addEventListener('DOMContentLoaded', () => {
    window.shell.commands.register(window.commands.adversarialReview('entry', {
      payload: o => ({ kind: 'change', target: o.worktree, item: o.item }),
      when: o => !!o.worktree || 'the lane recorded no worktree for this entry' }));
    // Read again (sd:5638): the shell's head button reads the lanes again.
    window.PAGE_AGAIN = { title: 'Read the lanes again', run: load };
    show = new URLSearchParams(location.search).get('show') === 'all' ? 'all' : 'active';
    $('show').addEventListener('click', e => {
      const b = e.target.closest('button[data-show]'); if (!b || b.dataset.show === show) return;
      show = b.dataset.show; window.shell.url(show === 'all' ? { show } : {}); draw();
    });
    // A write runs from the ledger's primary action or from Details; a lane name, Entries or the rest of its row opens the lane in Details.
    const press = e => {
      const b = e.target.closest('button[data-act]'); if (b) { if (!b.disabled) { open = b.dataset.repo; act(b); } return; }
      const o = e.target.closest('button[data-open]'); if (o) { open = o.dataset.open; draw(); window.shell.openPane('tab-details'); return; }
      // A click on the rest of a lane row opens it too, unless it hit a button or link (sd:6154).
      const r = !e.target.closest('button, a') && e.target.closest('tr[data-lane]'); if (r) { open = r.dataset.lane; draw(); window.shell.openPane('tab-details'); }
    };
    $('lanes').addEventListener('click', press); $('details').addEventListener('click', press);
    $('builds').addEventListener('click', e => { const b = e.target.closest('button[data-build]'); if (b && !b.disabled) buildAct(b); });
    if (typeof setInterval === 'function') setInterval(() => { if (!document.hidden && !busy) load(); }, 30000);
    load();
  });
})();
