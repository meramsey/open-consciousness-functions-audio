(() => {
  const status = document.getElementById('empty-state');
  const count = document.getElementById('release-count');
  fetch('catalog.json')
    .then(response => {
      if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
      return response.json();
    })
    .then(catalog => {
      const releases = Array.isArray(catalog.releases) ? catalog.releases : [];
      count.textContent = `${releases.length} ${releases.length === 1 ? 'release' : 'releases'}`;
      status.hidden = releases.length > 0;
    })
    .catch(() => {
      count.textContent = 'Catalog unavailable';
      status.hidden = false;
    });
})();
