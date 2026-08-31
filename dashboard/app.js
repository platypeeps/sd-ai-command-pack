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

const tabs = [
  ["tab-repos", "panel-repos"],
  ["tab-issues", "panel-issues"],
];

for (const [button, panel] of tabs) {
  document.getElementById(button).addEventListener("click", () => {
    for (const [b, p] of tabs) {
      const on = b === button;
      document.getElementById(b).setAttribute("aria-selected", String(on));
      document.getElementById(p).hidden = !on;
    }
  });
}

drawIssues();
setInterval(drawIssues, 30000);
