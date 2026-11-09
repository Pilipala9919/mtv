"""Sync MarcoMovie / MarcoTV packages to Quark Drive.

One folder per platform, one permanent share link per folder. The share
link never changes: a new release only uploads the new file into the
folder and deletes the previous file this script uploaded.

Current package per platform comes from the per-platform feeds the
mirror already publishes (movie/updates/<platform>.json), from the
MarcoTV stable feed (updates/stable.json), or from the official GitHub
releases API for the two packages with no feed (Movie lite, Marco TV
Lite). The mirror hosts no packages, so every source is a GitHub
download URL, verified by size and SHA-256 before upload.

After a TV sync the homepage's Quark buttons are patched from the
manifest (anchors marked data-quark="tv" / "tv-lite") so the links
never go stale.

Requires the `quark` CLI and a logged-in profile (jar file). Upload,
share, list and remove run straight from Node against Quark's web API
using the saved cookies; no Chrome is needed for these commands.

Usage (run from the repo root, inside the GitHub Actions job):
    python scripts/sync_quark.py --movie
    python scripts/sync_quark.py --tv
    python scripts/sync_quark.py --movie --dry-run   # print the plan only
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "quark.json"

# platform key -> Quark folder
MOVIE_FOLDERS = {
    "android-tv": "/MarcoMovie/电视版",
    "android-mobile": "/MarcoMovie/手机版",
    "ios": "/MarcoMovie/iOS",
    "windows-setup": "/MarcoMovie/Windows安装版",
    "windows-zip": "/MarcoMovie/Windows绿色版",
    "macos": "/MarcoMovie/macOS",
    "android-lite": "/MarcoMovie/轻量版",
}
TV_FOLDERS = {
    "tv": "/MarcoTV/电视版",
    "tv-lite": "/MarcoTV/Lite版",
}

UA = {"User-Agent": "mtv-quark-sync"}


class QuarkError(Exception):
    pass


# ---------------------------------------------------------------- CLI

def run_quark(args):
    """Run `quark <args...> --json`, return the parsed JSON.

    `--json` must come after the command name. stdout carries the
    result, stderr carries progress and error details.
    """
    cmd = ["quark", *args, "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise QuarkError(
            f"quark {' '.join(args)} failed (exit {proc.returncode}): "
            + " | ".join(detail[-3:]))
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise QuarkError(
            f"quark {' '.join(args)} returned non-JSON output: "
            f"{proc.stdout[:200]}") from exc


def ensure_folder(folder):
    run_quark(["mkdir", folder])


def list_folder(folder):
    """Return [(name, type)] for the folder's entries (ls returns a bare array)."""
    out = run_quark(["ls", folder])
    if not isinstance(out, list):
        raise QuarkError(f"quark ls {folder} returned unexpected shape: {out!r:.200}")
    return [(i.get("name"), i.get("type")) for i in out
            if isinstance(i, dict) and i.get("name")]


def upload_file(local_path, folder):
    out = run_quark(["upload", str(local_path), folder])
    uploaded = out.get("uploaded") or []
    if not uploaded:
        raise QuarkError(f"quark upload {local_path} -> {folder} reported nothing uploaded: {out!r:.200}")
    return uploaded[0]


def share_folder(folder):
    out = run_quark(["share", folder, "--days", "0"])
    url = out.get("link")
    if not url:
        raise QuarkError(f"quark share {folder} returned no link: {out!r:.200}")
    return url


def remove_files(folder, names):
    if not names:
        return
    # --yes is pre-approved by the user for one policy only: delete files
    # this script uploaded, inside the managed folders, after the new
    # version is confirmed in place. Deletions go to Quark's recycle
    # bin and are recoverable for 30 days.
    run_quark(["rm", *[f"{folder}/{n}" for n in names], "--yes"])


# ---------------------------------------------------------------- sources

def download(url, dest, size=None, sha256=None):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    if size is not None and dest.stat().st_size != size:
        raise QuarkError(f"size mismatch for {dest.name}: got {dest.stat().st_size}, want {size}")
    if sha256 is not None and digest != sha256:
        raise QuarkError(f"sha256 mismatch for {dest.name}")
    return digest


def feed_asset(feed_path, package_suffix):
    """Read one platform feed; return (filename, url, size, sha256, version).

    Feeds carry their assets in a `packages` dict (name -> {url, size,
    sha256}); android-tv/mobile additionally repeat the same file at the
    top level, but the dict is the uniform source.
    """
    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    version = feed.get("versionName")
    packages = feed.get("packages") or {}
    candidates = [n for n in packages if n.endswith(package_suffix)]
    if not candidates:
        raise QuarkError(f"{feed_path}: no package ending {package_suffix}")
    # Prefer the -x64- / portable variant when several names match.
    candidates.sort(key=lambda n: ("x64" not in n, "portable" not in n, n))
    name = candidates[0]
    info = packages[name]
    if not info.get("url"):
        raise QuarkError(f"{feed_path}: package {name} has no url")
    return name, info["url"], info.get("size"), info.get("sha256"), version


def github_api(url):
    """GET a GitHub API URL; a GITHUB_TOKEN in the environment raises the rate limit."""
    headers = dict(UA)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def github_release_asset(repo, tag_pattern, suffix):
    """Latest release whose tag matches, asset ending with suffix.

    Returns (filename, url, size, sha256, version). The official .sha256
    file is checked against the API digest.
    """
    releases = github_api(f"https://api.github.com/repos/{repo}/releases?per_page=30")
    for release in releases:
        tag = release.get("tag_name", "")
        if release.get("draft") or not re.fullmatch(tag_pattern, tag):
            continue
        assets = {a["name"]: a for a in release.get("assets", [])
                  if a.get("state") == "uploaded"}
        matches = [n for n in assets if n.endswith(suffix) and not n.endswith(".sha256")]
        if len(matches) != 1:
            continue
        name = matches[0]
        info = assets[name]
        sha_url = info["browser_download_url"] + ".sha256"
        if name + ".sha256" not in assets:
            raise QuarkError(f"{repo} {tag}: no checksum for {name}")
        checksum = fetch_text(sha_url).strip().split()
        if len(checksum) != 2 or checksum[1].lstrip("*") != name or not re.fullmatch("[0-9a-f]{64}", checksum[0]):
            raise QuarkError(f"{repo} {tag}: invalid checksum file for {name}")
        if info.get("digest") not in (None, "sha256:" + checksum[0]):
            raise QuarkError(f"{repo} {tag}: digest mismatch for {name}")
        version = re.search(r"(\d+\.\d+\.\d+)", tag).group(1)
        return name, info["browser_download_url"], info["size"], checksum[0], version
    raise QuarkError(f"{repo}: no release matching {tag_pattern} with a {suffix} asset")


def movie_sources():
    updates = ROOT / "movie" / "updates"
    src = {}

    def feed(name, suffix):
        stable = updates / f"{name}.json"
        preview = updates / f"{name}-preview.json"
        path = stable if stable.exists() else preview
        if not path.exists():
            raise QuarkError(f"no feed for {name}: {stable} / {preview}")
        return feed_asset(path, suffix)

    src["android-tv"] = feed("android-tv", ".apk")
    src["android-mobile"] = feed("android-mobile", ".apk")
    src["ios"] = feed("ios", ".ipa")
    src["windows-setup"] = feed("windows", "-setup.exe")
    src["windows-zip"] = feed("windows", ".zip")
    src["macos"] = feed("macos", ".zip")
    src["android-lite"] = github_release_asset(
        "Pilipala9919/MarcoMovie", r"v\d+\.\d+\.\d+-preview", "-lite.apk")
    return src


def tv_sources():
    """Marco TV from the stable feed (GitHub URL); Lite from the GitHub releases API."""
    feed = json.loads((ROOT / "updates" / "stable.json").read_text(encoding="utf-8"))
    version = feed.get("versionName")
    url = feed.get("url") or ""
    if not url.startswith("https://github.com/Pilipala9919/MarcoTV/releases/download/"):
        # Old feed still pointing at the mirror: rebuild the GitHub URL.
        url = (f"https://github.com/Pilipala9919/MarcoTV/releases/download/"
               f"v{version}/MarcoTV-{version}.apk")
    tv = ("MarcoTV-" + version + ".apk", url, feed.get("size"),
          feed.get("sha256"), version)
    lite = github_release_asset(
        "Pilipala9919/MarcoTV", r"lite-v\d+\.\d+\.\d+", ".apk")
    return {"tv": tv, "tv-lite": lite}


# ---------------------------------------------------------------- sync

def sync_platform(key, folder, source, manifest, tmpdir, dry_run):
    name, url, size, sha256, version = source
    size_mb = f"{size / 1024 / 1024:.1f} MB" if size else "?"
    print(f"[{key}] {name} ({version or '?'}, {size_mb}) -> {folder}")
    entry = manifest.get(key, {})
    if dry_run:
        print(f"  dry run: would upload to {folder}, keep share link "
              f"{entry.get('share_url') or '(new)'}")
        return entry or {"folder": folder, "share_url": None, "file": name,
                         "version": version, "sha256": sha256}
    ensure_folder(folder)
    names = [n for n, _ in list_folder(folder)]
    if (entry.get("file") == name and entry.get("sha256") == sha256
            and name in names):
        print("  already in place, skipping upload")
    else:
        local = Path(tmpdir) / name
        print(f"  downloading {url}")
        download(url, local, size, sha256)
        if name in names:
            print(f"  removing stale same-name file {name}")
            remove_files(folder, [name])
            names.remove(name)
        print(f"  uploading {name}")
        upload_file(local, folder)
        names = [n for n, _ in list_folder(folder)]
        if name not in names:
            raise QuarkError(f"{name} not found in {folder} after upload")
    stale = [n for n in names if n != name]
    if stale:
        print(f"  removing previous version(s): {', '.join(stale)}")
        remove_files(folder, stale)
    share_url = entry.get("share_url")
    if not share_url:
        share_url = share_folder(folder)
        print(f"  new permanent share link: {share_url}")
    return {"folder": folder, "share_url": share_url, "file": name,
            "version": version, "sha256": sha256}


def apply_homepage(manifest):
    """Patch the homepage's Quark buttons from the manifest (TV only).

    Anchors marked data-quark="tv" / "tv-lite" get their href updated;
    a missing anchor is inserted right after the matching GitHub download
    button. Returns True when the file changed.
    """
    index = ROOT / "index.html"
    html = index.read_text(encoding="utf-8")
    changed = False
    for key, file_part in (("tv", "MarcoTV-"), ("tv-lite", "MarcoTV-Lite-")):
        entry = manifest.get(key) or {}
        url = entry.get("share_url")
        if not url:
            print(f"  homepage: no share link for {key}, skipping")
            continue
        anchor = (f'<a class="btn2" data-quark="{key}" href="{url}" '
                  f'target="_blank" rel="noopener">夸克网盘下载</a>')
        pattern = re.compile(
            r'(<a[^>]*data-quark="' + re.escape(key) + r'"[^>]*href=")([^"]*)(")')
        m = pattern.search(html)
        if m:
            if m.group(2) == url:
                continue
            html, n = pattern.subn(r'\g<1>' + url + r'\g<3>', html, count=1)
            changed = changed or n > 0
            continue
        # Insert after the GitHub download button for this package.
        file_re = re.escape(file_part + (entry.get("version") or "") + ".apk")
        m = re.search(r'(<a[^>]*href="[^"]*' + file_re + r'"[^>]*>.*?</a>)',
                      html, re.S)
        if not m:
            print(f"  homepage: no GitHub button found for {key}, skipping")
            continue
        # A legacy Quark button without the data-quark marker may already
        # sit right after the GitHub button: update it instead of adding
        # a second one.
        tail = html[m.end():m.end() + 400]
        legacy = re.search(r'(<a[^>]*href=")https://pan\.quark\.cn/s/[^"]*("[^>]*>)',
                           tail)
        if legacy:
            start = m.end() + legacy.start()
            end = m.end() + legacy.end()
            old_tag = html[start:end]
            new_tag = re.sub(r'href="[^"]*"', f'href="{url}"', old_tag, count=1)
            if 'data-quark' not in new_tag:
                new_tag = new_tag.replace('<a ', f'<a data-quark="{key}" ', 1)
            html = html[:start] + new_tag + html[end:]
            changed = True
            continue
        html = html[:m.end()] + "\n" + anchor + html[m.end():]
        changed = True
    if changed:
        index.write_text(html, encoding="utf-8")
        print("  homepage Quark buttons updated")
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--movie", action="store_true", help="sync MarcoMovie platforms")
    ap.add_argument("--tv", action="store_true", help="sync MarcoTV platforms")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.movie == args.tv:
        ap.error("pass exactly one of --movie / --tv")
    folders = MOVIE_FOLDERS if args.movie else TV_FOLDERS
    sources = movie_sources() if args.movie else tv_sources()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    if not args.dry_run:
        who = run_quark(["whoami"])
        print(f"logged in as {who.get('name')}, used {who.get('used_human')} / "
              f"{who.get('total_human')}")
    errors = []
    with tempfile.TemporaryDirectory(prefix="quark-sync-") as tmpdir:
        for key, folder in folders.items():
            try:
                manifest[key] = sync_platform(key, folder, sources[key],
                                              manifest, tmpdir, args.dry_run)
            except (QuarkError, OSError) as exc:
                print(f"[{key}] FAILED: {exc}")
                errors.append(key)
    if not args.dry_run and not errors:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        tmp = MANIFEST.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(MANIFEST)
        print(f"manifest written: {MANIFEST}")
        if args.tv:
            apply_homepage(manifest)
    if errors:
        print(f"FAILED platforms: {', '.join(errors)}")
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
