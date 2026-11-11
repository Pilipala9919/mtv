"""Sync MarcoMovie / MarcoTV packages to Quark Drive.

One folder per platform, one permanent share link per folder. The share
link never changes: a new release only uploads the new file into the
folder and deletes the previous file this script uploaded. iOS follows
the same rule on normal runs (older versions are pruned once the current
package is verified in place); only an explicit --keep-old run retains
existing files.

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
    python scripts/sync_quark.py --movie --platform ios --keep-old
"""
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlsplit
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


def validate_profile_shape(raw):
    """Validate the CLI's JSON container only; never repair or print credentials."""
    try:
        profile = json.loads(raw)
        valid = (isinstance(profile, dict) and isinstance(profile.get("cookies"), list)
                 and isinstance(profile.get("ua"), str)
                 and bool(profile["ua"].strip()))
        if valid:
            for cookie in profile["cookies"]:
                valid = (isinstance(cookie, dict)
                         and all(isinstance(cookie.get(key), str) and bool(cookie[key])
                                 for key in ("name", "domain"))
                         and isinstance(cookie.get("value"), str)
                         and ("expires" not in cookie
                              or (type(cookie["expires"]) in (int, float)
                                  and math.isfinite(cookie["expires"])))
                         and ("path" not in cookie or isinstance(cookie["path"], str)))
                if not valid:
                    break
    except (ValueError, TypeError, OverflowError):
        valid = False
    if not valid:
        raise QuarkError("profile_format_invalid") from None


def safe_cli_failure(stdout, stderr, exit_code):
    """Only documented enum values and HTTP numbers may enter public logs."""
    categories = {
        "error": "unknown_error", "not_logged_in": "auth_required",
        "chrome_missing": "browser_unavailable", "profile_busy": "profile_busy",
        "network": "network", "not_found": "path_not_found",
        "local_not_found": "local_file_not_found", "not_a_folder": "not_a_folder",
        "usage": "invalid_arguments", "unknown_command": "invalid_arguments",
        "confirmation_required": "confirmation_required", "invalid_name": "invalid_name",
        "already_exists": "name_conflict", "no_space": "quota_exceeded",
        "refused": "provider_refused", "share_gone": "share_unavailable",
        "bad_code": "invalid_share_code", "login_cancelled": "auth_cancelled",
        "login_timeout": "auth_timeout", "already_logged_in": "already_authenticated",
    }
    fields = {}
    # The current CLI writes pretty-printed error JSON to stderr. A bounded
    # trailing JSON block also tolerates progress lines without printing them.
    for raw in (stderr, stdout):
        text = raw[-65536:] if isinstance(raw, str) else ""
        for match in reversed(list(re.finditer(r"(?m)^[ \t]*\{", text))):
            start = text.index("{", match.start())
            try:
                candidate, end = json.JSONDecoder().raw_decode(text, start)
            except (ValueError, RecursionError):
                continue
            if isinstance(candidate, dict) and not text[end:].strip():
                fields = candidate
                break
        if fields:
            break
    default = {2: "invalid_arguments", 3: "auth_required", 4: "path_not_found",
               5: "provider_refused"}.get(exit_code, "unknown_error")
    code = fields.get("code")
    result = {"category": categories.get(code, "unknown_error")
              if isinstance(code, str) else default,
              "exit": exit_code}
    for key in ("http_status", "httpStatus", "statusCode"):
        value = fields.get(key)
        if type(value) is int and 100 <= value <= 599:
            result["http_status"] = value
            break
    network_codes = {"ETIMEDOUT", "ECONNRESET", "ENOTFOUND", "ECONNREFUSED",
                     "EAI_AGAIN", "EHOSTUNREACH", "ENETUNREACH",
                     "ERR_TLS_CERT_ALTNAME_INVALID", "CERT_HAS_EXPIRED",
                     "UNABLE_TO_VERIFY_LEAF_SIGNATURE"}
    detail = fields.get("detail")
    if result["category"] == "network" and isinstance(detail, str) and detail in network_codes:
        result["network_code"] = detail
    return result


# ---------------------------------------------------------------- CLI

def run_quark(args):
    """Run `quark <args...> --json`, return the parsed JSON.

    `--json` must come after the command name. stdout carries the
    result, stderr carries progress and error details.
    """
    cmd = ["quark", *args, "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # CLI failures may include account/session details. Never copy raw output
        # into a public Actions log.
        diagnostic = safe_cli_failure(proc.stdout, proc.stderr, proc.returncode)
        summary = ", ".join(f"{key}={value}" for key, value in diagnostic.items())
        raise QuarkError(f"quark {args[0]} failed ({summary})")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise QuarkError(f"quark {args[0]} returned invalid JSON") from exc


def ensure_folder(folder):
    run_quark(["mkdir", folder])


def list_folder(folder):
    """Return [(name, type)] for the folder's entries (ls returns a bare array)."""
    out = run_quark(["ls", folder])
    if not isinstance(out, list):
        raise QuarkError(f"quark ls {folder} returned unexpected shape: {out!r:.200}")
    return [(i.get("name"), i.get("type")) for i in out
            if isinstance(i, dict) and i.get("name")]


def list_folder_entries(folder):
    """The CLI's ls JSON includes name, type, and file size in bytes."""
    out = run_quark(["ls", folder])
    if not isinstance(out, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("name"), str)
            or not row["name"] for row in out):
        raise QuarkError("Quark did not return a valid directory listing")
    return out


def upload_file(local_path, folder):
    out = run_quark(["upload", str(local_path), folder])
    uploaded = out.get("uploaded") or []
    if not uploaded:
        raise QuarkError("Quark did not confirm any uploaded file")
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
        received = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            received += len(chunk)
            if size is not None and received > size:
                raise QuarkError(f"download exceeds the published size for {dest.name}")
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


def movie_sources(platform=None):
    updates = ROOT / "movie" / "updates"
    src = {}

    def feed(name, suffix):
        stable = updates / f"{name}.json"
        preview = updates / f"{name}-preview.json"
        path = stable if stable.exists() else preview
        if not path.exists():
            raise QuarkError(f"no feed for {name}: {stable} / {preview}")
        return feed_asset(path, suffix)

    for key, (name, suffix) in {
        "android-tv": ("android-tv", ".apk"),
        "android-mobile": ("android-mobile", ".apk"),
        "ios": ("ios", ".ipa"),
        "windows-setup": ("windows", "-setup.exe"),
        "windows-zip": ("windows", ".zip"),
        "macos": ("macos", ".zip"),
        "android-lite": ("android-lite", ".apk"),
    }.items():
        if platform is not None and key != platform:
            continue
        if key == "android-lite" and not any(
                (updates / name).exists() for name in
                ("android-lite.json", "android-lite-preview.json")):
            src[key] = local_asset(ROOT / "movie" / "MarcoMovie-0.5.0-lite.apk")
        else:
            src[key] = feed(name, suffix)
    return src


def tv_sources():
    return {
        "tv": local_asset(ROOT / "MarcoTV-0.15.0.apk"),
        "tv-lite": local_asset(ROOT / "MarcoTV-Lite-0.1.2.apk"),
    }


# ---------------------------------------------------------------- sync

def published_bytes(url, limit):
    """Read public release metadata/checksums without printing credentials."""
    headers = dict(UA)
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                    timeout=60) as response:
            body = response.read(limit + 1)
    except OSError as exc:
        raise QuarkError("Cannot verify the published GitHub release") from exc
    if len(body) > limit:
        raise QuarkError("Published release response exceeds the size limit")
    return body


def validate_published_source(key, source):
    """Bind a scoped upload to one immutable, publicly released package."""
    name, url, size, digest, version = source
    if (key not in MOVIE_FOLDERS or not isinstance(version, str)
            or not re.fullmatch(r"\d+\.\d+\.\d+", version)
            or not isinstance(name, str)
            or not re.fullmatch(r"MarcoMovie-" + re.escape(version)
                                + r"-[A-Za-z0-9-]+\.(?:ipa|apk|exe|zip)", name)
            or type(size) is not int or not 0 < size <= 300 * 1024 * 1024
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise QuarkError("Scoped upload requires a valid version, size and SHA-256")
    platform = "windows" if key.startswith("windows-") else key
    allowed_suffixes = {
        "ios": ("ios-unsigned.ipa", "ios-iphone-ipad-unsigned.ipa"),
        "android-tv": ("android-tv.apk",),
        "android-mobile": ("android-mobile.apk",),
        "android-lite": ("android-lite.apk",),
        "windows-setup": ("windows-setup.exe", "windows-x64-setup.exe"),
        "windows-zip": ("windows-x64.zip", "windows-x64-portable.zip"),
        "macos": ("macos.zip", "macos-desktop.zip"),
    }
    if name not in {f"MarcoMovie-{version}-{suffix}" for suffix in allowed_suffixes[key]}:
        raise QuarkError("Package filename does not match the selected platform")
    tag = f"{platform}-v{version}"
    release_url = f"https://github.com/Pilipala9919/MarcoMovie/releases/download/{tag}/{name}"
    if url not in (release_url, f"https://marcotv.wlj9919.top/movie/{name}"):
        raise QuarkError("Package URL does not match the official platform release")
    try:
        release = json.loads(published_bytes(
            f"https://api.github.com/repos/Pilipala9919/MarcoMovie/releases/tags/{tag}",
            4 * 1024 * 1024))
        if (release.get("tag_name") != tag or release.get("draft")
                or release.get("prerelease") or not release.get("published_at")):
            raise QuarkError("The selected platform release is not publicly published")
        assets = release.get("assets", [])
        found = [a for a in assets if a.get("name") == name and a.get("state") == "uploaded"]
        checksums = [a for a in assets if a.get("name") == name + ".sha256"
                     and a.get("state") == "uploaded"]
        if (len(found) != 1 or len(checksums) != 1
                or found[0].get("browser_download_url") != release_url
                or found[0].get("size") != size
                or found[0].get("digest") not in (None, "sha256:" + digest)
                or checksums[0].get("browser_download_url") != release_url + ".sha256"):
            raise QuarkError("Published package metadata does not match the feed")
        checksum = published_bytes(release_url + ".sha256", 4096).decode("ascii").split()
        if len(checksum) != 2 or checksum != [digest, name]:
            raise QuarkError("Published package checksum does not match the feed")
    except (ValueError, TypeError, AttributeError) as exc:
        raise QuarkError("Invalid published release metadata") from exc


def checked_remote_file(rows, name, size):
    matches = [row for row in rows if row["name"] == name]
    if len(matches) != 1 or matches[0].get("type") != "file":
        raise QuarkError("Uploaded package was not uniquely confirmed in its directory")
    remote_size = matches[0].get("size")
    if type(remote_size) is not int or remote_size != size:
        raise QuarkError("Uploaded package size was not confirmed")


def ios_feed_fingerprint(root, version):
    """Only release notes may change while a scoped package upload is running."""
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise QuarkError("Invalid requested iOS version")
    path = Path(root) / "movie/updates/ios.json"
    feed = json.loads(path.read_text(encoding="utf-8"))
    release_url = "https://github.com/Pilipala9919/MarcoMovie/releases/tag/ios-v" + version
    if (feed.get("platform") != "ios" or feed.get("versionName") != version
            or feed.get("prerelease") is not False or feed.get("release_url") != release_url):
        raise QuarkError("Current iOS feed does not match the requested platform release")
    name, url, size, digest, source_version = feed_asset(path, ".ipa")
    return {"platform": feed["platform"], "prerelease": feed["prerelease"],
            "release_url": feed["release_url"],
            "package": {"name": name, "url": url, "size": size,
                        "sha256": digest, "version": source_version}}


def ios_manifest_fingerprint(root):
    manifest = json.loads((Path(root) / "scripts/quark.json").read_text(encoding="utf-8"))
    entry = manifest.get("ios")
    if not isinstance(entry, dict):
        raise QuarkError("Missing existing iOS share manifest")
    return {key: entry.get(key) for key in ("folder", "share_url", "file", "sha256", "version")}


def capture_ios_publication(root, version):
    feed = ios_feed_fingerprint(root, version)
    previous = ios_manifest_fingerprint(root)
    package = feed["package"]
    return {"version": version, "feed": feed, "beforeManifest": previous,
            "manifest": {**previous, "file": package["name"],
                         "sha256": package["sha256"], "version": package["version"]}}


def verify_ios_publication(root, snapshot, before_upload=False):
    """Fail closed on same-version package/share changes before any git push."""
    if ios_feed_fingerprint(root, snapshot["version"]) != snapshot["feed"]:
        raise QuarkError("iOS package metadata changed during upload; publication stopped")
    expected = snapshot["beforeManifest" if before_upload else "manifest"]
    if ios_manifest_fingerprint(root) != expected:
        raise QuarkError("iOS share manifest changed during upload; publication stopped")


def prune_stale_files(folder, name):
    """Remove every file in folder except name.

    Only called after the current package was verified present in the
    folder, so the new version is never at risk. A failed removal only
    warns; the sync still succeeds and retries on the next run.
    Non-file entries are never touched.
    """
    stale = [row["name"] for row in list_folder_entries(folder)
             if row.get("type") == "file" and row["name"] != name]
    if not stale:
        return
    print(f"  removing previous version(s): {', '.join(stale)}")
    try:
        remove_files(folder, stale)
    except QuarkError as exc:
        print(f"  warning: remove stale failed: {exc}")


def sync_preserving_files(key, folder, source, manifest, tmpdir, dry_run, prune=False):
    name, url, size, digest, version = source
    validate_published_source(key, source)
    entry = manifest.get(key, {})
    share = urlsplit(entry.get("share_url") or "")
    if (folder != MOVIE_FOLDERS[key] or entry.get("folder") != folder
            or share.scheme != "https" or share.netloc != "pan.quark.cn"
            or not re.fullmatch(r"/s/[A-Za-z0-9_-]+", share.path)):
        raise QuarkError("Keep-old mode requires the existing managed folder and permanent share")
    if dry_run:
        print(f"[{key}] verified {version}; would upload"
              + (" and prune older versions" if prune else " without removing any files"))
        return entry
    local = Path(tmpdir) / name
    download(url, local, size, digest)
    # Validate at the upload boundary too, independently of the downloader.
    if local.stat().st_size != size or hashlib.sha256(local.read_bytes()).hexdigest() != digest:
        raise QuarkError("Local package failed verification before upload")
    before = list_folder_entries(folder)
    if any(row["name"] == name for row in before):
        if entry.get("file") != name or entry.get("sha256") != digest:
            raise QuarkError("Same-name package already exists; keep-old mode refuses replacement")
        checked_remote_file(before, name, size)
        if prune:
            print(f"[{key}] verified package is already present; pruning older versions")
            prune_stale_files(folder, name)
        else:
            print(f"[{key}] verified package is already present; no upload or deletion")
        return entry
    upload_file(local, folder)
    after = list_folder_entries(folder)
    checked_remote_file(after, name, size)
    for row in before:
        if not any(all(candidate.get(k) == row.get(k) for k in ("name", "type", "size"))
                   for candidate in after):
            raise QuarkError("Existing directory entries changed during upload")
    if prune:
        print(f"[{key}] uploaded and verified {version}")
        prune_stale_files(folder, name)
    else:
        print(f"[{key}] uploaded and verified {version}; all existing files retained")
    return {**entry, "folder": folder, "file": name, "version": version, "sha256": digest}


def sync_platform(key, folder, source, manifest, tmpdir, dry_run, keep_old=False):
    if keep_old:
        return sync_preserving_files(key, folder, source, manifest, tmpdir, dry_run)
    if key == "ios":
        # iOS keeps the preserving upload flow, but prunes older versions
        # once the current package is verified in place (2026-11-11: the
        # folder had accumulated 0.5.17/0.5.18/0.5.19 alongside 0.5.21
        # because the preserving path never deleted anything).
        return sync_preserving_files(key, folder, source, manifest, tmpdir,
                                     dry_run, prune=True)
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
    ap.add_argument("--platform", choices=tuple(MOVIE_FOLDERS),
                    help="sync only this MarcoMovie platform")
    ap.add_argument("--keep-old", action="store_true",
                    help="never remove/replace files; require an existing permanent share")
    args = ap.parse_args(argv)
    if args.movie == args.tv:
        ap.error("pass exactly one of --movie / --tv")
    if args.platform and not args.movie:
        ap.error("--platform is only available with --movie")
    if args.keep_old and not args.platform:
        ap.error("--keep-old requires --movie --platform")
    folders = ({args.platform: MOVIE_FOLDERS[args.platform]} if args.platform
               else MOVIE_FOLDERS if args.movie else TV_FOLDERS)
    sources = movie_sources(args.platform) if args.movie else tv_sources()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    errors = []
    with tempfile.TemporaryDirectory(prefix="quark-sync-") as tmpdir:
        for key, folder in folders.items():
            try:
                manifest[key] = sync_platform(key, folder, sources[key],
                                              manifest, tmpdir, args.dry_run,
                                              keep_old=args.keep_old)
            except (QuarkError, OSError) as exc:
                print(f"[{key}] FAILED: {exc}")
                errors.append(key)
    if not args.dry_run and (not args.keep_old or not errors):
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
