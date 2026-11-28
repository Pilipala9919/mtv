"""Offline mirror contract tests; no release upload or network access."""
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import sync_movie_mirror as m


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'movie'
        self.release = dict(tag_name='v0.4.12-preview', published_at='2026-11-01', prerelease=True,
                            draft=False, body='<script>example</script>', assets=[])
        self.data = {}
        source = io.BytesIO()
        with zipfile.ZipFile(source, 'w') as z:
            z.writestr('MarcoMovie-0.4.12/LICENSE', 'GPL-3.0-only')
            z.writestr('MarcoMovie-0.4.12/NOTICE', 'Pilipala')
        for name, body in [('MarcoMovie-0.4.12-preview.apk', b'apk fixture'), ('MarcoMovie-0.4.12-source.zip', source.getvalue())]:
            url = f'https://github.com/{m.REPO}/releases/download/v0.4.12-preview/{name}'
            sha = hashlib.sha256(body).hexdigest()
            for suffix, payload in [('', body), ('.sha256', (sha + '  ' + name).encode())]:
                self.release['assets'].append(dict(name=name+suffix, state='uploaded', browser_download_url=url+suffix,
                                                   size=len(payload), digest='sha256:'+hashlib.sha256(payload).hexdigest()))
                self.data[url+suffix] = payload
        self.identity = dict(package='com.pilipala.marcomovie', versionName='0.4.12', versionCode=25, minSdk=23)
        self.stars = 602
        self.stars_error = False

    def fetch(self, url, limit=m.LIMIT):
        if url == f'https://api.github.com/repos/{m.REPO}':
            if self.stars_error:
                raise OSError('stars API unreachable')
            return json.dumps({'stargazers_count': self.stars}).encode()
        if url.startswith('https://api.github.com/'):
            return json.dumps([self.release]).encode()
        return self.data[url]

    def sync(self):
        with patch.object(m, 'fetch', self.fetch), patch.object(m, 'apk_identity', return_value=self.identity):
            return m.sync(self.out)

    def test_latest_numeric_preview_only(self):
        older = dict(self.release, tag_name='v0.4.9-preview')
        draft = dict(self.release, tag_name='v99.0.0-preview', draft=True)
        stable = dict(self.release, tag_name='v99.0.0', prerelease=False)
        self.assertEqual(m.choose([older, self.release, draft, stable])['tag_name'], 'v0.4.12-preview')
        with self.assertRaises(ValueError): m.choose([draft, stable])

    def test_complete_snapshot_and_repeat(self):
        unrelated = self.out.parent/'index.html'
        unrelated.write_text('Marco TV')
        feed = self.sync()
        self.assertEqual(feed['versionCode'], 25)
        self.assertEqual(feed['url'], m.BASE+'MarcoMovie-0.4.12-preview.apk')
        self.assertEqual(json.loads((self.out/'updates/preview.json').read_text(encoding='utf-8')), feed)
        self.assertIn('&lt;script&gt;', (self.out/'index.html').read_text(encoding='utf-8'))
        self.assertEqual(unrelated.read_text(), 'Marco TV')
        self.assertEqual(self.sync(), feed)

    def test_wrong_release_checksum_leaves_feed_unchanged(self):
        self.sync()
        before = (self.out/'updates/preview.json').read_bytes()
        name='MarcoMovie-0.4.12-preview.apk'
        (self.out/name).write_bytes(b'bad')
        with self.assertRaises(ValueError): self.sync()
        self.assertEqual((self.out/'updates/preview.json').read_bytes(), before)

    def test_wrong_asset_host(self):
        self.release['assets'][0]['browser_download_url']='https://example.invalid/file.apk'
        with self.assertRaises(ValueError): self.sync()
        self.assertFalse(self.out.exists())

    def test_wrong_apk_version(self):
        self.identity['versionName']='0.4.13'
        with self.assertRaises(ValueError): self.sync()
        self.assertFalse(self.out.exists())

    def test_reject_rollback(self):
        self.sync()
        self.identity['versionCode']=24
        with self.assertRaises(ValueError): self.sync()
        self.assertEqual(json.loads((self.out/'updates/preview.json').read_text(encoding='utf-8'))['versionCode'],25)

    def test_pages_size_limit(self):
        self.release['assets'][0]['size']=m.LIMIT+1
        with self.assertRaises(ValueError): self.sync()

    def test_invalid_manifest_rejected(self):
        source=io.BytesIO()
        with zipfile.ZipFile(source,'w') as z: z.writestr('AndroidManifest.xml',b'<manifest/>')
        with self.assertRaises(ValueError): m.apk_identity(source.getvalue())

    def test_large_tv_package_is_verified_and_linked_from_checksum_and_feed(self):
        name='MarcoMovie-0.4.12-preview.apk'
        self.release['assets']=[a for a in self.release['assets'] if a['name'] not in (name,name+'.sha256')]
        self.add_asset(name,b'large apk fixture' * (m.LIMIT//17+2))
        feed=self.sync()
        expected=f'https://github.com/{m.REPO}/releases/download/v0.4.12-preview/{name}'
        self.assertEqual(feed['url'],expected)
        self.assertFalse((self.out/name).exists())
        # 2026-11-17 policy: the card's download button is Quark-only, so
        # the GitHub asset URL only survives on the page as the checksum
        # file link; the feed still carries the verified release URL.
        self.assertIn('href="'+expected+'.sha256"',(self.out/'index.html').read_text(encoding='utf8'))
        self.assertNotIn('href="'+expected+'"',(self.out/'index.html').read_text(encoding='utf8'))

    def test_official_release_updates_stable_channel(self):
        self.release['prerelease']=False
        feed=self.sync()
        self.assertFalse(feed['prerelease'])
        self.assertEqual(json.loads((self.out/'updates/stable.json').read_text(encoding='utf8')),feed)

    def test_hero_has_no_download_buttons_and_cards_use_quark(self):
        # 2026-11-22 layout: the hero has no download buttons at all
        # (only a "全部平台" text link to #download); the card buttons
        # point at the permanent Quark share links, not at the release
        # assets; the feed still carries the verified release URL for
        # the in-app updater.
        name='MarcoMovie-0.4.12-mobile.apk';self.add_asset(name,b'mobile fixture')
        next(a for a in self.release['assets'] if a['name']==name)['size']=m.LIMIT+1
        links = {'android-tv': 'https://pan.quark.cn/s/tv123',
                 'android-mobile': 'https://pan.quark.cn/s/mo456'}
        with patch.object(m, 'load_quark_links', return_value=links):
            feed=self.sync()
        page=(self.out/'index.html').read_text(encoding='utf8')
        hero = page.split('<header class="hero">')[1].split('</header>')[0]
        self.assertNotIn('pan.quark.cn', hero)
        self.assertNotIn('>下载</a>', hero)
        self.assertIn('<a class="textlink" href="#download">全部平台</a>', hero)
        self.assertIn('href="https://pan.quark.cn/s/mo456" target="_blank" rel="noopener">下载</a>', page)
        self.assertNotIn('href="'+feed['mobile']['url']+'"', page)
        self.assertNotIn('href="'+name+'"',page)

    def add_asset(self, name, body, checksum=True):
        url = f'https://github.com/{m.REPO}/releases/download/v0.4.12-preview/{name}'
        sha = hashlib.sha256(body).hexdigest()
        items = [('', body)] + ([('.sha256', (sha + '  ' + name).encode())] if checksum else [])
        for suffix, payload in items:
            self.release['assets'].append(dict(name=name+suffix, state='uploaded', browser_download_url=url+suffix,
                                               size=len(payload), digest='sha256:'+hashlib.sha256(payload).hexdigest()))
            self.data[url+suffix] = payload

    def test_platform_packages_mirrored_when_published(self):
        self.add_asset('MarcoMovie-0.4.12-windows-x64.zip', b'windows fixture')
        self.add_asset('MarcoMovie-0.4.12-ios-unsigned.ipa', b'ios fixture')
        self.sync()
        self.assertEqual((self.out/'MarcoMovie-0.4.12-windows-x64.zip').read_bytes(), b'windows fixture')
        self.assertTrue((self.out/'MarcoMovie-0.4.12-ios-unsigned.ipa.sha256').exists())
        self.assertFalse((self.out/'MarcoMovie-0.4.12-macos.zip').exists())
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertIn('MarcoMovie-0.4.12-windows-x64.zip', page)
        self.assertIn('全平台独立更新', page)

    def test_platform_package_without_checksum_rejected(self):
        self.add_asset('MarcoMovie-0.4.12-macos.zip', b'mac fixture', checksum=False)
        with self.assertRaises(ValueError): self.sync()
        self.assertFalse(self.out.exists())

    def test_large_platform_package_links_github_not_copied(self):
        self.add_asset('MarcoMovie-0.4.12-windows-x64.zip', b'windows fixture')
        big = [a for a in self.release['assets'] if a['name'] == 'MarcoMovie-0.4.12-windows-x64.zip'][0]
        big['size'] = m.LIMIT + 1
        self.sync()
        self.assertFalse((self.out/'MarcoMovie-0.4.12-windows-x64.zip').exists())
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertIn(f'https://github.com/{m.REPO}/releases/download/v0.4.12-preview/MarcoMovie-0.4.12-windows-x64.zip', page)

    def test_without_platform_packages_links_release_page(self):
        self.sync()
        self.assertIn('Windows / macOS / iOS 多平台下载', (self.out/'index.html').read_text(encoding='utf-8'))

    def test_new_layout_section_order_and_card_markup(self):
        # 2026-11-22 layout: hero -> download -> donate -> features ->
        # changelog -> group -> footer; cards carry the patcher contract
        # (data-platform, package-version span, one size, one checksum,
        # one checksum link) and the page ships the filter script the
        # platform patcher-generated changelog needs.
        self.add_asset('MarcoMovie-0.4.12-mobile.apk', b'mobile fixture')
        links = {'android-tv': 'https://pan.quark.cn/s/tv123',
                 'android-mobile': 'https://pan.quark.cn/s/mo456'}
        with patch.object(m, 'load_quark_links', return_value=links):
            self.sync()
        page = (self.out/'index.html').read_text(encoding='utf-8')
        order = ['<header class="hero">', 'id="download"', 'id="club"', 'id="donate"',
                 'id="features"', 'id="changelog"', '<footer>']
        positions = [page.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(page.count('<div class="dl"'), 2)
        self.assertIn('<div class="dl" data-platform="android-tv">', page)
        self.assertIn('<div class="dl" data-platform="android-mobile">', page)
        self.assertIn('<span class="package-version">0.4.12</span>', page)
        self.assertIn('src="/assets/donate-wechat.jpg"', page)
        self.assertIn('src="/assets/donate-alipay.jpg"', page)
        self.assertIn("document.getElementById('release-platform')", page)

    def test_changelog_numbered_items_render_as_list(self):
        body = ('\ufeff### Marco Movie 0.4.12 正式版更新内容\n\n'
                '1. **搜索结果驻留保持（全平台）**：\n'
                '   - 从搜索结果进详情页再返回，关键词与滚动位置完整保留。\n'
                '2. **跳片头 / 跳片尾支持手动拖拽**：\n'
                '   - 新增 0~300 秒拖拽滑块。\n')
        self.assertIn('<ol class="feats">', m.render_changelog(body))
        self.assertIn('搜索结果驻留保持', m.render_changelog(body))
        self.assertIn('从搜索结果进详情页再返回', m.render_changelog(body))
        self.assertNotIn('<script>', m.render_changelog(body + '<script>example</script>'))

    def test_changelog_without_numbered_items_escapes_html(self):
        rendered = m.render_changelog('<script>example</script>')
        self.assertIn('&lt;script&gt;', rendered)
        self.assertNotIn('<script>', rendered)

    def test_windows_setup_platform_listed_when_published(self):
        self.add_asset('MarcoMovie-0.4.12-windows-setup.exe', b'setup fixture')
        self.sync()
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertIn('MarcoMovie-0.4.12-windows-setup.exe', page)
        self.assertIn('Windows 安装版', page)

    def test_group_section_removed_and_showcase_frames_removed(self):
        self.sync()
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertNotIn('id="group"', page)
        self.assertNotIn('官方交流群', page)
        self.assertNotIn('qun.qq.com', page)
        self.assertNotIn('815085102', page)
        self.assertNotIn('加入 QQ 群', page)
        self.assertNotIn('画面展示', page)
        self.assertNotIn('界面示意', page)
        self.assertNotIn('class="shots"', page)

    def test_tencent_channel_section_present(self):
        self.sync()
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertIn('id="channel"', page)
        self.assertIn('腾讯频道', page)
        self.assertIn('Marco交流区', page)
        self.assertIn('https://pd.qq.com/s/N45e3aaawv?b=9', page)
        self.assertIn('加入腾讯频道', page)
        self.assertIn('反馈 bug、功能建议、适配版本等需求，请到频道对应板块提交。', page)
        self.assertIn('<a class="textlink" href="#channel">交流区</a>', page)
        self.assertIn('<a class="btn btn-primary" href="https://pd.qq.com/s/N45e3aaawv?b=9" target="_blank" rel="noopener">加入腾讯频道</a>', page)
        self.assertLess(page.index('id="download"'), page.index('id="channel"'))
        self.assertLess(page.index('id="channel"'), page.index('id="club"'))
        self.assertLess(page.index('id="club"'), page.index('id="donate"'))

    def test_club_channel_section_present(self):
        self.sync()
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertIn('id="club"', page)
        self.assertIn('俱乐部', page)
        self.assertIn('Marco俱乐部', page)
        self.assertIn('https://pd.qq.com/s/f8tm7swar8?b=9', page)
        self.assertIn('加入俱乐部', page)
        self.assertIn('加入需要提交赞助或捐赠截图，人工审核通过后进频道。', page)
        self.assertIn('<a class="textlink" href="#club">俱乐部</a>', page)
        self.assertIn('<a class="btn btn-primary" href="https://pd.qq.com/s/f8tm7swar8?b=9" target="_blank" rel="noopener">加入俱乐部【捐赠赞助后加入】</a>', page)
        self.assertIn('.btn{display:inline-block;text-align:center;text-decoration:none;', page)
        self.assertLess(page.index('id="download"'), page.index('id="channel"'))
        self.assertLess(page.index('id="channel"'), page.index('id="club"'))
        self.assertLess(page.index('id="club"'), page.index('id="donate"'))

    def test_brand_assets_and_dark_hero_frame(self):
        self.sync()
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertIn('<link rel="icon" type="image/png" href="/assets/movie-icon-512.png">', page)
        self.assertIn('<link rel="apple-touch-icon" href="/assets/movie-icon-512.png">', page)
        self.assertIn('src="assets/movie-wordmark-dark.png"', page)
        self.assertIn('src="/assets/marco-symbol.png"', page)
        self.assertIn('<a class="textlink" href="#download">全部平台</a>', page)
        self.assertNotIn('app-icon-512.png', page)
        self.assertNotIn('tv-banner-960x540.png', page)
        self.assertNotIn('Marco Movie 品牌横幅', page)
        self.assertNotIn('银色场记板', page)
        # The hero carries no download button: only the text link above.
        hero = page.split('<header class="hero">')[1].split('</header>')[0]
        self.assertNotIn('class="btn', hero)

    def test_stars_rendered_from_repo_api(self):
        self.sync()
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertIn('<b>602 Stars</b>', page)
        self.assertNotIn('165 Stars', page)
        self.assertNotIn('ver-tag', page)
        self.assertNotIn('同版本源码', page)

    def test_stars_fallback_when_api_fails(self):
        self.stars_error = True
        self.sync()
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertIn('<b>602 Stars</b>', page)
        (self.out/'index.html').write_text(page.replace('<b>602 Stars</b>', '<b>599 Stars</b>'), encoding='utf-8')
        self.sync()
        page = (self.out/'index.html').read_text(encoding='utf-8')
        self.assertIn('<b>599 Stars</b>', page)

    def test_quark_asset_keys(self):
        self.assertEqual(m.quark_key_for_asset('MarcoMovie-0.5.9-android-tv.apk'), None)
        self.assertEqual(m.quark_key_for_asset('MarcoMovie-0.5.9-mobile.apk'), 'android-mobile')
        self.assertEqual(m.quark_key_for_asset('MarcoMovie-0.5.5-ios-unsigned.ipa'), 'ios')
        self.assertEqual(m.quark_key_for_asset('MarcoMovie-0.5.3-windows-x64-setup.exe'), 'windows-setup')
        self.assertEqual(m.quark_key_for_asset('MarcoMovie-0.5.3-windows-x64-portable.zip'), 'windows-zip')
        self.assertEqual(m.quark_key_for_asset('MarcoMovie-0.5.2-macos.zip'), 'macos')
        self.assertEqual(m.quark_key_for_asset('MarcoMovie-0.5.0-lite.apk'), 'android-lite')
        self.assertEqual(m.quark_button('android-tv', {}), '')
        self.assertIn('>下载</a>', m.quark_button('android-tv', {'android-tv': 'https://pan.quark.cn/s/abc'}))

    def test_quark_buttons_render_from_manifest(self):
        links = {'android-tv': 'https://pan.quark.cn/s/tv123',
                 'android-mobile': 'https://pan.quark.cn/s/mo456'}
        with patch.object(m, 'load_quark_links', return_value=links):
            self.sync()
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('https://pan.quark.cn/s/tv123', page)
        self.assertIn('>下载</a>', page)

    def test_platform_feed_override_tv_card(self):
        # The user's per-platform feeds override a card with that platform's
        # latest version (TV 0.5.9 while the release is 0.4.12): the card
        # shows the override version, URL, size and checksum; the card
        # button points at the permanent Quark share link.
        (self.out / 'updates').mkdir(parents=True)
        (self.out / 'updates' / 'android-tv.json').write_text(json.dumps({
            "versionName": "0.5.9", "packages": {
                "MarcoMovie-0.5.9-android-tv.apk": {
                    "url": "https://github.com/Pilipala9919/MarcoMovie/releases/download/v0.5.9-android-tv/MarcoMovie-0.5.9-android-tv.apk",
                    "size": 1234567, "sha256": "a" * 64}}}), encoding='utf-8')
        links = {'android-tv': 'https://pan.quark.cn/s/tv123'}
        with patch.object(m, 'load_quark_links', return_value=links):
            self.sync()
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<span class="package-version">0.5.9</span>', page)
        self.assertIn('https://github.com/Pilipala9919/MarcoMovie/releases/download/v0.5.9-android-tv/MarcoMovie-0.5.9-android-tv.apk', page)
        self.assertIn('1.2 MB', page)
        self.assertIn('a' * 64, page)
        self.assertIn('href="https://pan.quark.cn/s/tv123" target="_blank" rel="noopener">下载</a>', page)

    def test_platform_feed_override_platform_card_new_schema(self):
        # The iOS feed uses the new single-package shape (0.5.6).
        (self.out / 'updates').mkdir(parents=True)
        (self.out / 'updates' / 'ios-preview.json').write_text(json.dumps({
            "version": "0.5.6", "package": {
                "name": "MarcoMovie-0.5.6-ios-iphone-ipad-unsigned.ipa",
                "url": "https://github.com/Pilipala9919/MarcoMovie/releases/download/ios-v0.5.6-preview/MarcoMovie-0.5.6-ios-iphone-ipad-unsigned.ipa",
                "size": 65121228, "sha256": "b" * 64}}), encoding='utf-8')
        self.add_asset('MarcoMovie-0.4.12-ios-unsigned.ipa', b'ios fixture')
        self.sync()
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('iPhone / iPad 版 (IPA)', page)
        self.assertIn('<span class="package-version">0.5.6</span>', page)
        self.assertIn('https://github.com/Pilipala9919/MarcoMovie/releases/download/ios-v0.5.6-preview/MarcoMovie-0.5.6-ios-iphone-ipad-unsigned.ipa', page)
        self.assertIn('b' * 64, page)
        (self.out / 'updates' / 'android-lite.json').write_text(json.dumps({
            "versionName": "0.5.1", "packages": {
                "MarcoMovie-0.5.1-android-lite.apk": {
                    "url": "https://github.com/Pilipala9919/MarcoMovie/releases/download/android-lite-v0.5.1/MarcoMovie-0.5.1-android-lite.apk",
                    "size": 348928, "sha256": "c" * 64}}}), encoding='utf-8')
        self.add_asset('MarcoMovie-0.4.12-lite.apk', b'lite fixture')
        self.sync()
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('Android 4.0+ 轻量版', page)
        self.assertIn('<span class="package-version">0.5.1</span>', page)
        self.assertIn('https://github.com/Pilipala9919/MarcoMovie/releases/download/android-lite-v0.5.1/MarcoMovie-0.5.1-android-lite.apk', page)
        self.assertIn('c' * 64, page)

    def test_platform_feed_override_missing_falls_back(self):
        self.sync()
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h3>Android 电视版 ', page)
        self.assertIn('<span class="package-version">0.4.12</span>', page)
        self.assertNotIn('· v', page)

    def test_no_quark_buttons_without_manifest(self):
        # The workflow checkout contains scripts/quark.json, so isolate the
        # manifest read; otherwise this test only passes when the file is absent.
        with patch.object(m, 'load_quark_links', return_value={}):
            self.sync()
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('pan.quark.cn', page)
        self.assertNotIn('>下载</a>', page)
        # With no Quark links there are no download buttons at all: the
        # card buttons are Quark-only, and the hero has no buttons.
        self.assertNotIn('>下载电视版</a>', page)
        self.assertNotIn('>下载手机版</a>', page)

    def test_download_buttons_are_quark_only(self):
        # 2026-11-17 policy: mirror files stay hosted for the feeds, but
        # every card's download button is Quark-only; the GitHub asset
        # URL only survives on the page as the checksum file link.
        self.add_asset('MarcoMovie-0.4.12-mobile.apk', b'mobile fixture')
        links = {'android-tv': 'https://pan.quark.cn/s/tv123',
                 'android-mobile': 'https://pan.quark.cn/s/mo456'}
        with patch.object(m, 'load_quark_links', return_value=links):
            self.sync()
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        tv_gh = 'https://github.com/Pilipala9919/MarcoMovie/releases/download/v0.4.12-preview/MarcoMovie-0.4.12-preview.apk'
        mobile_gh = 'https://github.com/Pilipala9919/MarcoMovie/releases/download/v0.4.12-preview/MarcoMovie-0.4.12-mobile.apk'
        self.assertNotIn('去 GitHub 下载', page)
        self.assertIn('href="' + tv_gh + '.sha256"', page)
        self.assertIn('href="' + mobile_gh + '.sha256"', page)
        self.assertIn('https://pan.quark.cn/s/tv123', page)
        self.assertIn('https://pan.quark.cn/s/mo456', page)
        self.assertTrue((self.out / 'MarcoMovie-0.4.12-preview.apk').exists())
        self.assertTrue((self.out / 'MarcoMovie-0.4.12-mobile.apk').exists())

    def test_no_mirror_package_links_on_page(self):
        # Mirror files stay hosted for the in-app feeds, but the rendered
        # page must not offer any manually clickable mirror package
        # download; 2026-11-17 policy: every package href is Quark-only.
        self.add_asset('MarcoMovie-0.4.12-mobile.apk', b'mobile fixture')
        links = {'android-tv': 'https://pan.quark.cn/s/tv123',
                 'android-mobile': 'https://pan.quark.cn/s/mo456'}
        with patch.object(m, 'load_quark_links', return_value=links):
            feed = self.sync()
        page = (self.out / 'index.html').read_text(encoding='utf-8')
        for href in re.findall(r'href="([^"]+)"', page):
            bare = href.split('?')[0].split('#')[0].lower()
            if bare.endswith(('.apk', '.ipa', '.zip', '.exe')):
                self.assertTrue(href.startswith('https://pan.quark.cn/'), href)
        self.assertTrue(feed['url'].startswith('https://marcotv.wlj9919.top/movie/'))

    def test_mirror_package_link_in_changelog_stays_plain_text(self):
        # A release note may link the mirror download page, but never a
        # mirror package file: that would be a manual mirror download.
        body = ('9. **安装包与源码**\n'
                '   - [电视安装包](https://marcotv.wlj9919.top/movie/MarcoMovie-0.4.12-preview.apk)\n'
                '   - [镜像下载页](https://marcotv.wlj9919.top/movie/)\n')
        rendered = m.render_changelog(body)
        self.assertNotIn('href="https://marcotv.wlj9919.top/movie/MarcoMovie-0.4.12-preview.apk"', rendered)
        self.assertIn('[电视安装包](https://marcotv.wlj9919.top/movie/MarcoMovie-0.4.12-preview.apk)', rendered)
        self.assertIn('<a href="https://marcotv.wlj9919.top/movie/">镜像下载页</a>', rendered)

    def test_sub_bullets_do_not_consume_list_numbers(self):
        # The CSS counter must count top-level items only: with the old
        # "ol.feats li" selector a sub-bullet ate number 10, so 0.5.0
        # showed 9 then 11.
        self.assertIn('ol.feats > li{', m.PAGE_CSS)
        self.assertNotIn('ol.feats li {', m.PAGE_CSS)
        body = ('1. **第一条**\n'
                '   - 子项一\n'
                '2. **第二条**\n')
        rendered = m.render_changelog(body)
        self.assertEqual(rendered.count('<li><b>'), 2)

    def test_markdown_links_become_anchors_not_bare_urls(self):
        body = ('9. **兼容边界**\n'
                '   - 详见 [跨端兼容记录](https://github.com/Pilipala9919/MarcoMovie/blob/main/docs/COMPATIBILITY.md)。\n'
                '10. **安装包与源码**\n'
                '   - [镜像下载页](https://marcotv.wlj9919.top/movie/)\n')
        rendered = m.render_changelog(body)
        self.assertIn('<a href="https://github.com/Pilipala9919/MarcoMovie/blob/main/docs/COMPATIBILITY.md">跨端兼容记录</a>', rendered)
        self.assertIn('<a href="https://marcotv.wlj9919.top/movie/">镜像下载页</a>', rendered)
        self.assertNotIn('](', rendered)

    def test_unlisted_link_stays_plain_text(self):
        rendered = m.render_changelog('1. **第一条**\n   - 看 [这里](https://evil.example/a) 别点\n')
        self.assertNotIn('href="https://evil.example', rendered)
        self.assertIn('[这里](https://evil.example/a)', rendered)

if __name__ == '__main__': unittest.main()
