// The whole client. One file, no build step, no framework: the page polls
// /api/state and redraws a table, and anything more elaborate would be a
// toolchain to maintain for a view that fits on one screen.
const rows = document.getElementById("rows");
const sub = document.getElementById("sub");

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
