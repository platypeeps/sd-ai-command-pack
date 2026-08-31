// The whole client. One file, no build step, no framework: the page polls
// /api/state and redraws a table, and anything more elaborate would be a
// toolchain to maintain for a view that fits on one screen.
const rows = document.getElementById("rows");
const sub = document.getElementById("sub");
const needs = document.getElementById("needs");
const other = document.getElementById("other");
const issueSub = document.getElementById("issue-sub");

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

// --- tabs ---------------------------------------------------------------
// The backbone's own tabs are fixed; plugin tabs arrive from the registry and
// are rebuilt on every poll, so the list is rebuilt with them rather than
// appended to. A plugin removed from the registry has to lose its tab, and a
// list that only grows would keep serving a tab nothing feeds.

const STATIC = [
  ["tab-repos", "panel-repos"],
  ["tab-issues", "panel-issues"],
];
let tabs = STATIC.slice();

const pluginNav = document.getElementById("plugin-tabs");
const pluginPanels = document.getElementById("plugin-panels");
const alerts = document.getElementById("alerts");

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
select("tab-repos");

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

function compare(a, b, how) {
  if (how !== "num") return a.localeCompare(b, undefined, { sensitivity: "base" });
  // Strip everything a number is not, so "12 min" and "$4.10" still order.
  const x = Number.parseFloat(a.replace(/[^0-9.eE+-]/g, ""));
  const y = Number.parseFloat(b.replace(/[^0-9.eE+-]/g, ""));
  // A cell that holds no number sinks either way rather than sorting as zero,
  // which would put "—" among the small values and read as data.
  if (Number.isNaN(x) && Number.isNaN(y)) return 0;
  if (Number.isNaN(x)) return 1;
  if (Number.isNaN(y)) return -1;
  return x - y;
}

function addFilter(table) {
  const box = document.createElement("input");
  box.type = "search";
  box.className = "filter";
  box.placeholder = table.getAttribute("data-sd-search") || "filter";
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
    let descending = false;
    const run = () => {
      const body = table.tBodies[0];
      if (!body) return;
      descending = !descending;
      const rows = bodyRows(table);
      rows.sort(
        (a, b) =>
          compare(cellText(a, column), cellText(b, column), how) * (descending ? -1 : 1),
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

function showAlerts(rows) {
  alerts.replaceChildren();
  alerts.hidden = rows.length === 0;
  if (!rows.length) return;
  const heading = document.createElement("p");
  heading.className = "sub";
  heading.textContent =
    `${rows.length} plugin alert${rows.length === 1 ? "" : "s"}` +
    " \u00b7 shown here on every tab until Now lands";
  const list = document.createElement("ul");
  for (const row of rows) {
    const item = document.createElement("li");
    item.textContent = row.detail
      ? `${row.source}: ${row.what} \u2014 ${row.detail}`
      : `${row.source}: ${row.what}`;
    list.append(item);
  }
  alerts.append(heading, list);
}

let pluginSignature = "";

async function drawPlugins() {
  let payload;
  try {
    payload = await (await fetch("/api/plugins")).json();
  } catch (err) {
    // A loader that cannot be reached is itself a rank-0 event: every plugin
    // has gone quiet at once, and an empty strip would say the opposite.
    showAlerts([
      { source: "dashboard", what: `cannot reach the server (${err})`, detail: "" },
    ]);
    return;
  }
  // Rebuilt only when what the tiles returned actually changed. The poll is
  // every ten seconds and a rebuild throws away the panel's DOM, which is
  // where a typed filter and a chosen sort order live -- redrawing identical
  // markup would clear both, four times a minute, while the operator was
  // reading it. When the data does change the state goes with it, which is
  // the honest trade: the rows under a filter are no longer the rows it was
  // applied to.
  const signature = JSON.stringify(payload.tabs);
  if (signature === pluginSignature) {
    showAlerts(payload.rows.filter((row) => row.rank === 0));
    return;
  }
  pluginSignature = signature;
  const previous = (tabs.find(([button]) =>
    document.getElementById(button).getAttribute("aria-selected") === "true",
  ) || STATIC[0])[0];
  pluginNav.replaceChildren();
  pluginPanels.replaceChildren();
  tabs = STATIC.slice();
  const used = new Set();
  for (const tab of payload.tabs) {
    const id = panelId(tab, used);
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
  showAlerts(payload.rows.filter((row) => row.rank === 0));
}

drawIssues();
setInterval(drawIssues, 30000);

drawPlugins();
// Deliberately not the 30s of the other two: the plugin loader has its own
// five-second cache, and this is the view where a cron job going red is the
// thing being watched.
setInterval(drawPlugins, 10000);
