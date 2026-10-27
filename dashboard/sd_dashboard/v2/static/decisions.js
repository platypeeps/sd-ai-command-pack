// Decide's Decisions (sd:3012; Today's view until sd:5781): each open question note, one button per option. It loads before
// shell.js.
// Rows: /api/decisions (sd_dashboard.decisions.document). A click posts /api/decisions/answer with the item, note, option
// and the item revision the read gave; the server writes the ruling and resolves the question in one transaction.
// A question with fewer than two Option: lines (sd:5064) gets a text box: its words post as the option, the same ruling
// `sd task note N "<words>" --kind decision --answers <note>` writes.
// Rulings by session (pack sd:6015): the last 7 days of decision notes, one group per session, each with its item and
// that item's state. Reverse posts /api/decisions/reverse: the server notes the reversal and reopens the question, which
// the next read lists above again.
// Drafts (pack sd:6361): each planning item a headless lead drafted, with its spec. Mark ready posts
// /api/items/<id>/status with status ready and the item revision; it is off while a draft question is open, as the
// server refuses that move. A 409 reads the list again.
// Markup is html`…` from markup.js: every value put in it is escaped, and put() is the only way into the page.
(() => {
  const { html, put } = window.markup;
  const $ = id => document.getElementById(id);
  const repoName = path => String(path || '').split('/').filter(Boolean).pop() || '';

  // LIST is the last read; null when it failed. RULED and REFUSED hold what a click did to a row until the next read.
  // REVIEW counts the questions on review batches (sd:3709): Scoring asks them, so Decisions draws one line that opens it.
  let LIST = [], REVIEW = 0, RULINGS = [], DRAFTS = [], reads = 0, failed = '';
  // READY holds the drafted items a tap moved to ready, MARKING those in flight, UNREADY a refusal's words.
  const READY = new Set(), MARKING = new Set(), UNREADY = new Map();
  const RULED = new Map(), REFUSED = new Map(), BUSY = new Set(), DRAFT = new Map();
  // The marker an option carries (sd:5306); the label drops it, the posted text keeps it.
  const REC = /^\s*(?:\(recommended\)|recommended:)\s*|\s*\(recommended\)\s*$/gi, label = o => o.replace(REC, '');
  // Sort (sd:3455): the shell's sort header, in memory as the other tables. The read's order (priority, then the oldest)
  // stands until a header is pressed; a tie keeps it.
  const low = s => String(s || '').toLowerCase();
  const SORT = { sort: '', dir: 1, page: 1 };
  const BY = { s: d => RULED.has(d.note) ? 1 : 0, what: d => low(d.title), question: d => low(d.question) };
  const COLS = [['s', html`<span class="sr">State</span>`, 'g'], ['what', 'Item'], ['question', 'Question'], [null, 'Choose', 'act']];
  const sorted = list => !SORT.sort ? list : [...list].sort((a, b) => { const x = BY[SORT.sort](a), y = BY[SORT.sort](b); return (x < y ? -1 : x > y ? 1 : 0) * SORT.dir; });

  const advice = d => { const rec = d.options[d.recommended]; return rec != null ? html`<span class="advice">Recommended: ${label(rec)}</span>` : html`<span class="advice none">No recommendation</span>`; };
  const refused = d => REFUSED.has(d.note) ? html`<p class="refused" role="alert">Not recorded: ${REFUSED.get(d.note)}</p>` : '';
  function choices(d) {
    const ruled = RULED.get(d.note);
    if (ruled) return html`<p class="ruled"><span class="g-ok" aria-hidden="true">●</span> Ruled: ${ruled.option} · note #${ruled.id}</p>`;
    // sd:5064: a free-text question; a typed draft survives a redraw.
    if (d.options.length < 2) {
      const off = BUSY.has(d.note) ? html` disabled` : '';
      return html`<form class="answer" data-note="${d.note}"><label class="sr" for="${`answer-${d.note}`}">${`Answer note ${d.note}`}</label><input id="${`answer-${d.note}`}" name="answer" autocomplete="off" maxlength="4000" placeholder="${d.options[0] || 'Your answer'}" value="${DRAFT.get(d.note) || ''}"${off}><button type="submit" class="btn sm"${off}>Answer</button></form>${refused(d)}`;
    }
    // sd:5306: the server names the recommended option; a filled button picks it, the others stay quiet in written order.
    const off = BUSY.has(d.note) ? html` disabled` : '', rec = d.options[d.recommended];
    return html`<div class="choices" role="group" aria-label="${`Choose for note ${d.note}`}">${rec != null ? html`<button type="button" class="btn sm" data-note="${d.note}" data-option="${d.recommended}" title="${rec}"${off}><span>Choose recommended</span></button>` : ''}${d.options.map((o, i) => html`<button type="button" class="btn quiet sm" data-note="${d.note}" data-option="${i}" title="${o}"${off}><span>${label(o)}</span></button>`)}</div>
      ${refused(d)}`;
  }

  // A session id is long; its first block names it, as sd today prints it.
  // A week can hold a thousand rulings (pack sd:6017): each session is a fold, the newest open; FOLD keeps what the
  // operator opened or shut across redraws.
  const FOLD = new Map();
  const session = g => g.session ? `Session ${g.session.split('-')[0]}` : 'No session';
  function reversal(r) {
    if (r.reversed) return html`<span class="why">reversed</span>`;
    if (!r.answers) return html`<span class="why" title="This ruling answered no question note: note the item to change it">answered no question</span>`;
    return html`<button type="button" class="btn quiet sm" data-reverse="${r.note}"${BUSY.has(-r.note) ? html` disabled` : ''}>Reverse</button>`;
  }
  function drawRulings() {
    const box = $('rulings'); if (!box) return;
    const n = RULINGS.reduce((sum, g) => sum + g.rulings.length, 0);
    put($('rulings-tally'), n ? html`<span>${n} in ${RULINGS.length} ${RULINGS.length === 1 ? 'session' : 'sessions'}</span>` : html``);
    put(box, !LIST ? html`` : RULINGS.length ? html`${RULINGS.map((g, i) => html`<details class="ruling-group"${(FOLD.has(g.session) ? FOLD.get(g.session) : !i) ? html` open` : ''}><summary class="ruling-session" data-session="${g.session}">${session(g)} · ${g.rulings.length} ${g.rulings.length === 1 ? 'ruling' : 'rulings'} · <time class="rel" datetime="${g.at}"></time></summary>
      <table class="ledger decisions rulings" aria-label="${`Rulings of ${session(g).toLowerCase()}`}"><tbody>${g.rulings.map(r => html`<tr data-item="${r.item}">
        <td class="g ${r.reversed ? 'g-queued' : 'g-ok'}" title="${r.reversed ? 'reversed' : 'ruled'}">${r.reversed ? '○' : '●'}</td>
        <td class="what"><a href="${window.shell.itemHref(r.item)}"><span class="id">#${r.item}</span> ${r.title}</a><span class="repo">${repoName(r.repo)} · ${r.state}</span></td>
        <td class="question">${r.question ? html`${r.question} → ` : ''}<b>${r.ruling}</b><span class="asked-at">note #${r.note} · <time class="rel" datetime="${r.at}"></time></span></td>
        <td class="act">${reversal(r)}</td></tr>`)}</tbody></table></details>`)}`
      : html`<p class="filtered">No ruling in the last 7 days.</p>`);
  }

  function readiness(d) {
    if (READY.has(d.item)) return html`<p class="ruled"><span class="g-ok" aria-hidden="true">●</span> Ready</p>`;
    const n = d.questions, off = n || MARKING.has(d.item) ? html` disabled` : '';
    return html`<button type="button" class="btn sm" data-ready="${d.item}"${off}>Mark ready</button>${n ? html`<span class="why">${n} open ${n === 1 ? 'question' : 'questions'}: answer below</span>` : ''}${UNREADY.has(d.item) ? html`<p class="refused" role="alert">Not marked: ${UNREADY.get(d.item)}</p>` : ''}`;
  }
  function drawDrafts() {
    const box = $('drafts'); if (!box) return;
    const list = LIST ? DRAFTS : [];
    $('drafts-sec').hidden = !list.length;
    const open = list.filter(d => d.questions && !READY.has(d.item)).length;
    put($('drafts-tally'), list.length ? html`<span>${list.length} drafted</span>${open ? html`<span class="g-caution">▲ ${open} with questions</span>` : ''}` : html``);
    put(box, html`${list.map(d => { const ready = READY.has(d.item); return html`<tr data-item="${d.item}"${MARKING.has(d.item) ? html` aria-busy="true"` : ''}>
      <td class="g ${ready ? 'g-ok' : d.questions ? 'g-caution' : 'g-queued'}" title="${ready ? 'ready' : d.questions ? 'questions open' : 'drafted'}">${ready ? '●' : d.questions ? '▲' : '◌'}</td>
      <td class="what"><a href="${window.shell.itemHref(d.item)}"><span class="id">#${d.item}</span> ${d.title}</a><span class="repo">${repoName(d.repo)}</span></td>
      <td class="question"><details class="spec"><summary>Spec</summary><div class="spec-text">${d.spec}</div></details><span class="asked-at">drafted <time class="rel" datetime="${d.drafted}"></time></span></td>
      <td class="act">${readiness(d)}</td></tr>`; })}`);
  }

  async function markReady(item) {
    const d = DRAFTS.find(x => x.item === item);
    if (!d || d.questions || READY.has(item) || MARKING.has(item)) return;
    MARKING.add(item); UNREADY.delete(item); draw();
    try {
      const out = await window.shell.post(`/api/items/${item}/status`, { status: 'ready', revision: d.revision });
      MARKING.delete(item); READY.add(item);
      // The move changed the item: its questions' rows carry the revision it returned.
      [...(LIST || []), ...DRAFTS].forEach(x => { if (x.item === item && out.revision) x.revision = out.revision; });
      draw();
    } catch (e) {
      MARKING.delete(item);
      if (e.stale) { say(`Not marked ready: ${e.message}. The list was read again.`); return load(); }
      UNREADY.set(item, e.message); draw();
    }
  }

  function draw() {
    drawRulings();
    drawDrafts();
    const tb = $('decisions'), line = $('decisions-review'), n = LIST ? REVIEW : 0;
    put($('decisions-head'), window.shell.list.sortHead(COLS, SORT));
    if (line) {
      put(line, n ? html`<span class="g-caution" aria-hidden="true">▲</span> <a href="#view=scoring">${n} ${n === 1 ? 'question waits' : 'questions wait'} on Scoring</a>` : html``);
      line.hidden = !n;
    }
    if (!LIST) {
      put(tb, html`<tr class="empty"><td colspan="4">Decisions could not be read: ${failed}. Refresh tries again.</td></tr>`);
      put($('decisions-tally'), html``); window.decideCount?.('decisions', null);
      return;
    }
    put(tb, LIST.length ? html`${sorted(LIST).map(d => { const ruled = RULED.has(d.note); return html`<tr data-item="${d.item}"${BUSY.has(d.note) ? html` aria-busy="true"` : ''}>
      <td class="g ${ruled ? 'g-ok' : 'g-caution'}" title="${ruled ? 'ruled' : 'waiting'}">${ruled ? '●' : '▲'}</td>
      <td class="what"><a href="${window.shell.itemHref(d.item)}"><span class="id">#${d.item}</span> ${d.title}</a><span class="repo">${repoName(d.repo)}</span></td>
      <td class="question">${d.question}${advice(d)}<span class="asked-at">note #${d.note} · asked <time class="rel" datetime="${d.asked}"></time></span></td>
      <td class="act">${choices(d)}</td></tr>`; })}`
      : html`<tr class="empty"><td colspan="4">No decision waits on you. An open question note appears here; one with two Option: lines gets a button each.</td></tr>`);
    const waiting = LIST.filter(d => !RULED.has(d.note)).length;
    put($('decisions-tally'), LIST.length ? html`<span class="g-caution">▲ ${waiting} waiting</span>${RULED.size ? html`<span class="g-ok">● ${RULED.size} ruled</span>` : ''}` : html``);
    window.decideCount?.('decisions', waiting); // the Decisions tab's count, and its part of Decide's badge
  }

  // Of overlapping reads only the newest draws.
  async function load() {
    const n = ++reads;
    try {
      const doc = await window.shell.getJSON('/api/decisions');
      if (n !== reads) return;
      LIST = doc.decisions; REVIEW = doc.review || 0; RULINGS = doc.rulings || []; RULED.clear(); REFUSED.clear(); BUSY.clear();
      DRAFTS = doc.drafts || []; READY.clear(); MARKING.clear(); UNREADY.clear();
    } catch (e) {
      if (n !== reads) return;
      LIST = null; failed = e.message;
    }
    draw();
  }

  function say(text) { const p = $('decisions-note'); p.textContent = text; p.hidden = !text; }

  // i picks an option; words answer a free-text question.
  async function choose(note, i, words) {
    const d = (LIST || []).find(x => x.note === note);
    const option = words != null ? words.trim() : d && d.options.length >= 2 ? d.options[i] : undefined;
    if (!d || BUSY.has(note) || RULED.has(note) || !option || (words != null) !== (d.options.length < 2)) return;
    BUSY.add(note); REFUSED.delete(note); draw();
    try {
      const out = await window.shell.post('/api/decisions/answer', { item: d.item, note, revision: d.revision, option });
      BUSY.delete(note); DRAFT.delete(note);
      RULED.set(note, { option, id: out.ruling.id });
      // The answer changed the item: its other decisions carry the revision the answer returned.
      LIST.forEach(x => { if (x.item === d.item) x.revision = out.revision; });
      draw();
    } catch (e) {
      BUSY.delete(note);
      if (e.stale) { say(`Not recorded: ${e.message}. The list was read again; choose again if the question is still open.`); return load(); }
      REFUSED.set(note, e.message); draw();
    }
  }

  // A ruling's busy mark is its negated note id, so it never meets a question's.
  async function reverse(note) {
    const r = RULINGS.flatMap(g => g.rulings).find(x => x.note === note);
    if (!r || !r.answers || r.reversed || BUSY.has(-note)) return;
    BUSY.add(-note); say(''); draw();
    try {
      await window.shell.post('/api/decisions/reverse', { item: r.item, note, revision: r.revision });
      say(`Reversed note #${note}: its question asks again above.`);
    } catch (e) {
      say(`Not reversed: ${e.message}.${e.stale ? ' The list was read again.' : ''}`);
    }
    return load();
  }

  // Read again (decide.js) reads the list again.
  window.decisions = { load: () => { say(''); return load(); } };

  document.addEventListener('DOMContentLoaded', () => {
    $('decisions').addEventListener('click', e => {
      const b = e.target.closest('button[data-option]');
      if (b && !b.disabled) choose(+b.dataset.note, +b.dataset.option);
    });
    $('decisions').addEventListener('submit', e => {
      const f = e.target.closest('form.answer'); if (!f) return;
      e.preventDefault(); choose(+f.dataset.note, null, f.elements.answer.value);
    });
    $('decisions').addEventListener('input', e => { const f = e.target.closest('form.answer'); if (f) DRAFT.set(+f.dataset.note, e.target.value); });
    $('drafts').addEventListener('click', e => {
      const b = e.target.closest('button[data-ready]');
      if (b && !b.disabled) markReady(+b.dataset.ready);
    });
    $('rulings').addEventListener('click', e => {
      const b = e.target.closest('button[data-reverse]');
      if (b && !b.disabled) reverse(+b.dataset.reverse);
    });
    // toggle does not bubble, so the box listens in the capture phase.
    $('rulings').addEventListener('toggle', e => { const s = e.target.querySelector?.(':scope > summary')?.dataset.session; if (s != null) FOLD.set(s, e.target.open); }, true);
    $('decisions-head').addEventListener('click', e => { if (window.shell.list.sortBy(e, SORT)) window.shell.list.keepFocus(e, draw); });
    put($('decisions-head'), window.shell.list.sortHead(COLS, SORT)); // drawn before the read, so a failed one keeps the columns
    load();
  });
})();
