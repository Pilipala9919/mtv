#!/usr/bin/env python3
"""Sync the MarcoTV mirror site with the latest stable GitHub release.

Reads https://api.github.com/repos/Pilipala9919/MarcoTV/releases/latest
(which excludes drafts and prereleases), downloads the APK and the four
showcase screenshots, and updates tv/index.html in place: version, release
date, APK filename, size and SHA256. It also keeps the hub's TV version
line (index.html) in step via its own sync anchor, so the hub never goes
stale after a release. Exits 0 with no changes when the mirror already
matches the latest stable release.

Only the TV version line on the hub is owned here; the hub's Movie line
is owned by sync_platform_packages.py, and the rest of the hub is static.
"""
import hashlib
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "tv" / "index.html"
HUB = ROOT / "index.html"
SOURCE_REPO = "Pilipala9919/MarcoTV"
API = f"https://api.github.com/repos/{SOURCE_REPO}/releases/latest"
RAW = f"https://raw.githubusercontent.com/{SOURCE_REPO}/main/docs/showcase/assets"
# Permanent Quark share for the MarcoTV folder. 2026-11-17 policy: every
# version's manual download button is Quark-only; the mirror APK stays
# hosted in the repo for the in-app update feeds, and the GitHub release
# asset remains only as the checksum source.
QUARK_TV_URL = "https://pan.quark.cn/s/df36e65bca44"

SCREENSHOTS = {
    "01-desktop.webp": "desktop.webp",
    "03-library.webp": "library.webp",
    "11-clock.webp": "clock.webp",
    "12-screensaver.webp": "screensaver.webp",
}


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "mtv-sync"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    return data if binary else data.decode("utf-8")


def _replace_anchor(html, name, value):
    """Replace every <!--sync:<name>-->...<!--/sync:<name>--> spot in a page.

    The TV page marks each syncable value (version, release-date, size,
    sha256) with an HTML comment anchor; a value may appear in more than
    one place (hero + download section) and all marked spots update
    together. The hub marks its TV version line the same way
    (hub-tv-version). A missing anchor fails loudly: a silently stale
    version or checksum is worse than a failed sync.
    """
    pattern = re.compile(r"(<!--sync:" + re.escape(name) + r"-->)[^<]*(<!--/sync:" + re.escape(name) + r"-->)")
    html, n = pattern.subn(lambda m: m.group(1) + value + m.group(2), html)
    if n == 0:
        raise ValueError(f"sync anchor missing: sync:{name}")
    return html


def choose_apk(assets, version):
    """Pick the official stable APK: exactly MarcoTV-<version>.apk.

    A release may also carry experimental variants (e.g.
    MarcoTV-0.15.0-Restricted.apk); those must never be treated as the
    stable download, and picking by alphabetical order would do exactly
    that ('-' sorts before '.'). A missing official APK fails loudly.
    """
    name = f"MarcoTV-{version}.apk"
    if name not in assets:
        raise ValueError("Official APK missing from latest release: " + name)
    return name


def main():
    release = json.loads(fetch(API))
    tag = release["tag_name"]
    version = tag[1:] if tag.startswith("v") else tag
    published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=8))).date()
    assets = {a["name"]: a for a in release.get("assets", [])}
    try:
        apk_name = choose_apk(assets, version)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    apk_url = assets[apk_name]["browser_download_url"]
    print(f"latest stable release: {tag} ({published}), apk: {apk_name}")

    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r"MarcoTV-[0-9]+\.[0-9]+\.[0-9]+\.apk", html)
    old_version = None
    if m:
        old_version = re.search(r"([0-9]+\.[0-9]+\.[0-9]+)", m.group(0)).group(1)
    old_apk = m.group(0) if m else None

    apk_data = fetch(apk_url, binary=True)
    sha = hashlib.sha256(apk_data).hexdigest()
    size_mb = len(apk_data) / 1024 / 1024

    # Download screenshots (best effort: keep old ones if a download fails).
    for src, dst in SCREENSHOTS.items():
        try:
            (ROOT / dst).write_bytes(fetch(f"{RAW}/{src}", binary=True))
            print(f"updated screenshot {dst}")
        except Exception as exc:  # noqa: BLE001 - keep old screenshot on failure
            print(f"warning: screenshot {src} failed, keeping old one: {exc}")

    changed = False
    if old_apk and old_apk != apk_name:
        # Keep versioned APKs: older clients and preview feeds may still need them.
        changed = True
    (ROOT / apk_name).write_bytes(apk_data)
    if old_version and old_version != version:
        # Only update release links and labels; screenshot provenance and old-version
        # upgrade instructions must retain their historical version.
        html = html.replace(f"MarcoTV-{old_version}", f"MarcoTV-{version}")
        html = html.replace(f"/v{old_version}/", f"/v{version}/")
        html = html.replace(f"版本信息以 {old_version} 稳定版为准", f"版本信息以 {version} 稳定版为准")
        changed = True
    # Main download button: Quark-only (2026-11-17 policy). The button is
    # a permanent share link, so this sync never rewrites it; the mirror
    # APK stays hosted in the repo for the in-app update feeds, but no
    # visible button on the page links to it or to GitHub.
    # Sync anchors in tv/index.html (idempotent: same values rewrite to the
    # same text, so these run on every sync, not only on version change).
    before_anchors = html
    html = _replace_anchor(html, "version", version)
    html = _replace_anchor(html, "release-date",
                           f"{published.year} 年 {published.month} 月 {published.day} 日")
    html = _replace_anchor(html, "size", f"{size_mb:.1f} MB")
    html = _replace_anchor(html, "sha256", sha)
    changed = changed or html != before_anchors
    today = datetime.now(timezone(timedelta(hours=8))).date()
    html, n = re.subn(r"镜像建于 \d{4} 年 \d{1,2} 月 \d{1,2} 日",
                      f"镜像上次同步于 {today.year} 年 {today.month} 月 {today.day} 日", html)
    html, n2 = re.subn(r"镜像上次同步于 \d{4} 年 \d{1,2} 月 \d{1,2} 日",
                       f"镜像上次同步于 {today.year} 年 {today.month} 月 {today.day} 日", html)
    changed = changed or n > 0 or n2 > 0
    # Zip link: point it at the new release's zip asset when present.
    zip_names = [n for n in assets if n.endswith(".zip")]
    if zip_names:
        html = re.sub(r"MarcoTV-[0-9]+\.[0-9]+\.[0-9]+-source-and-apk\.zip",
                      sorted(zip_names)[0], html)

    INDEX.write_text(html, encoding="utf-8")
    print(f"apk sha256: {sha}")
    print(f"apk size: {len(apk_data)} bytes ({size_mb:.1f} MB)")
    preview_version=sync_update_channels()
    html=render_channels(INDEX.read_text(encoding="utf-8"), preview_version)
    INDEX.write_text(html,encoding="utf-8")
    # Hub TV version line: same release, same date, via its own anchor.
    # Idempotent like the TV anchors above, so it runs on every sync.
    hub = HUB.read_text(encoding="utf-8")
    hub_new = _replace_anchor(hub, "hub-tv-version",
                              f"当前稳定版 {version}，{published.year} 年 {published.month} 月 {published.day} 日发布")
    if hub_new != hub:
        HUB.write_text(hub_new, encoding="utf-8")
        changed = True
    print("changed" if changed else "already up to date")
    return 0


def render_channels(html, version):
    """Render either a preview release or its stable successor without stale RC labels.

    Rewrites only the inside of the TV page's update section (from its
    <h2> to its own closing </section>); the surrounding section tags and
    the sections before/after it are untouched. Update-feed links are
    root-absolute: the page lives at /tv/, so a relative updates/ link
    would resolve to /tv/updates/ and break.
    """
    preview = "-" in version
    label = "体验版" if preview else "正式版"
    status = "体验版仍在验证中，日常使用默认推荐上方稳定版。" if preview else "体验渠道与稳定渠道当前提供同一正式版，原 RC 用户可直接覆盖升级。"
    section = f'''<h2>电视在线更新</h2>
    <p class="intro">当前提供 <a href="{QUARK_TV_URL}">{version} {label}</a>。{status} 更多机型等待实测反馈，<a href="https://github.com/Pilipala9919/MarcoTV/issues">欢迎加入测试，分享你的使用情况</a>。</p>
    <p class="intro">安装后到“维护与帮助 → 软件更新”检查更新，日常使用选择稳定版渠道。镜像优先，失败后尝试 GitHub；可选自动下载，安装仍需确认。0.11.1 没有在线更新，需先手动覆盖安装。每次 APK 更新后，最近任务辅助服务仍需电脑重新启动。</p>
    <div class="links">
      <a href="https://github.com/Pilipala9919/MarcoTV/releases/download/v{version}/MarcoTV-{version}.apk.sha256">校验值</a>
      <a href="/updates/stable.json">稳定版索引</a>
      <a href="/updates/preview.json">体验版索引</a>
    </div>
  </section>'''
    result, count = re.subn(r"<h2>(?:体验版与)?电视在线更新</h2>.*?</section>", lambda _: section, html, flags=re.S)
    if count != 1: raise ValueError("Update section missing or duplicated")
    return result


def sync_update_channels():
    """Pilipala: mirror only published upstream feeds after release digest validation."""
    staged = {}
    for channel in ("stable", "preview"):
        feed = json.loads(fetch(f"https://raw.githubusercontent.com/{SOURCE_REPO}/main/docs/updates/{channel}.json"))
        version = feed["versionName"]
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.]+)?", version) or len(version)>48:
            raise ValueError("Invalid version")
        if feed["schema"]!=1 or type(feed["versionCode"]) is not int or feed["versionCode"]<=0:
            raise ValueError("Invalid schema/code")
        if not 23<=feed["minSdk"]<=100 or not 0<feed["size"]<=128*1024*1024 or not re.fullmatch(r"[a-f0-9]{64}", feed["sha256"]):
            raise ValueError("Invalid feed bounds")
        if ("-" in version)!=feed["prerelease"] or (channel=="stable" and feed["prerelease"]):
            raise ValueError("Wrong release channel")
        name=f"MarcoTV-{version}.apk"
        official=f"https://github.com/{SOURCE_REPO}/releases/download/v{version}/{name}"
        if feed["url"]!=official:raise ValueError("Unexpected upstream APK URL")
        release=json.loads(fetch(f"https://api.github.com/repos/{SOURCE_REPO}/releases/tags/v{version}"))
        if release["draft"] or release["prerelease"]!=feed["prerelease"]:raise ValueError("Release not ready")
        assets={a["name"]:a for a in release["assets"]}
        asset=assets[name]
        if asset["browser_download_url"]!=official or asset["size"]!=feed["size"]:raise ValueError("Release mismatch")
        local=ROOT/name
        data=local.read_bytes() if local.exists() else b""
        if len(data)!=feed["size"] or hashlib.sha256(data).hexdigest()!=feed["sha256"]:data=fetch(official,binary=True)
        if len(data)!=feed["size"] or hashlib.sha256(data).hexdigest()!=feed["sha256"]:raise ValueError("APK digest mismatch")
        if asset.get("digest") and asset["digest"]!="sha256:"+feed["sha256"]:raise ValueError("GitHub digest mismatch")
        checksum=fetch(assets[name+".sha256"]["browser_download_url"]).split()[0]
        if checksum!=feed["sha256"]:raise ValueError("Published checksum mismatch")
        staged[name]=data
        staged[name+".sha256"]=(feed["sha256"]+"  "+name+"\n").encode()
        feed["url"]=f"https://marcotv.wlj9919.top/{name}"
        staged[f"updates/{channel}.json"]=(json.dumps(feed,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    # All checks finish before replacing public channel files. Pages deploys one Git commit.
    for name,data in staged.items():
        target=ROOT/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    print("Both update channels verified and synchronized")
    return feed["versionName"]


if __name__ == "__main__":
    raise SystemExit(main())
