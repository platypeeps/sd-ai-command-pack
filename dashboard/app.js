// The whole client. One file, no build step, no framework: the page polls
// /api/state and redraws a table, and anything more elaborate would be a
// toolchain to maintain for a view that fits on one screen.
const rows = document.getElementById("rows");
const sub = document.getElementById("sub");
const needs = document.getElementById("needs");
const issueSub = document.getElementById("issue-sub");
const prNeeds = document.getElementById("pr-needs");
const prSub = document.getElementById("pr-sub");
const skillRows = document.getElementById("skill-rows");
const skillSub = document.getElementById("skill-sub");
const sessionTrees = document.getElementById("session-trees");
const sessionProcs = document.getElementById("session-procs");
const sessionSub = document.getElementById("session-sub");
const workMoving = document.getElementById("work-moving");
const workUnstated = document.getElementById("work-unstated");
const workSub = document.getElementById("work-sub");
const nowRows = document.getElementById("now-rows");
const nowSub = document.getElementById("now-sub");
const nowBadge = document.getElementById("now-badge");

// Where a plugin row goes when clicked, keyed on the source the loader
// stamped. Written by the plugin renderer as it assigns panel ids and read by
// Now. Declared up here because the renderer runs long before Now's section
// is reached, and a `const` further down would still be in its temporal dead
// zone by then.
const PANELS = { bySource: new Map() };

const cell = (text, cls) => {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
};

const num = (value, cls) =>
  // null means "no upstream to compare against", which is not zero. Showing a
  // dash keeps the page from inventing a divergence the repo never reported.
  cell(value === null || value === undefined ? "–" : String(value), value ? `n ${cls}` : "n");

async function draw() {
  let state;
  try {
    state = await (await fetch("/api/state")).json();
  } catch (err) {
    sub.textContent = `cannot reach the server (${err})`;
    return;
  }
  sub.textContent = state.rootExists
    ? `${state.counts.repos} repos under ${state.root} · ${state.counts.dirty} dirty · ${state.counts.ahead} ahead`
    : `no such directory: ${state.root} — check SD_REPO_ROOT`;
  rows.replaceChildren();
  for (const repo of state.repos) {
    const tr = document.createElement("tr");
    tr.append(
      cell(repo.name),
      cell(repo.group === "." ? "" : repo.group),
      cell(repo.branch),
      num(repo.dirty, "dirty"),
      num(repo.ahead, "ahead"),
      num(repo.behind),
      cell(repo.last),
      cell(repo.subject),
    );
    rows.append(tr);
  }
}

draw();
setInterval(draw, 30000);

// --- issues -------------------------------------------------------------
// Rendered from the index, never from a live collect: the server does not
// reach GitHub or Jira on a page load, so what this shows is as fresh as the
// last `sd-dashboard index` and the page says so rather than implying live.

const link = (text, href) => {
  const td = document.createElement("td");
  if (href) {
    const a = document.createElement("a");
    a.href = href;
    a.textContent = text;
    a.target = "_blank";
    // `noopener` spelled out: `noreferrer` implies it in current browsers,
    // but not everywhere, and the new tab must never get a `window.opener`.
    a.rel = "noopener noreferrer";
    td.append(a);
  } else {
    td.textContent = text;
  }
  return td;
};

const where = (issue) =>
  // A GitHub row has a number to show; a Jira row's identity is already in its
  // URL tail, so showing "#null" would be an invented fact.
  issue.number === null || issue.number === undefined
    ? issue.repo || issue.tracker
    : `${issue.repo}#${issue.number}`;

function fillIssues(tbody, list, emphasise) {
  tbody.replaceChildren();
  if (!list.length) {
    const tr = document.createElement("tr");
    const td = cell("none");
    td.colSpan = 4;
    td.style.opacity = ".6";
    tr.append(td);
    tbody.append(tr);
    return;
  }
  for (const issue of list) {
    const tr = document.createElement("tr");
    if (emphasise) tr.className = "you";
    tr.append(
      link(where(issue), issue.url),
      cell(issue.title),
      cell((issue.why || []).join(", ")),
      cell((issue.updated_at || "").slice(0, 10)),
    );
    tbody.append(tr);
  }
}

// Issues and PRs are one renderer because they are one table: the search that
// fills the index does not separate them, and the only thing that differs
// between the two tabs is which `kind` the route asked for.
//
// One table, not two. The second one listed `author:@me` and `mentions:@me`
// -- everything the account touches rather than everything it owes anybody --
// and it was the longer of the two by a wide margin, so the tab read as a
// feed. The index still collects those buckets and `/api/{issues,prs}` still
// returns them; the count below says how many are being withheld, because a
// view that quietly drops rows is worse than one that lists too many.
//
// That count names the two buckets rather than calling them settled. A first
// draft read "not yours to answer", which is true of `author:@me` and a guess
// about `mentions:@me` -- somebody can ask for a decision by naming you, and
// no label here should decide they did not. What the withheld group actually
// has in common is how it was found, so that is what the line says.
//
// And it says it in links. Suppressing a bucket from a queue is a ranking
// decision; making it unreachable is a different and worse one, because a
// mention is how some people hand work over, and a dashboard that answers
// "seventeen" and nothing else has hidden them rather than deprioritised
// them. GitHub already keeps exactly these two lists, so the counts point at
// them and the tab does not have to grow a second table to stay honest.
function subLink(href, text) {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noreferrer";
  a.textContent = text;
  return a;
}

async function drawTracker(route, into, subLine, noun, hub) {
  let payload;
  try {
    payload = await (await fetch(route)).json();
  } catch (err) {
    subLine.textContent = `cannot reach the server (${err})`;
    return;
  }
  if (!payload.available) {
    subLine.textContent = payload.reason;
    fillIssues(into, [], true);
    return;
  }
  const stamp = payload.indexedAt ? ` \u00b7 last collected ${payload.indexedAt}` : "";
  subLine.replaceChildren(
    document.createTextNode(
      `${payload.needsYou.length} ${noun} assigned to you or awaiting your ` +
      `review \u00b7 ${payload.other.length} more, not shown: `),
    subLink(`https://github.com/${hub}/created`, "authored"),
    document.createTextNode(" or "),
    subLink(`https://github.com/${hub}/mentioned`, "mentioning you"),
    document.createTextNode(stamp),
  );
  fillIssues(into, payload.needsYou, true);
}

const drawIssues = () =>
  drawTracker("/api/issues", needs, issueSub, "issues", "issues");
const drawPrs = () =>
  drawTracker("/api/prs", prNeeds, prSub, "pull requests", "pulls");

// --- work ---------------------------------------------------------------
// Two tables rather than one, because the second is not a subset of the first:
// an item with no status is not "moving slowly", it is an item the fleet
// cannot describe, and burying it in a status column reading blank is how it
// stays that way.

function emptyRow(tbody, span, text) {
  const tr = document.createElement("tr");
  const td = cell(text);
  td.colSpan = span;
  td.style.opacity = ".6";
  tr.append(td);
  tbody.append(tr);
}

async function drawWork() {
  let payload;
  try {
    payload = await (await fetch("/api/work")).json();
  } catch (err) {
    workSub.textContent = `cannot reach the server (${err})`;
    return;
  }
  // Every status, not just the ones missing from the table below. Showing six
  // rows without saying that 300 more exist would read as the whole set, and
  // a breakdown that omitted the six would not add up to `active`.
  const breakdown = Object.entries(payload.counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => `${count} ${name}`)
    .join(" \u00b7 ");
  workSub.textContent =
    `${payload.active} active across ${payload.repos} repos` +
    `${breakdown ? ` \u00b7 ${breakdown}` : ""}` +
    ` \u00b7 ${payload.archived} archived`;

  workMoving.replaceChildren();
  if (!payload.moving.length) {
    emptyRow(workMoving, 5, "nothing in flight");
  } else {
    for (const item of payload.moving) {
      const tr = document.createElement("tr");
      tr.append(
        cell(item.repo),
        cell(item.title || item.name),
        cell(item.status),
        cell(item.detail),
        cell(item.created),
      );
      workMoving.append(tr);
    }
  }

  workUnstated.replaceChildren();
  if (!payload.unstated.length) {
    emptyRow(workUnstated, 3, "every item says what it is");
  } else {
    for (const item of payload.unstated) {
      const tr = document.createElement("tr");
      tr.className = "you";
      tr.append(
        cell(item.repo),
        cell(item.name),
        cell(item.hasPrd ? "prd.md has no status" : "no prd.md"),
      );
      workUnstated.append(tr);
    }
  }
}

// --- skills --------------------------------------------------------------
// Two directories and the gap between them. Nothing keeps `skills/` and
// ~/.claude/skills in step -- installing is a deliberate act -- so the gap is
// the view, not a fault to hide.

async function drawSkills() {
  let payload;
  try {
    payload = await (await fetch("/api/skills")).json();
  } catch (err) {
    skillSub.textContent = `cannot reach the server (${err})`;
    return;
  }
  const seen = payload.counts;
  skillSub.textContent = payload.installedExists
    ? `${seen.shipped} ship here \u00b7 ${seen.installed} installed in ` +
      `${payload.installedAt} \u00b7 ${seen.unadopted} not installed \u00b7 ` +
      `${seen.foreign} installed from elsewhere`
    : `${seen.shipped} ship here \u00b7 nothing installed at ${payload.installedAt}`;
  skillRows.replaceChildren();
  if (!payload.skills.length) {
    emptyRow(skillRows, 4, "no skills anywhere");
    return;
  }
  for (const skill of payload.skills) {
    const tr = document.createElement("tr");
    // The one row shape worth emphasising: shipped here and not installed
    // means the agent cannot reach a skill this repository thinks it has.
    if (skill.shipped && !skill.installed) tr.className = "you";
    tr.append(
      cell(skill.name),
      cell(skill.shipped ? "yes" : ""),
      cell(skill.installed ? "yes" : ""),
      cell(skill.description),
    );
    skillRows.append(tr);
  }
}

// --- sessions ------------------------------------------------------------
// No ledger replaces `.runtime/sessions`: a worktree is registered in git's
// own directory and a running command is in the process table, and both are
// already true without anything having written them down.

async function drawSessions() {
  let payload;
  try {
    payload = await (await fetch("/api/sessions")).json();
  } catch (err) {
    sessionSub.textContent = `cannot reach the server (${err})`;
    return;
  }
  sessionSub.textContent =
    `${payload.counts.worktrees} worktree${payload.counts.worktrees === 1 ? "" : "s"}` +
    ` \u00b7 ${payload.abandoned} abandoned \u00b7 ` +
    `${payload.counts.processes} sd-* running`;

  sessionTrees.replaceChildren();
  if (!payload.worktrees.length) {
    emptyRow(sessionTrees, 5, "no worktrees registered anywhere in the fleet");
  } else {
    for (const tree of payload.worktrees) {
      const tr = document.createElement("tr");
      if (!tree.live) tr.className = "you";
      tr.append(
        cell(tree.repo),
        cell(tree.name),
        cell(tree.branch),
        cell(tree.live ? "live" : "abandoned"),
        cell(tree.path),
      );
      sessionTrees.append(tr);
    }
  }

  sessionProcs.replaceChildren();
  if (!payload.processes.length) {
    emptyRow(sessionProcs, 3, "nothing sd-* is running");
  } else {
    for (const proc of payload.processes) {
      const tr = document.createElement("tr");
      tr.append(cell(proc.pid), cell(proc.elapsed), cell(proc.command));
      sessionProcs.append(tr);
    }
  }
}

// --- tabs ---------------------------------------------------------------
// The backbone's own tabs are fixed; plugin tabs arrive from the registry and
// are rebuilt on every poll, so the list is rebuilt with them rather than
// appended to. A plugin removed from the registry has to lose its tab, and a
// list that only grows would keep serving a tab nothing feeds.

const STATIC = [
  ["tab-now", "panel-now"],
  ["tab-repos", "panel-repos"],
  ["tab-prs", "panel-prs"],
  ["tab-issues", "panel-issues"],
  ["tab-work", "panel-work"],
  ["tab-skills", "panel-skills"],
  ["tab-sessions", "panel-sessions"],
];
let tabs = STATIC.slice();

const pluginNav = document.getElementById("plugin-tabs");
const pluginPanels = document.getElementById("plugin-panels");

function select(chosen) {
  for (const [button, panel] of tabs) {
    const on = button === chosen;
    document.getElementById(button).setAttribute("aria-selected", String(on));
    document.getElementById(panel).hidden = !on;
  }
}

function wire(button) {
  document.getElementById(button).addEventListener("click", () => select(button));
}

for (const [button] of STATIC) wire(button);
// The generic table behaviour is not a plugin privilege. Skills is 138 rows
// and asks for the filter by the same attribute a tile would use, so the
// backbone's own panels go through `enhance` once at startup -- plugin panels
// go through it on every rebuild because they are rebuilt.
for (const [, panel] of STATIC) enhance(document.getElementById(panel));
select("tab-now");

// --- generic table behaviour --------------------------------------------
// A plugin declares what its table can do and the backbone provides the doing:
// `data-sd-search` asks for a filter box, `data-sd-sort` for click-to-sort
// headers, and a `<th data-sort="num">` says how that column compares. This is
// the whole reason no plugin ships script — the sanitiser would drop it, and
// this is what it is dropped in favour of.

const bodyRows = (table) =>
  table.tBodies[0] ? Array.from(table.tBodies[0].rows) : [];

const cellText = (row, column) =>
  row.cells[column] ? row.cells[column].textContent.trim() : "";

// Direction is an argument rather than a multiplier on the result, and that is
// the whole reason this signature has four parameters. A cell holding no
// number must sink in both directions -- sorting it as zero would put an
// em-dash among the small values and read as data -- and a `* -1` applied to
// the answer flips the sinking along with everything else, floating the empty
// cells to the top of a descending sort. Found in review, where the comment
// promising "either way" was true of the comparator and false of its caller.
function compare(a, b, how, descending) {
  if (how !== "num") {
    const order = a.localeCompare(b, undefined, { sensitivity: "base" });
    return descending ? -order : order;
  }
  // Strip everything a number is not, so "12 min" and "$4.10" still order.
  const x = Number.parseFloat(a.replace(/[^0-9.eE+-]/g, ""));
  const y = Number.parseFloat(b.replace(/[^0-9.eE+-]/g, ""));
  if (Number.isNaN(x) && Number.isNaN(y)) return 0;
  if (Number.isNaN(x)) return 1;
  if (Number.isNaN(y)) return -1;
  return descending ? y - x : x - y;
}

function addFilter(table) {
  const box = document.createElement("input");
  box.type = "search";
  box.className = "filter";
  box.placeholder = table.getAttribute("data-sd-search") || "filter";
  // A placeholder is not a name: it is not reliably announced, and it vanishes
  // as soon as anything is typed into it.
  box.setAttribute("aria-label", box.placeholder);
  box.addEventListener("input", () => {
    const needle = box.value.trim().toLowerCase();
    for (const row of bodyRows(table)) {
      row.hidden = needle !== "" && !row.textContent.toLowerCase().includes(needle);
    }
  });
  table.parentNode.insertBefore(box, table);
}

function addSort(table) {
  const head = table.tHead && table.tHead.rows[0];
  if (!head) return;
  Array.from(head.cells).forEach((th, column) => {
    const how = th.getAttribute("data-sort");
    if (!how || how === "none") return;
    th.classList.add("sortable");
    th.tabIndex = 0;
    // First click sorts ascending, each one after it reverses. Started at
    // `true` because the toggle runs before the sort does, and a header whose
    // first click sorts descending reads as a page that ignored the click and
    // did something else.
    let descending = true;
    const run = () => {
      const body = table.tBodies[0];
      if (!body) return;
      descending = !descending;
      const rows = bodyRows(table);
      rows.sort((a, b) =>
        compare(cellText(a, column), cellText(b, column), how, descending),
      );
      for (const other of head.cells) other.removeAttribute("aria-sort");
      th.setAttribute("aria-sort", descending ? "descending" : "ascending");
      // Re-appending moves the existing rows rather than redrawing them, so a
      // filter already applied to a row survives its own sort.
      body.append(...rows);
    };
    th.addEventListener("click", run);
    th.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        run();
      }
    });
  });
}

function enhance(panel) {
  for (const table of panel.querySelectorAll("table")) {
    if (table.hasAttribute("data-sd-search")) addFilter(table);
    if (table.hasAttribute("data-sd-sort")) addSort(table);
  }
}

// --- plugin tabs ---------------------------------------------------------

function panelId(tab, used) {
  // Identity is the plugin's own, not the position in the list: a registry
  // that reorders must not move which tab the operator is looking at.
  const base = `${tab.prefix}/${tab.name}`.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  let id = base;
  for (let n = 2; used.has(id); n += 1) id = `${base}-${n}`;
  used.add(id);
  return id;
}

// --- now -----------------------------------------------------------------
// The one view that outranks its own tabs. The rows come merged and ranked
// from /api/now; what is left here is the two things that cannot be decided
// server-side -- how loud a rank looks, and which panel on this page a row
// belongs to.

// Severity is derived from `rank` and never from `kind` (R11-D20). `kind` is
// the category of thing that happened and a plugin names its own, so styling
// from it paints `plugin-dark` -- a rank-0 row -- with whatever the ternary's
// catch-all branch happens to be. The bands are chosen here because choosing
// them is a rendering decision; the ruling is that nothing else may choose.
function band(rank) {
  if (rank <= 1) return "broken";
  if (rank <= 3) return "look";
  return "queued";
}

// A plugin row's destination is looked up, never recomputed (R11-D20). The
// renderer records the id it assigned; `panelId` normalises with a many-to-one
// regex, so deriving it again here could send a row to a sibling tab's panel,
// which is worse than not linking it. Three sources name no served panel, and
// they are exactly the failures: `dashboard` for a registry that did not load,
// a bare prefix for a plugin that is dark, and `prefix/name` for a tab that was
// refused and filtered out at the moment its alert was created. Those render
// unlinked by design -- sending a reader to a tab that is not on screen is the
// same disappearance one layer along.
const BACKBONE_PANELS = {
  repos: "panel-repos",
  prs: "panel-prs",
  sessions: "panel-sessions",
};

function destination(row) {
  if (BACKBONE_PANELS[row.source]) return BACKBONE_PANELS[row.source];
  return PANELS.bySource.get(row.source) || "";
}

function whereCell(row) {
  const td = cell(row.source);
  const panel = destination(row);
  if (!panel) return td;
  // In-page, and only ever in-page: the destination is a tab this page is
  // already showing, chosen by the backbone rather than supplied by a plugin.
  // A button rather than an anchor because selecting a tab is what it does,
  // and an href would need the panel to be a scroll target.
  const link = document.createElement("button");
  link.className = "linklike";
  link.textContent = row.source;
  link.addEventListener("click", () => {
    const found = tabs.find(([, id]) => id === panel);
    if (found) select(found[0]);
  });
  td.replaceChildren(link);
  return td;
}

function paintNow(all) {
  const loud = all.filter((row) => band(row.rank) !== "queued").length;
  nowBadge.textContent = loud ? String(loud) : "";
  nowSub.textContent = all.length
    ? `${all.length} thing${all.length === 1 ? "" : "s"} \u00b7 ${loud} above the fold`
    : "nothing is asking for anything";
  nowRows.replaceChildren();
  if (!all.length) {
    emptyRow(nowRows, 4, "nothing is asking for anything");
    return;
  }
  for (const row of all) {
    const how = band(row.rank);
    const pill = document.createElement("span");
    pill.className = `pill ${how}`;
    pill.textContent = how;
    const rank = document.createElement("td");
    rank.append(pill);
    const tr = document.createElement("tr");
    if (how === "broken") tr.className = "you";
    tr.append(rank, cell(row.what), cell(row.detail || ""), whereCell(row));
    nowRows.append(tr);
  }
}

// null until the first fetch answers, and the distinction is the point: the
// plugin poll repaints this view whenever the panel map moves, and it can win
// the race on page load. Painting an empty list then would flash "nothing is
// asking for anything" across the one view whose whole job is not to say that
// when it does not know.
let nowRowsSeen = null;

async function drawNow() {
  let payload;
  try {
    payload = await (await fetch("/api/now")).json();
  } catch (err) {
    // A Now that cannot be reached is itself the loudest thing there is: every
    // source has gone quiet at once, and an empty table would say the opposite.
    paintNow([{
      rank: 0,
      id: "now-unreachable",
      source: "dashboard",
      what: `cannot reach the server (${err})`,
      detail: "",
    }]);
    // What was last seen is no longer what is true, and the plugin poll
    // repaints from it. Left in place, a tab rebuild ten seconds from now
    // would quietly replace the error with the rows from before the server
    // went away -- the failure erased by the thing that reports failures.
    nowRowsSeen = null;
    return;
  }
  nowRowsSeen = payload.rows;
  paintNow(nowRowsSeen);
}

// Called by the plugin poll too, which is why this repaints from what was last
// fetched rather than fetching again: the panel map changed, the rows did not.
function repaintNow() {
  // Against the sentinel, not for truthiness. Both read the same here -- an
  // empty array is truthy in JS, so no fetched-but-empty list was ever being
  // skipped -- but the guard is about whether Now has an answer yet, and
  // saying so is the only way that stays true if the shape changes.
  if (nowRowsSeen !== null) paintNow(nowRowsSeen);
}

let pluginSignature = "";

async function drawPlugins() {
  let payload;
  try {
    payload = await (await fetch("/api/plugins")).json();
  } catch (err) {
    // A loader that cannot be reached is itself a rank-0 event: every plugin
    // has gone quiet at once, and an empty strip would say the opposite.
    return;
  }
  // Rebuilt only when what the tiles returned actually changed. The poll is
  // every ten seconds and a rebuild throws away the panel's DOM, which is
  // where a typed filter and a chosen sort order live -- redrawing identical
  // markup would clear both, four times a minute, while the operator was
  // reading it. When the data does change the state goes with it, which is
  // the honest trade: the rows under a filter are no longer the rows it was
  // applied to.
  // Only the fields the panel is built from. A tab also carries `rows` and
  // `complaints`, which go to the alert strip and change whenever a job's age
  // or exit code does -- signing those would rebuild the panels every poll on
  // exactly the machines that have something to report, which is the opposite
  // of what this guard is for.
  const signature = JSON.stringify(
    payload.tabs.map((tab) => [tab.prefix, tab.name, tab.title, tab.html]),
  );
  if (signature === pluginSignature) {
    return;
  }
  pluginSignature = signature;
  const previous = (tabs.find(([button]) =>
    document.getElementById(button).getAttribute("aria-selected") === "true",
  ) || STATIC[0])[0];
  pluginNav.replaceChildren();
  pluginPanels.replaceChildren();
  tabs = STATIC.slice();
  PANELS.bySource = new Map();
  const used = new Set();
  for (const tab of payload.tabs) {
    const id = panelId(tab, used);
    PANELS.bySource.set(`${tab.prefix}/${tab.name}`, `panel-plugin-${id}`);
    const button = document.createElement("button");
    button.id = `tab-plugin-${id}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", "false");
    button.setAttribute("aria-controls", `panel-plugin-${id}`);
    button.textContent = tab.title;
    const panel = document.createElement("section");
    panel.id = `panel-plugin-${id}`;
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", button.id);
    panel.hidden = true;
    // Markup, not text: a tile draws its own tab. What makes that safe is the
    // filter this payload already passed through server-side -- see
    // dashboard/markup.py, which is where the allow-list lives and where the
    // reasoning about inline handlers belongs.
    panel.innerHTML = tab.html;
    enhance(panel);
    pluginNav.append(button);
    pluginPanels.append(panel);
    tabs.push([button.id, panel.id]);
    wire(button.id);
  }
  // A plugin tab that vanished takes the selection back to a tab that exists,
  // rather than leaving every panel hidden and the page apparently blank.
  select(document.getElementById(previous) ? previous : STATIC[0][0]);
  // The panel map just changed, so every plugin row's destination did too.
  repaintNow();
}

drawIssues();
setInterval(drawIssues, 30000);

drawPrs();
setInterval(drawPrs, 30000);

drawWork();
setInterval(drawWork, 30000);

drawSkills();
// Slower than the rest on purpose: two directory listings answer a question
// whose answer changes when somebody runs an installer, not on a timer.
setInterval(drawSkills, 120000);

drawSessions();
setInterval(drawSessions, 30000);

drawNow();
// The same ten seconds as the plugin poll: this is the view where a cron job
// going red is the thing being watched, and half its rows come from there.
setInterval(drawNow, 10000);

drawPlugins();
// Deliberately not the 30s of the other two: the plugin loader has its own
// five-second cache, and this is the view where a cron job going red is the
// thing being watched.
setInterval(drawPlugins, 10000);

// --- run ----------------------------------------------------------------
// The one place this page writes, below the tabs rather than inside one: an
// action belongs to the dashboard, not to whichever view is open when somebody
// wants to press it. A button sends an **id** -- the argv lives in
// `RUN_ALLOWLIST` or a manifest and has never been sent here.

const runButtons = document.getElementById("run-buttons");
const runSub = document.getElementById("run-sub");
// Delivered with the page, so anything able to read it could already read the
// page. Missing means every POST is refused, which is the safe direction.
const RUN_TOKEN =
  (document.querySelector('meta[name="dashboard-token"]') || {}).content || "";

async function press(button, id) {
  button.disabled = true;
  runSub.textContent = `running ${id}…`;
  try {
    const reply = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Dashboard-Token": RUN_TOKEN },
      body: JSON.stringify({ action: id }),
    });
    const body = await reply.json().catch(() => ({}));
    // The last line of output: the summary is printed last, and the strip is
    // one line tall.
    runSub.textContent = body.ok
      ? `${id}: ${(body.output || "finished").split("\n").pop()}`
      : `${id} failed: ${body.error || reply.status}`;
  } catch (err) {
    runSub.textContent = `${id} could not be sent (${err})`;
  }
  button.disabled = false;
  // Whatever it did, every view that reads what it wrote is now behind.
  for (const redraw of [drawIssues, drawPrs, drawNow, drawPlugins]) redraw();
}

async function drawRun() {
  let payload;
  try {
    payload = await (await fetch("/api/actions")).json();
  } catch (err) {
    runSub.textContent = `cannot list actions (${err})`;
    return;
  }
  runButtons.replaceChildren();
  for (const action of payload.actions) {
    const button = document.createElement("button");
    button.textContent = action.label;
    button.addEventListener("click", () => press(button, action.id));
    runButtons.append(button);
  }
  // "none declared" would report a broken loader as a machine with no plugins.
  runSub.textContent = payload.reason
    ? `every button here is one allow-listed command — ${payload.reason}`
    : payload.actions.length
      ? "every button here is one allow-listed command"
      : "no actions declared";
}

// Once. The set changes when a plugin is registered, which is a restart.
drawRun();
