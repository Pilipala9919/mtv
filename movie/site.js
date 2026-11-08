// Progressive enhancement: every package and release remains available without JS.
(() => {
  const ghPrefix = 'https://github.com/Pilipala9919/MarcoMovie/releases/download/';
  document.querySelectorAll('.dl').forEach(card => {
    const primary = card.querySelector('a.btn.primary[href]');
    if (!primary || !primary.href.startsWith(ghPrefix)) return;
    const rawHref = primary.href;
    const rest = rawHref.slice(ghPrefix.length);
    primary.href = '/movie/dl/' + rest;
    const check = card.querySelector('.package-check');
    if (check) {
      const shaLink = check.querySelector('a[href]');
      if (shaLink && shaLink.href.startsWith(ghPrefix)) {
        shaLink.href = '/movie/dl/' + shaLink.href.slice(ghPrefix.length);
      }
      const p = check.querySelector('p');
      if (p && !p.querySelector('.gh-direct-link')) {
        const sep = document.createTextNode(' · ');
        const direct = document.createElement('a');
        direct.className = 'gh-direct-link';
        direct.href = rawHref;
        direct.textContent = 'GitHub 原生直链';
        p.append(sep, direct);
      }
    }
  });
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
