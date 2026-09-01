// The whole client. One file, no build step, no framework: the page polls
// /api/state and redraws a table, and anything more elaborate would be a
// toolchain to maintain for a view that fits on one screen.
const rows = document.getElementById("rows");
const sub = document.getElementById("sub");
const needs = document.getElementById("needs");
const other = document.getElementById("other");
const issueSub = document.getElementById("issue-sub");
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

async function drawIssues() {
  let payload;
  try {
    payload = await (await fetch("/api/issues")).json();
  } catch (err) {
    issueSub.textContent = `cannot reach the server (${err})`;
    return;
  }
  if (!payload.available) {
    issueSub.textContent = payload.reason;
    fillIssues(needs, [], true);
    fillIssues(other, [], false);
    return;
  }
  const stamp = payload.indexedAt ? ` \u00b7 last collected ${payload.indexedAt}` : "";
  issueSub.textContent =
    `${payload.needsYou.length} waiting on you, ${payload.other.length} other open${stamp}`;
  fillIssues(needs, payload.needsYou, true);
  fillIssues(other, payload.other, false);
}

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

// --- tabs ---------------------------------------------------------------
// The backbone's own tabs are fixed; plugin tabs arrive from the registry and
// are rebuilt on every poll, so the list is rebuilt with them rather than
// appended to. A plugin removed from the registry has to lose its tab, and a
// list that only grows would keep serving a tab nothing feeds.

const STATIC = [
  ["tab-now", "panel-now"],
  ["tab-repos", "panel-repos"],
  ["tab-issues", "panel-issues"],
  ["tab-work", "panel-work"],
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
function destination(row) {
  if (row.source === "repos") return "panel-repos";
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
    return;
  }
  nowRowsSeen = payload.rows;
  paintNow(nowRowsSeen);
}

// Called by the plugin poll too, which is why this repaints from what was last
// fetched rather than fetching again: the panel map changed, the rows did not.
function repaintNow() {
  if (nowRowsSeen) paintNow(nowRowsSeen);
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

drawWork();
setInterval(drawWork, 30000);

drawNow();
// The same ten seconds as the plugin poll: this is the view where a cron job
// going red is the thing being watched, and half its rows come from there.
setInterval(drawNow, 10000);

drawPlugins();
// Deliberately not the 30s of the other two: the plugin loader has its own
// five-second cache, and this is the view where a cron job going red is the
// thing being watched.
setInterval(drawPlugins, 10000);
