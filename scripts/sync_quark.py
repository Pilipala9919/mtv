"""Sync MarcoMovie / MarcoTV packages to Quark Drive.

One folder per platform, one permanent share link per folder. The share
link never changes: a new release only uploads the new file into the
folder and deletes the previous file this script uploaded.

Current package per platform comes from the per-platform feeds the
mirror already publishes (movie/updates/<platform>.json), or from the
mirrored file in the repo for the two cases with no feed (Movie lite,
Marco TV + Lite).

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
    top level, but the dict is the uniform source. Newer feeds (iOS from
    0.5.6) use a single `package` object plus a `version` field instead.
    """
    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    version = feed.get("versionName") or feed.get("version")
    package = feed.get("package")
    if isinstance(package, dict) and package.get("url"):
        name = package.get("name") or ""
        if not name.endswith(package_suffix):
            raise QuarkError(f"{feed_path}: package {name} does not end {package_suffix}")
        return name, package["url"], package.get("size"), package.get("sha256"), version
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


def local_asset(path):
    """A mirrored file already in the repo; return (filename, None, size, sha256, version)."""
    if not path.exists():
        raise QuarkError(f"mirrored file missing: {path}")
    sha_path = path.with_suffix(path.suffix + ".sha256")
    sha = None
    if sha_path.exists():
        parts = sha_path.read_text(encoding="utf-8").strip().split()
        if parts:
            sha = parts[0]
    if sha is None:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
    version = None
    m = re.search(r"(\d+\.\d+\.\d+)", path.name)
    if m:
        version = m.group(1)
    return path.name, None, path.stat().st_size, sha, version


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
    src["android-lite"] = local_asset(ROOT / "movie" / "MarcoMovie-0.5.0-lite.apk")
    return src


def tv_sources():
    return {
        "tv": local_asset(ROOT / "MarcoTV-0.15.0.apk"),
        "tv-lite": local_asset(ROOT / "MarcoTV-Lite-0.1.2.apk"),
    }


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
        if url:
            local = Path(tmpdir) / name
            print(f"  downloading {url}")
            download(url, local, size, sha256)
        else:
            local = ROOT / name
            if key == "android-lite":
                local = ROOT / "movie" / name
            if not local.exists():
                raise QuarkError(f"mirrored file missing: {local}")
            print(f"  using mirrored file {local}")
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
        try:
            remove_files(folder, stale)
        except QuarkError as exc:
            print(f"  warning: remove stale failed: {exc}")
    share_url = entry.get("share_url")
    if not share_url:
        share_url = share_folder(folder)
        print(f"  new permanent share link: {share_url}")
    return {"folder": folder, "share_url": share_url, "file": name,
            "version": version, "sha256": sha256}


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
    if not args.dry_run:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        tmp = MANIFEST.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(MANIFEST)
        print(f"manifest written: {MANIFEST}")
    if errors:
        print(f"FAILED platforms: {', '.join(errors)}")
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
