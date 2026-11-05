// Operations moved (pack sd:7517): the bare /operations lists where each area went (operations_screen.moved_page), one
// link per area, named by data-view. Only the browser sees an old #view=<area> address, so this follows the link that
// names it, or Trackers' when there is none, the area the page opened on; an unknown view stays on the list.
(() => {
  const id = (/^#view=([a-z0-9-]+)$/.exec(location.hash) || [])[1] || 'trackers';
  const link = document.querySelector(`a[data-view="${id}"]`);
  if (link) location.replace(link.getAttribute('href'));
})();
