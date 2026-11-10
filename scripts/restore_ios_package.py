"""Restore a missing older public iOS package without changing the current feed."""
import argparse
import json
import re
import tempfile
from pathlib import Path

import sync_quark as sync


def restore(version, current):
    for value in (version, current):
        if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
            raise sync.QuarkError("Invalid iOS version")
    if tuple(map(int, version.split('.'))) >= tuple(map(int, current.split('.'))):
        raise sync.QuarkError("Only an older published iOS package may be restored")
    snapshot = sync.capture_ios_publication(sync.ROOT, current)
    sync.verify_ios_publication(sync.ROOT, snapshot)
    manifest_bytes = sync.MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    name = f'MarcoMovie-{version}-ios-iphone-ipad-unsigned.ipa'
    release = json.loads(sync.published_bytes(
        f'https://api.github.com/repos/Pilipala9919/MarcoMovie/releases/tags/ios-v{version}',
        4 * 1024 * 1024))
    assets = [a for a in release.get('assets', []) if a.get('name') == name]
    if len(assets) != 1 or not re.fullmatch(r'sha256:[0-9a-f]{64}', assets[0].get('digest') or ''):
        raise sync.QuarkError("The older package must have one published SHA-256 digest")
    asset = assets[0]
    source = (name, asset.get('browser_download_url'), asset.get('size'),
              asset['digest'][7:], version)
    # This validates release publication, exact filename, size, and checksum
    # before any cloud request. Existing same-name conflicts remain fail-closed.
    sync.validate_published_source('ios', source)
    with tempfile.TemporaryDirectory(prefix='restore-ios-') as directory:
        sync.sync_preserving_files('ios', sync.MOVIE_FOLDERS['ios'], source,
                                   manifest, Path(directory), False)
    if sync.MANIFEST.read_bytes() != manifest_bytes:
        raise sync.QuarkError("The current package manifest changed during restoration")
    sync.verify_ios_publication(sync.ROOT, snapshot)
    print(json.dumps({'restored_version':version, 'current_version':current,
                      'file':name, 'sha256':source[3], 'manifest_unchanged':True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version')
    parser.add_argument('--current', required=True)
    args = parser.parse_args()
    try:
        restore(args.version, args.current)
    except (sync.QuarkError, OSError, ValueError, TypeError) as error:
        raise SystemExit(str(error))
