// Progressive enhancement: every package and release remains available without JS.
(() => {
  const download = document.querySelector('#download-platform');
  const releases = document.querySelector('#release-platform');
  if (download) {
    download.closest('label').hidden = false;
    download.addEventListener('change', () => {
      document.querySelectorAll('.dl').forEach(card => {
        card.hidden = download.value !== 'all' && card.dataset.platform !== download.value;
      });
    });
  }
  if (releases) {
    releases.closest('label').hidden = false;
    releases.addEventListener('change', () => {
      let visible = 0;
      document.querySelectorAll('.release-entry').forEach(entry => {
        const matches = releases.value === 'all' || entry.dataset.platforms.split(' ').includes(releases.value);
        entry.hidden = !matches;
        if (matches) visible++;
      });
      const archive = document.querySelector('.release-archive');
      if (archive) {
        const count = archive.querySelectorAll('.release-entry:not([hidden])').length;
        archive.hidden = !count;
        archive.querySelector('summary span').textContent = count + ' 个版本';
        if (releases.value !== 'all' && !document.querySelector('.current-releases .release-entry:not([hidden])')) archive.open = !!count;
      }
      document.querySelector('#release-empty').hidden = visible !== 0;
    });
  }
})();
