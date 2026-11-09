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
        return sync.render_channels('<p>以上为 0.11.1 实机截图</p><h2>体验版与电视在线更新</h2><p>old</p><h2>先核对你的电视能不能装</h2>', version)
    def test_stable_replaces_preview_label(self):
        page=self.page('0.12.0')
        self.assertIn('0.12.0 正式版',page)
        self.assertNotIn('old',page)
        self.assertIn('0.11.1 实机截图',page)
        self.assertIn('0.11.1 没有在线更新',page)
    def test_future_preview_and_repeated_sync(self):
        page=self.page('0.12.0')
        page=sync.render_channels(page,'0.13.0-rc.1')
        self.assertIn('0.13.0-rc.1 体验版',page)
        self.assertNotIn('0.12.0.apk',page)
        self.assertEqual(page,sync.render_channels(page,'0.13.0-rc.1'))
    def test_update_section_links_github_not_mirror(self):
        # The update section's version and checksum links are manual
        # downloads, so they point at the GitHub release asset; the
        # mirror APK stays hosted only for the in-app update feeds.
        page=self.page('0.12.0')
        self.assertIn('https://github.com/Pilipala9919/MarcoTV/releases/download/v0.12.0/MarcoTV-0.12.0.apk',page)
        self.assertIn('https://github.com/Pilipala9919/MarcoTV/releases/download/v0.12.0/MarcoTV-0.12.0.apk.sha256',page)
        self.assertNotIn('href="MarcoTV-0.12.0.apk"',page)
        self.assertNotIn('href="MarcoTV-0.12.0.apk.sha256"',page)

class InstallWizardChecks(unittest.TestCase):
    def setUp(self):
        self.app=(Path(sync.__file__).resolve().parent.parent/'install'/'app.js').read_text(encoding='utf-8')
    def test_no_mirror_download_buttons(self):
        # The install wizard's download buttons are GitHub (the TV APK
        # also offers Quark); the mirror files stay hosted for in-app
        # updates but are never a visible manual download here.
        self.assertNotIn('marcotv.wlj9919.top',self.app)
        self.assertNotIn('base+file',self.app)
        self.assertIn('https://github.com/Pilipala9919/MarcoTV/releases/download/v0.15.0/MarcoTV-0.15.0.apk',self.app)
        self.assertIn('https://pan.quark.cn/s/df36e65bca44',self.app)
        self.assertIn('https://raw.githubusercontent.com/Pilipala9919/mtv/main/MarcoTV-Installer-1.0.0-Windows.exe',self.app)
        self.assertIn('https://raw.githubusercontent.com/Pilipala9919/mtv/main/MarcoTV-Installer-1.0.0-Android.apk',self.app)

class OfficialApkChecks(unittest.TestCase):
    def test_choose_apk_ignores_restricted(self):
        assets = {'MarcoTV-0.15.0-Restricted.apk': {}, 'MarcoTV-0.15.0.apk': {}}
        self.assertEqual(sync.choose_apk(assets, '0.15.0'), 'MarcoTV-0.15.0.apk')
        with self.assertRaises(ValueError):
            sync.choose_apk({'MarcoTV-0.15.0-Restricted.apk': {}}, '0.15.0')
    def test_main_syncs_official_apk_and_homepage_sha(self):
        # End to end with the real homepage as fixture: the release carries
        # both the official APK and the Restricted variant; the sync must
        # download the official one and stamp its SHA on the homepage.
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
        with tempfile.TemporaryDirectory() as directory, patch.object(sync, 'ROOT', Path(directory)), patch.object(sync, 'fetch', fetch):
            (Path(directory) / 'index.html').write_text((root / 'index.html').read_text(encoding='utf-8'), encoding='utf-8')
            self.assertEqual(sync.main(), 0)
            self.assertEqual((Path(directory) / 'MarcoTV-0.15.0.apk').read_bytes(), official)
            self.assertFalse((Path(directory) / 'MarcoTV-0.15.0-Restricted.apk').exists())
            html = (Path(directory) / 'index.html').read_text(encoding='utf-8')
            self.assertIn(osha, html)
            self.assertNotIn('ef6fd9257e7c0364198e13c3021932fd35902919ee9a8f9ddd1b4a64977bf672', html)

if __name__=='__main__':unittest.main()
