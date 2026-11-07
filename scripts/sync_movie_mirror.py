"""Sync published Marco Movie preview releases into an isolated static mirror directory.

Copyright (C) 2026 Pilipala. SPDX-License-Identifier: GPL-3.0-only.
Only official release assets are accepted; all downloads are checked before writing the feed.
"""
import argparse
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import struct
import urllib.request
import zipfile

REPO = 'Pilipala9919/MarcoMovie'
BASE = 'https://marcotv.wlj9919.top/movie/'
LIMIT = 25 * 1024 * 1024
# Desktop and Apple packages may exceed the 25 MiB per-file limit of the Cloudflare Pages host.
# Those are listed on the mirror page but downloaded from the official GitHub release asset.
PLATFORM_LIMIT = 300 * 1024 * 1024

# Official QQ group (universal: covers Marco TV and Marco Movie, not one product).
QQ_GROUP_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=%2FqKQ4IqdIqi2mRxgPr8PBGGEhIo0M5yMI6%2BBNKH7CoOFDczcaEXekgiu8Kbt%2BORc&busi_data=eyJncm91cENvZGUiOiI4MTUwODUxMDIiLCJ0b2tlbiI6Im9CUW4wejI1NlB6UW9uK1EzdGNEMlZXdkgvMExVcGpVdXhOMFVrVXZmcWt0N3ZoaHRLMzNzd2lLVVp6UzZXc2QiLCJ1aW4iOiI5MjYwMDQzIn0%3D&data=VXYI4NkXW1KuR0A5qzeADzpuJOBl7PrdDs8NBNT4RMeKMjrMmev1_pjDDKH3CfTw7VwFoH-5Hkd71EDQ9_qj1w&svctype=4&tempid=h5_group_info'
QQ_GROUP_CODE = '815085102'
# (file name pattern, button label, short note). Mirrored only when the release carries the
# package together with its official .sha256 file.
PLATFORMS = (
    ('MarcoMovie-{version}-mobile.apk', 'Android 手机 / 平板版 (64位)', 'Android 6.0+ · 原生 64 位 (arm64-v8a) 与 32 位双架构 · 竖屏触控 UI'),
    ('MarcoMovie-{version}-ios-unsigned.ipa', 'iPhone / iPad 版 (IPA)', 'iOS / iPadOS 14.0+ · 支持巨魔 (TrollStore) 直接安装或自签安装'),
    ('MarcoMovie-{version}-windows-setup.exe', 'Windows 安装版（推荐）', 'Windows 10 / 11 · 64 位安装向导 · 内置运行库与快捷方式，支持后续一键更新'),
    ('MarcoMovie-{version}-windows-x64.zip', 'Windows 绿色版（ZIP）', 'Windows 10 / 11 · 64 位便携压缩包 · 解压后运行 marco_movie.exe'),
    ('MarcoMovie-{version}-macos.zip', 'macOS 版', 'macOS · 解压后拖入“应用程序”；未公证，首次打开请右键选择“打开”'),
    ('MarcoMovie-{version}-lite.apk', 'Android 4.0+ 轻量版', 'Android 4.0+ (API 14+) · 适配老旧电视/盒子/老手机 · 独立包名可共存'),
)

# Page layout (2026-11-07, approved from the local preview): dark background,
# silver-white accent, rounded cards, no emoji. The two images are the real
# MarcoMovie repo assets, copied into movie/ (app-icon-512.png, tv-banner-960x540.png).
# Device showcase frames removed 2026-11-07 at the user's request; official QQ group section added the same day.
# The "165 Stars" figure is a 2026-11-07 snapshot; the sync does not fetch it.
PAGE_CSS = """
  :root { --bg:#0b0d10; --card:#15181d; --card2:#1b1f26; --line:#262c35;
          --text:#e8eaed; --muted:#9aa3ad; --silver:#c9ced6; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; line-height:1.7; }
  a { color:var(--text); }
  .wrap { max-width:1080px; margin:0 auto; padding:0 20px 64px; }
  header.nav { display:flex; align-items:center; justify-content:space-between; gap:16px;
    padding:18px 0; border-bottom:1px solid var(--line); flex-wrap:wrap; }
  .brand { display:flex; align-items:center; gap:12px; font-size:20px; font-weight:700; }
  .brand img { width:40px; height:40px; border-radius:10px; }
  .ver-tag { font-size:12px; font-weight:600; color:#0b0d10; background:var(--silver);
    border-radius:20px; padding:2px 10px; }
  nav.links { display:flex; gap:20px; font-size:14px; color:var(--muted); flex-wrap:wrap; }
  nav.links a { color:var(--muted); text-decoration:none; }
  nav.links a:hover { color:var(--text); }
  .hero { display:grid; grid-template-columns:1.05fr 1fr; gap:28px; padding:44px 0 8px; align-items:center; }
  .hero h1 { font-size:40px; line-height:1.25; letter-spacing:.5px; }
  .hero p.lead { color:var(--muted); margin:14px 0 22px; font-size:16px; }
  .btn-row { display:flex; gap:12px; flex-wrap:wrap; }
  .btn { display:inline-block; padding:11px 22px; border-radius:10px; font-size:15px; font-weight:600;
    text-decoration:none; border:1px solid var(--silver); }
  .btn.primary { background:var(--text); color:#0b0d10; }
  .btn.ghost { background:transparent; color:var(--text); }
  .meta { margin-top:18px; color:var(--muted); font-size:13px; }
  .meta b { color:var(--silver); }
  .hero figure { background:#fff; border-radius:16px; padding:14px; }
  .hero figure img { width:100%; display:block; border-radius:8px; }
  .hero figure figcaption { color:#666; font-size:12px; text-align:center; padding-top:10px; }
  .notice { margin:30px 0 0; padding:14px 18px; background:var(--card); border:1px solid var(--line);
    border-left:3px solid var(--silver); border-radius:10px; color:var(--muted); font-size:14px; }
  section.block { padding:44px 0 0; }
  section.block h2 { font-size:24px; margin-bottom:6px; }
  section.block .sub { color:var(--muted); font-size:14px; margin-bottom:20px; }
  .cards { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; }
  .card h3 { font-size:16px; margin-bottom:8px; }
  .card p, .card li { color:var(--muted); font-size:14px; }
  .card ul { padding-left:18px; }
  ol.feats { list-style:none; counter-reset:f; display:grid; gap:12px; }
  ol.feats li { counter-increment:f; background:var(--card); border:1px solid var(--line);
    border-radius:12px; padding:16px 18px 16px 56px; position:relative; }
  ol.feats li::before { content:counter(f); position:absolute; left:16px; top:16px;
    width:26px; height:26px; border-radius:50%; background:var(--silver); color:#0b0d10;
    font-weight:700; font-size:14px; text-align:center; line-height:26px; }
  ol.feats li b { display:block; font-size:15px; margin-bottom:2px; }
  ol.feats li span { color:var(--muted); font-size:14px; }
  ol.feats li ul { margin-top:6px; padding-left:18px; color:var(--muted); font-size:14px; }
  ol.feats li ul li { background:none; border:none; border-radius:0; padding:0; position:static; }
  ol.feats li ul li::before { content:none; }
  pre { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; margin:0;
    background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; }
  code { overflow-wrap:anywhere; }
  .dl-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
  .dl { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; }
  .dl h3 { font-size:16px; }
  .dl p { color:var(--muted); font-size:13px; margin:6px 0 12px; min-height:40px; }
  .dl code { display:block; font-size:11px; color:var(--muted); word-break:break-all;
    background:#0e1116; border:1px solid var(--line); border-radius:8px; padding:8px; margin-top:10px; }
  .dl .btn { padding:8px 16px; font-size:14px; }
  .steps { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-top:16px; }
  .step { background:var(--card2); border:1px solid var(--line); border-radius:12px; padding:16px; }
  .step b { display:block; margin-bottom:4px; }
  .step span { color:var(--muted); font-size:13px; }
  footer { margin-top:48px; padding-top:20px; border-top:1px solid var(--line);
    color:var(--muted); font-size:13px; }
  @media (max-width:760px) {
    .hero, .cards, .dl-grid, .steps { grid-template-columns:1fr; }
    .hero h1 { font-size:30px; }
    nav.links { display:none; }
  }
"""


def fetch(url, limit=LIMIT):
    headers = {'User-Agent': 'MarcoMovie-Mirror', 'Accept-Encoding': 'identity'}
    if url.startswith('https://api.github.com/') and os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Download exceeds limit')
    return data


def apk_identity(apk):
    """Read literal package/version/minSdk from the actual binary APK manifest."""
    with zipfile.ZipFile(io.BytesIO(apk)) as z:
        entry = z.getinfo('AndroidManifest.xml')
        if entry.file_size > 1024 * 1024:
            raise ValueError('Manifest too large')
        data = z.read(entry)
    if struct.unpack_from('<H', data)[0] != 3:
        raise ValueError('Expected binary Android manifest')
    strings, values = [], {}
    offset = 8
    while offset < len(data):
        kind, header, size = struct.unpack_from('<HHI', data, offset)
        if size < header or header < 8 or offset + size > len(data):
            raise ValueError('Invalid XML chunk')
        if kind == 1:
            count, _, flags, start = struct.unpack_from('<IIII', data, offset + 8)
            if count > 65536 or header + count * 4 > size:
                raise ValueError('Invalid string pool')
            for i in range(count):
                pos = offset + start + struct.unpack_from('<I', data, offset + header + 4 * i)[0]
                if flags & 256:
                    def length8(p):
                        n = data[p]
                        return (((n & 127) << 8) | data[p + 1], p + 2) if n & 128 else (n, p + 1)
                    _, pos = length8(pos)
                    length, pos = length8(pos)
                    strings.append(data[pos:pos + length].decode('utf-8'))
                else:
                    length = struct.unpack_from('<H', data, pos)[0]; pos += 2
                    if length & 32768:
                        length = ((length & 32767) << 16) | struct.unpack_from('<H', data, pos)[0]; pos += 2
                    strings.append(data[pos:pos + length * 2].decode('utf-16le'))
        elif kind == 0x102:
            name = strings[struct.unpack_from('<I', data, offset + 20)[0]]
            start, stride, count = struct.unpack_from('<HHH', data, offset + 24)
            if stride < 20 or 16 + start + stride * count > size:
                raise ValueError('Invalid attributes')
            if name in ('manifest', 'uses-sdk'):
                for i in range(count):
                    pos = offset + 16 + start + i * stride
                    _, key, raw, _, _, value_type, value = struct.unpack_from('<IIIHBBI', data, pos)
                    values[(name, strings[key])] = strings[raw] if raw != 0xffffffff else strings[value] if value_type == 3 else value
        offset += size
    result = {'package': values[('manifest', 'package')], 'versionName': values[('manifest', 'versionName')],
              'versionCode': int(values[('manifest', 'versionCode')]), 'minSdk': int(values[('uses-sdk', 'minSdkVersion')])}
    if result['package'] != 'com.pilipala.marcomovie' or result['minSdk'] < 23 or result['versionCode'] <= 0:
        raise ValueError('Wrong application identity')
    return result


def choose(releases):
    valid = [r for r in releases if not r.get('draft') and r.get('published_at')
             and re.fullmatch(r'v\d+\.\d+\.\d+-preview', r.get('tag_name', ''))]
    if not valid:
        raise ValueError('No published preview release')
    return max(valid, key=lambda r: tuple(map(int, r['tag_name'][1:-8].split('.'))))


def _plain_md(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    return text.strip()


def render_changelog(notes):
    """Render a release body as a numbered list; fall back to escaped <pre> text.

    Release bodies are Markdown like "### Marco Movie 0.4.36 ..." followed by
    numbered items with a bold title and "- " sub-bullets. Anything that does
    not parse as numbered items is shown escaped, never as raw HTML.
    """
    items = []
    current = None
    for raw_line in (notes or '').splitlines():
        line = raw_line.strip().lstrip('\ufeff')
        if not line or line.startswith('#'):
            continue
        numbered = re.match(r'(\d+)\.\s+(.*)$', line)
        if numbered:
            current = {'title': _plain_md(numbered.group(2)).rstrip(':：'), 'points': []}
            items.append(current)
            continue
        if line.startswith('- ') and current is not None:
            current['points'].append(_plain_md(line[2:]))
            continue
        if current is not None and current['points']:
            current['points'][-1] += ' ' + _plain_md(line)
        elif current is not None:
            current['title'] += ' ' + _plain_md(line)
    if not items:
        return '<pre>' + html.escape(notes or '') + '</pre>'
    parts = ['<ol class="feats">']
    for item in items:
        parts.append('<li><b>' + html.escape(item['title']) + '</b>')
        if item['points']:
            parts.append('<ul>' + ''.join('<li>' + html.escape(point) + '</li>'
                                          for point in item['points']) + '</ul>')
        parts.append('</li>')
    parts.append('</ol>')
    return ''.join(parts)


def asset(release, name, output, limit=LIMIT):
    matches = [a for a in release['assets'] if a['name'] == name and a['state'] == 'uploaded']
    if len(matches) != 1:
        raise ValueError('Missing or duplicate asset: ' + name)
    info = matches[0]
    expected = f'https://github.com/{REPO}/releases/download/{release["tag_name"]}/{name}'
    if info['browser_download_url'] != expected or not 0 < info['size'] <= limit:
        raise ValueError('Unexpected asset URL or size')
    sha_url = expected + '.sha256'
    checksums = [a for a in release['assets'] if a['name'] == name + '.sha256' and a['state'] == 'uploaded' and a['browser_download_url'] == sha_url]
    if len(checksums) != 1:
        raise ValueError('Missing official checksum')
    checksum = fetch(sha_url, 4096).decode('ascii').strip().split()
    if len(checksum) != 2 or checksum[1].lstrip('*') != name or not re.fullmatch('[0-9a-f]{64}', checksum[0]):
        raise ValueError('Invalid checksum file')
    local = output / name
    body = local.read_bytes() if local.exists() else fetch(expected, limit)
    digest = hashlib.sha256(body).hexdigest()
    if len(body) != info['size'] or digest != checksum[0] or info.get('digest') not in (None, 'sha256:' + digest):
        raise ValueError('Release digest mismatch: ' + name)
    return body, digest


def platform_asset(release, name, output):
    """Return (href, size, sha256, body-or-None). Large packages stay on GitHub, never on Pages."""
    info = [a for a in release['assets'] if a['name'] == name and a['state'] == 'uploaded']
    if len(info) != 1:
        raise ValueError('Missing or duplicate asset: ' + name)
    size = info[0]['size']
    if size <= LIMIT:
        body, digest = asset(release, name, output)
        return name, size, digest, body
    expected = f'https://github.com/{REPO}/releases/download/{release["tag_name"]}/{name}'
    if info[0]['browser_download_url'] != expected or size > PLATFORM_LIMIT:
        raise ValueError('Unexpected asset URL or size')
    sha_url = expected + '.sha256'
    if len([a for a in release['assets'] if a['name'] == name + '.sha256' and a['state'] == 'uploaded'
            and a['browser_download_url'] == sha_url]) != 1:
        raise ValueError('Missing official checksum')
    checksum = fetch(sha_url, 4096).decode('ascii').strip().split()
    if len(checksum) != 2 or checksum[1].lstrip('*') != name or not re.fullmatch('[0-9a-f]{64}', checksum[0]):
        raise ValueError('Invalid checksum file')
    if info[0].get('digest') not in (None, 'sha256:' + checksum[0]):
        raise ValueError('Release digest mismatch: ' + name)
    return expected, size, checksum[0], None


def sync(output):
    release = choose(json.loads(fetch(f'https://api.github.com/repos/{REPO}/releases?per_page=100', 4 * 1024 * 1024)))
    version = release['tag_name'][1:-8]
    release_tag = release['tag_name']
    published_date = (release.get('published_at') or '')[:10]
    apk_name, source_name = f'MarcoMovie-{version}-preview.apk', f'MarcoMovie-{version}-source.zip'
    apk, sha = asset(release, apk_name, output, limit=PLATFORM_LIMIT)
    apk_href = apk_name if len(apk) <= LIMIT else f'https://github.com/{REPO}/releases/download/{release_tag}/{apk_name}'
    source, source_sha = asset(release, source_name, output)
    platforms = []
    for pattern, label, note in PLATFORMS:
        name = pattern.format(version=version)
        if any(a['name'] == name for a in release['assets']):
            href, size, digest, body = platform_asset(release, name, output)
            platforms.append((name, label, note, href, size, digest, body))
    identity = apk_identity(apk)
    if identity['versionName'] != version:
        raise ValueError('APK version does not match release')
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        if archive.testzip() is not None:
            raise ValueError('Source ZIP failed CRC')
        license_text = archive.read(f'MarcoMovie-{version}/LICENSE')
        notice = archive.read(f'MarcoMovie-{version}/NOTICE')
    feed = dict(schema=1, versionCode=identity['versionCode'], versionName=version, minSdk=identity['minSdk'],
                size=len(apk), sha256=sha, url=apk_href if apk_href.startswith('https://') else BASE + apk_name,
                prerelease=bool(release.get('prerelease',True)), notes=(release.get('body') or '')[:8000])
    for name, _, _, href, size, digest, _ in platforms:
        for suffix, key in (('-mobile.apk','mobile'),('-windows-setup.exe','windows')):
            if name == f'MarcoMovie-{version}{suffix}':
                feed[key] = dict(size=size, sha256=digest, url=href if href.startswith('https://') else BASE + name)
    feed_path = output / 'updates/preview.json'
    feed_paths = [feed_path] + ([] if feed['prerelease'] else [output/'updates/stable.json'])
    for channel in feed_paths:
        if channel.exists():
            previous = json.loads(channel.read_text(encoding='utf-8'))
            if previous['versionCode'] > feed['versionCode']:
                raise ValueError('Refusing to roll the mirror back')
            if previous['versionCode'] == feed['versionCode'] and previous['sha256'] != sha:
                raise ValueError('Refusing to replace a published version')
    escaped = html.escape
    mobile_href = next((p[3] for p in platforms if p[0] == f'MarcoMovie-{version}-mobile.apk'), None)
    mobile_button = (f'<a class="btn ghost" href="{escaped(mobile_href)}">下载手机版</a>' if mobile_href else '')
    download_cards = []
    download_cards.append(
        f'<div class="dl"><h3>Android 电视版</h3><p>Android 6.0+ 电视 / 盒子 / 投影仪大屏专享版 · ARM 32 位（内置 FFmpeg / AV1 / VP9 扩展）· {len(apk)/1024/1024:.1f} MB</p>'
        f'<a class="btn primary" href="{escaped(apk_href)}">下载</a>'
        f'<p><a href="{escaped(apk_href)}.sha256">校验文件</a></p><code>SHA-256：{sha}</code></div>')
    for name, label, note, href, size, digest, body in platforms:
        download_cards.append(
            f'<div class="dl"><h3>{escaped(label)}</h3><p>{escaped(note)} · {size/1024/1024:.1f} MB</p>'
            f'<a class="btn primary" href="{escaped(href)}">下载</a>'
            f'<p><a href="{escaped(href)}.sha256">校验文件</a></p><code>SHA-256：{digest}</code></div>')
    download_cards.append(
        f'<div class="dl"><h3>同版本源码</h3><p>与发布包同一版本 · {len(source)/1024/1024:.1f} MB</p>'
        f'<a class="btn primary" href="{escaped(source_name)}">下载</a>'
        f'<p><a href="{escaped(source_name)}.sha256">校验文件</a></p><code>SHA-256：{source_sha}</code></div>')
    if platforms:
        other_platforms = ('<p class="sub"><b>其他平台</b> · 与 Android 版同一版本，由 GitHub Actions 云端构建；'
                           '尚未在每台设备上实机验证。</p>')
        fallback_link = ''
    else:
        other_platforms = ''
        fallback_link = (f'<p><a class="btn ghost" href="https://github.com/{REPO}/releases/tag/{release_tag}">'
                         'Windows / macOS / iOS 多平台下载</a></p>')
    changelog = render_changelog(feed['notes'])
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Marco Movie · 多端自适应播放器 · Pilipala</title><style>{PAGE_CSS}</style>
<body><div class="wrap">
<header class="nav"><div class="brand"><img src="app-icon-512.png" alt="Marco Movie 应用图标">Marco Movie <span class="ver-tag">{version}</span></div>
<nav class="links"><a href="#download">下载</a><a href="#features">功能</a><a href="#changelog">本次更新</a><a href="#group">交流群</a><a href="https://github.com/{REPO}" target="_blank" rel="noopener">GitHub</a></nav></header>
<div class="hero"><div>
<h1>Marco Movie<br>多端自适应播放器</h1>
<p class="lead">支持 Android 电视大屏遥控、手机与平板 64 位专属触控，以及 Windows / macOS / iOS（iOS 14.0+ 巨魔与自签）多端独立适配的开源播放器。</p>
<div class="btn-row"><a class="btn primary" href="{escaped(apk_href)}">下载电视版</a>{mobile_button}<a class="btn ghost" href="#download">全部平台</a></div>
<p class="meta"><b>165 Stars</b> · GPL-3.0-only · {published_date} 更新 · 作者 Pilipala</p>
</div><figure><img src="tv-banner-960x540.png" alt="Marco Movie 横幅：银色场记板加播放标志"><figcaption>银色场记板横幅 · 仓库原图</figcaption></figure></div>
<p class="notice">本产品仅为工具，不内置、不提供、不托管任何影视资源或配置地址。内容与配置请自行合法获取，数据保存在本机。</p>
<section class="block" id="features"><h2>文字介绍与功能</h2>
<p class="sub">同一版本，按遥控器、触屏和桌面操作分别适配。</p>
<div class="cards">
<div class="card"><h3>Android 电视端</h3><p>专为遥控器与 10 英尺大屏打造：5–8 列 2:3 海报墙、右侧悬浮图标 Dock、内置遥控全拼 / 首拼搜索、左固定海报 + 右独立滚动选集、小屏返回续播、局域网扫码导入配置。</p></div>
<div class="card"><h3>Android 手机 / 平板端</h3><p>完全独立的移动端触控 UI：支持滑动切换的玻璃 Dock、横竖屏自适应导航，保留系统状态栏、去除遥控白框；首页直接支持剪贴板一键粘贴与原生输入法导入（无需扫码）；支持 50 集分组触控选集与全屏横屏手势播放（双击暂停、左右滑快进、左半屏亮度、右半屏音量、长按 2 倍速）。</p></div>
<div class="card"><h3>Windows 与 Apple 端</h3><p>提供跨平台客户端工程（覆盖 Windows x64、macOS、iPhone 与 iPad），自适应桌面侧边导航与移动端底部导航，内置硬件加速播放内核，支持已适配来源、Emby 与本机 CatPaw，提供公开订阅备份；功能边界以本次更新说明为准。</p></div>
</div></section>
<section class="block" id="changelog"><h2>版本特性 · {version}</h2>
<p class="sub">{published_date} 发布 · 更新内容来自 GitHub Release 原文，改写为列表。</p>
{changelog}</section>
<section class="block" id="download"><h2>下载与安装</h2>
<p class="sub">校验值以 GitHub Release 为准；超过 Pages 单文件 25 MB 上限的大包只挂 GitHub 下载链接。</p>
{other_platforms}<div class="dl-grid">{''.join(download_cards)}</div>{fallback_link}
<div class="steps">
<div class="step"><b>第一步 · 下载核对</b><span>按设备选对应安装包，下载后核对 SHA-256 再安装。</span></div>
<div class="step"><b>第二步 · 安装</b><span>电视 / 手机直接安装；Windows 运行安装向导或解压绿色版；macOS 拖入应用程序。</span></div>
<div class="step"><b>第三步 · 导入配置</b><span>按应用内提示导入自己的配置，自行合法获取内容与配置。</span></div>
</div></section>
<section class="block" id="group"><h2>官方交流群</h2>
<p class="sub">通用群，不分软件，Marco TV 和 Marco Movie 都可以在这里交流。</p>
<div class="card"><h3>官方交流群 1️⃣：Marco！</h3><p>群号 815085102 · 点开下面的按钮会跳到 QQ 加群。</p>
<a class="btn primary" href="{escaped(QQ_GROUP_URL)}">加入 QQ 群</a></div></section>
<footer>作者：Pilipala · <a href="LICENSE">GPL-3.0-only</a> · <a href="NOTICE">署名与许可</a> · <a href="https://github.com/{REPO}/blob/main/docs/USER_GUIDE.md">使用指南</a> · <a href="/">Marco TV</a></footer>
</div></body></html>'''
    files = {apk_name + '.sha256': (sha + '  ' + apk_name + '\n').encode(),
             source_name: source, source_name + '.sha256': (source_sha + '  ' + source_name + '\n').encode(),
             'LICENSE': license_text, 'NOTICE': notice, 'index.html': page.encode()}
    if len(apk) <= LIMIT:
        files[apk_name] = apk
    for name, _, _, _, _, digest, body in platforms:
        if body is None:
            continue
        files[name] = body
        files[name + '.sha256'] = (digest + '  ' + name + '\n').encode()
    # Versions are immutable and written before the channel pointer; Git/Pages publishes one complete snapshot.
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = output / name
        if target.exists() and target.suffix in ('.apk', '.zip', '.ipa') and target.read_bytes() != data:
            raise ValueError('Immutable asset already differs')
        target.write_bytes(data)
    for channel in feed_paths:
        channel.parent.mkdir(exist_ok=True)
        temporary = channel.with_suffix('.tmp')
        temporary.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        temporary.replace(channel)
    print(f'Synced {version}: {len(apk)} bytes, SHA-256 {sha}; deployment must be verified separately.')
    return feed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sync(args.output)
