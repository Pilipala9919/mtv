#!/usr/bin/env python3
"""Sync the MarcoTV mirror site with the latest stable GitHub release.

Reads https://api.github.com/repos/Pilipala9919/MarcoTV/releases/latest
(which excludes drafts and prereleases), downloads the APK and the four
showcase screenshots, and updates index.html in place: version, release
date, APK filename, size and SHA256. Exits 0 with no changes when the
mirror already matches the latest stable release.
"""
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
SOURCE_REPO = "Pilipala9919/MarcoTV"
API = f"https://api.github.com/repos/{SOURCE_REPO}/releases/latest"
RAW = f"https://raw.githubusercontent.com/{SOURCE_REPO}/main/docs/showcase/assets"

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


def main():
    release = json.loads(fetch(API))
    tag = release["tag_name"]
    version = tag[1:] if tag.startswith("v") else tag
    published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")).date()
    assets = {a["name"]: a for a in release.get("assets", [])}
    apk_names = [n for n in assets if n.endswith(".apk")]
    if not apk_names:
        print("no APK asset in latest release", file=sys.stderr)
        return 1
    apk_name = sorted(apk_names)[0]
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
        html = html.replace(f"v{old_version}", f"v{version}")
        html = html.replace(old_version, version)
        changed = True
    html, n = re.subn(r"发布于 \d{4} 年 \d{1,2} 月 \d{1,2} 日",
                      f"发布于 {published.year} 年 {published.month} 月 {published.day} 日", html)
    changed = changed or n > 0
    html, n = re.subn(r"约 [\d.]+MB", f"约 {size_mb:.1f}MB", html, count=1)
    changed = changed or n > 0
    if re.search(r"[0-9a-f]{64}", html):
        html, n = re.subn(r"[0-9a-f]{64}", sha, html, count=1)
        changed = changed or n > 0
    today = date.today()
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
    html=re.sub(r"[0-9]+\.[0-9]+\.[0-9]+-[a-zA-Z0-9.]+(?=\.apk|/| 体验版|-source-and-apk\.zip)",preview_version,INDEX.read_text(encoding="utf-8"))
    INDEX.write_text(html,encoding="utf-8")
    print("changed" if changed else "already up to date")
    return 0


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
