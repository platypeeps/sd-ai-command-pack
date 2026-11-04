// Operations (pack sd:7266): Fleet's Operations section, operations_screen's areas as the shell's views. It loads before
// shell.js, which draws them as the rail's sub-entries. The ids and labels are operations_screen.AREAS, in its order.
// The server draws only the area ?area= names (Resources with none) into its view-<id> panel; the others hold a line. So the
// drawn area is the view: an address with no #view= takes the drawn one, which also outranks the view kept from the last
// visit, and a view shown that is not drawn (a rail sub-entry, a v key, a #view= address) loads that area's address.
window.PAGE_VIEWS = [{ id: 'resources', label: 'Resources' }, { id: 'trackers', label: 'Trackers' }];
(() => {
  const ids = window.PAGE_VIEWS.map(v => v.id);
  const drawn = new URLSearchParams(location.search).get('area') || ids[0];
  const asked = (/^#view=([a-z0-9-]+)$/.exec(location.hash) || [])[1];
  // pack sd:7517: a retired area's old view address opens the view that holds it now (operations_screen.MOVED).
  const moved = { services: '/management#view=deploys', sessions: '/management#view=sessions', usage: '/metrics#view=spend' }[asked];
  if (moved) { location.replace(moved); return; }
  if (!ids.includes(asked)) try { history.replaceState(history.state, '', `#view=${drawn}`); } catch (_) {}
  // The shell fires only a declared view, whose id is [a-z0-9-]+: one of the kept areas.
  const open = id => location.replace(`/operations?area=${id}#view=${id}`);
  document.addEventListener('shell:view', e => { if (e.detail.id !== drawn) open(e.detail.id); });
})();
