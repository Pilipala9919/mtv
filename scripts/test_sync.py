# Copyright (C) 2026 Pilipala
"""Offline checks: corrupt or unpublished update data must never replace a channel."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_release as sync

class SyncChecks(unittest.TestCase):
    def exercise(self, change=None, fail=False):
        data=b'APK fixture';sha=hashlib.sha256(data).hexdigest();name='MarcoTV-1.2.3.apk'
        url=f'https://github.com/{sync.SOURCE_REPO}/releases/download/v1.2.3/{name}'
        feed=dict(schema=1,versionCode=100,versionName='1.2.3',minSdk=23,size=len(data),sha256=sha,url=url,prerelease=False)
        release=dict(draft=False,prerelease=False,assets=[dict(name=name,browser_download_url=url,size=len(data),digest='sha256:'+sha),dict(name=name+'.sha256',browser_download_url=url+'.sha256')])
        altered=copy.deepcopy(feed)
        if change:change(altered,release)
        def fetch(address,binary=False):
            if address.endswith('/stable.json'):return json.dumps(feed)
            if address.endswith('/preview.json'):return json.dumps(altered)
            if '/releases/tags/' in address:return json.dumps(release)
            if address==url:return data
            if address==url+'.sha256':return sha+'  '+name
            raise AssertionError(address)
        with tempfile.TemporaryDirectory() as directory,patch.object(sync,'ROOT',Path(directory)),patch.object(sync,'fetch',fetch):
            existing=Path(directory)/'updates/stable.json';existing.parent.mkdir();existing.write_text('previous')
            if fail:
                with self.assertRaises(ValueError):sync.sync_update_channels()
                self.assertEqual(existing.read_text(),'previous')
            else:
                sync.sync_update_channels()
                self.assertEqual(json.loads(existing.read_text())['url'],'https://marcotv.wlj9919.top/'+name)
                self.assertEqual((Path(directory)/name).read_bytes(),data)
    def test_valid_channels(self):self.exercise()
    def test_bad_digest_keeps_old_index(self):self.exercise(lambda f,r:f.update(sha256='0'*64),True)
    def test_wrong_url_keeps_old_index(self):self.exercise(lambda f,r:f.update(url='https://example.org/test.apk'),True)
    def test_draft_keeps_old_index(self):self.exercise(lambda f,r:r.update(draft=True),True)
    def test_traversal_keeps_old_index(self):self.exercise(lambda f,r:f.update(versionName='../evil'),True)

class ChannelPageChecks(unittest.TestCase):
    def page(self, version):
        # Fixture mirrors the TV page layout: the update section sits
        # between the install section and the highlights section, each
        # with its own <section> wrapper.
        return sync.render_channels(
            '<p>以上为 0.11.1 实机截图</p>'
            '<section class="util rows" id="update"><h2>电视在线更新</h2><p class="intro">old</p></section>'
            '<section class="util" id="highlights"><h2>更新亮点</h2></section>',
            version)
    def test_stable_replaces_preview_label(self):
        page=self.page('0.12.0')
        self.assertIn('0.12.0 正式版',page)
        self.assertNotIn('old',page)
        self.assertIn('0.11.1 实机截图',page)
        self.assertIn('0.11.1 没有在线更新',page)
        self.assertIn('<section class="util rows" id="update">',page)
        self.assertIn('<section class="util" id="highlights"><h2>更新亮点</h2></section>',page)
        self.assertEqual(page.count('</section>'),2)
    def test_future_preview_and_repeated_sync(self):
        page=self.page('0.12.0')
        page=sync.render_channels(page,'0.13.0-rc.1')
        self.assertIn('0.13.0-rc.1 体验版',page)
        self.assertNotIn('0.12.0.apk',page)
        self.assertEqual(page,sync.render_channels(page,'0.13.0-rc.1'))
    def test_update_section_links_quark_not_mirror(self):
        # 2026-11-17 policy: the update section's version link is the
        # Quark manual download; the checksum link still points at the
        # GitHub release asset. The mirror APK stays hosted only for
        # the in-app update feeds.
        page=self.page('0.12.0')
        self.assertIn('https://pan.quark.cn/s/df36e65bca44',page)
        self.assertIn('https://github.com/Pilipala9919/MarcoTV/releases/download/v0.12.0/MarcoTV-0.12.0.apk.sha256',page)
        self.assertNotIn('href="https://github.com/Pilipala9919/MarcoTV/releases/download/v0.12.0/MarcoTV-0.12.0.apk"',page)
        self.assertNotIn('href="MarcoTV-0.12.0.apk"',page)
        self.assertNotIn('href="MarcoTV-0.12.0.apk.sha256"',page)
    def test_update_section_feed_links_are_root_absolute(self):
        # The TV page lives at /tv/: a relative updates/ link would
        # resolve to /tv/updates/ and break, so the feeds must be
        # root-absolute.
        page=self.page('0.12.0')
        self.assertIn('href="/updates/stable.json"',page)
        self.assertIn('href="/updates/preview.json"',page)
        self.assertNotIn('href="updates/stable.json"',page)
        self.assertNotIn('href="updates/preview.json"',page)
    def test_update_section_has_no_source_link(self):
        # No source download on the mirror site: the update section
        # links the APK, its checksum and the two update feeds only.
        page=self.page('0.12.0')
        self.assertNotIn('对应源码',page)
        self.assertNotIn('source-and-apk',page)

class InstallWizardChecks(unittest.TestCase):
    def setUp(self):
        self.app=(Path(sync.__file__).resolve().parent.parent/'install'/'app.js').read_text(encoding='utf-8')
    def test_no_mirror_download_buttons(self):
        # 2026-11-17 policy: the install wizard's TV download button is
        # Quark-only; the GitHub release URL stays in the file only as
        # the checksum base (sha.href=f.href+'.sha256'). The installer
        # tools have no Quark link, so they keep their GitHub raw links.
        # The mirror files stay hosted for in-app updates but are never
        # a visible manual download here.
        self.assertNotIn('marcotv.wlj9919.top',self.app)
        self.assertNotIn('base+file',self.app)
        self.assertNotIn("a.href=f.href;a.textContent=f.label;$('download').append(a);if(f.quark)",self.app)
        self.assertIn('https://pan.quark.cn/s/df36e65bca44',self.app)
        self.assertIn("sha.href=f.href+'.sha256'",self.app)
        self.assertIn('https://raw.githubusercontent.com/Pilipala9919/mtv/main/MarcoTV-Installer-1.0.1-Windows.exe',self.app)
        self.assertIn('https://raw.githubusercontent.com/Pilipala9919/mtv/main/MarcoTV-Installer-1.0.1-Android.apk',self.app)

class OfficialApkChecks(unittest.TestCase):
    def test_choose_apk_ignores_restricted(self):
        assets = {'MarcoTV-0.15.0-Restricted.apk': {}, 'MarcoTV-0.15.0.apk': {}}
        self.assertEqual(sync.choose_apk(assets, '0.15.0'), 'MarcoTV-0.15.0.apk')
        with self.assertRaises(ValueError):
            sync.choose_apk({'MarcoTV-0.15.0-Restricted.apk': {}}, '0.15.0')
    def test_main_syncs_official_apk_and_homepage_sha(self):
        # End to end with the real TV page as fixture: the release carries
        # both the official APK and the Restricted variant; the sync must
        # download the official one and stamp its SHA on the TV page.
        # The hub's TV version line is owned by this sync too (anchor
        # hub-tv-version); the hub's Movie line belongs to the Movie
        # patcher and the rest of the hub stays untouched.
        official = b'official apk fixture'
        osha = hashlib.sha256(official).hexdigest()
        ourl = f'https://github.com/{sync.SOURCE_REPO}/releases/download/v0.15.0/MarcoTV-0.15.0.apk'
        rurl = f'https://github.com/{sync.SOURCE_REPO}/releases/download/v0.15.0/MarcoTV-0.15.0-Restricted.apk'
        feed = dict(schema=1, versionCode=40, versionName='0.15.0', minSdk=23,
                    size=len(official), sha256=osha, url=ourl, prerelease=False)
        release = dict(draft=False, prerelease=False, assets=[
            dict(name='MarcoTV-0.15.0.apk', browser_download_url=ourl, size=len(official), digest='sha256:' + osha),
            dict(name='MarcoTV-0.15.0.apk.sha256', browser_download_url=ourl + '.sha256')])
        latest = dict(tag_name='v0.15.0', published_at='2026-11-03T00:00:00Z', assets=[
            dict(name='MarcoTV-0.15.0.apk', browser_download_url=ourl, size=len(official)),
            dict(name='MarcoTV-0.15.0-Restricted.apk', browser_download_url=rurl, size=1788190),
            dict(name='MarcoTV-0.15.0.apk.sha256', browser_download_url=ourl + '.sha256'),
            dict(name='MarcoTV-0.15.0-source-and-apk.zip', browser_download_url=ourl.replace('.apk', '-source-and-apk.zip'))])
        def fetch(address, binary=False):
            if address == sync.API:
                return json.dumps(latest)
            if address == ourl:
                return official
            if address == ourl + '.sha256':
                return osha + '  MarcoTV-0.15.0.apk'
            if address.endswith('/stable.json') or address.endswith('/preview.json'):
                return json.dumps(feed)
            if '/releases/tags/' in address:
                return json.dumps(release)
            raise AssertionError(address)
        root = Path(sync.__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory, patch.object(sync, 'ROOT', Path(directory)), patch.object(sync, 'INDEX', Path(directory) / 'tv' / 'index.html'), patch.object(sync, 'HUB', Path(directory) / 'index.html'), patch.object(sync, 'fetch', fetch):
            (Path(directory) / 'tv').mkdir()
            (Path(directory) / 'tv' / 'index.html').write_text((root / 'tv' / 'index.html').read_text(encoding='utf-8'), encoding='utf-8')
            (Path(directory) / 'index.html').write_text((root / 'index.html').read_text(encoding='utf-8'), encoding='utf-8')
            self.assertEqual(sync.main(), 0)
            self.assertEqual((Path(directory) / 'MarcoTV-0.15.0.apk').read_bytes(), official)
            self.assertFalse((Path(directory) / 'MarcoTV-0.15.0-Restricted.apk').exists())
            hub = (Path(directory) / 'index.html').read_text(encoding='utf-8')
            self.assertIn('<!--sync:hub-tv-version-->当前稳定版 0.15.0，2026 年 11 月 3 日发布<!--/sync:hub-tv-version-->', hub)
            self.assertNotIn('<!--sync:hub-tv-version-->当前稳定版 0.21.2', hub)
            self.assertIn('<!--sync:hub-movie-versions-->', hub)
            html = (Path(directory) / 'tv' / 'index.html').read_text(encoding='utf-8')
            self.assertIn(osha, html)
            self.assertNotIn('26a912eb31ccf7450ac9df6aead303b753c5f008550b2b6384ac0f542b8860f9', html)
            self.assertEqual(html.count('<!--sync:version-->0.15.0<!--/sync:version-->'), 2)
            self.assertNotIn('<!--sync:version-->0.19.0', html)
            self.assertIn('MarcoTV-0.15.0.apk', html)
            self.assertIn('0.15.0 正式版', html)
            self.assertIn('<section class="util" id="highlights">', html)

class SyncAnchorChecks(unittest.TestCase):
    def test_replace_anchor_updates_all_marked_spots(self):
        html = '<p><!--sync:version-->0.19.0<!--/sync:version--> and <!--sync:version-->0.19.0<!--/sync:version--></p>'
        out = sync._replace_anchor(html, 'version', '0.20.0')
        self.assertEqual(out.count('<!--sync:version-->0.20.0<!--/sync:version-->'), 2)
    def test_replace_anchor_missing_raises(self):
        with self.assertRaises(ValueError):
            sync._replace_anchor('<p>no anchors here</p>', 'version', '0.20.0')
    def test_tv_page_has_sync_anchors(self):
        # Pins the contract between tv/index.html and the sync: every
        # anchor the script requires must exist, exactly as many times
        # as the page design expects (hero + download section).
        root = Path(sync.__file__).resolve().parent.parent
        html = (root / 'tv' / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('<!--sync:version-->'), 2)
        self.assertEqual(html.count('<!--sync:release-date-->'), 2)
        self.assertEqual(html.count('<!--sync:size-->'), 2)
        self.assertEqual(html.count('<!--sync:sha256-->'), 1)
    def test_hub_has_sync_anchors(self):
        # Pins the contract between the hub and both syncs: the TV line
        # is owned by sync_release.py, the Movie line by
        # sync_platform_packages.py; each anchor appears exactly once.
        root = Path(sync.__file__).resolve().parent.parent
        html = (root / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('<!--sync:hub-tv-version-->'), 1)
        self.assertEqual(html.count('<!--sync:hub-movie-versions-->'), 1)

if __name__=='__main__':unittest.main()
