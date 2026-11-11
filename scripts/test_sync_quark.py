"""Prune behaviour for the iOS keep-old Quark flow.

iOS uploads go through sync_preserving_files, which used to never delete
anything, so the folder accumulated every version (2026-11-11: 0.5.17 /
0.5.18 / 0.5.19 alongside 0.5.21). Normal syncs now prune older versions
once the current package is verified in place; explicit --keep-old runs
still never delete.
"""
import hashlib
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import sync_quark as m

FOLDER = "/MarcoMovie/iOS"
CURRENT = "MarcoMovie-0.5.21-ios-iphone-ipad-unsigned.ipa"
OLD = [
    "MarcoMovie-0.5.17-ios-iphone-ipad-unsigned.ipa",
    "MarcoMovie-0.5.18-ios-iphone-ipad-unsigned.ipa",
    "MarcoMovie-0.5.19-ios-iphone-ipad-unsigned.ipa",
]
CONTENT = b"A" * 100
DIGEST = hashlib.sha256(CONTENT).hexdigest()
SOURCE = ("https://github.com/Pilipala9919/MarcoMovie/releases/download/"
          "ios-v0.5.21/" + CURRENT)
MANIFEST = {"ios": {"folder": FOLDER, "share_url": "https://pan.quark.cn/s/88f59851a6f7",
                    "file": CURRENT, "sha256": DIGEST, "version": "0.5.21"}}


def rows(*names, folder_names=()):
    out = [{"name": n, "type": "file", "size": len(CONTENT)} for n in names]
    out += [{"name": n, "type": "folder", "size": 0} for n in folder_names]
    return out


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmpdir = self.temp.name
        self.removed = []
        self.uploaded = []
        self.source = (CURRENT, SOURCE, len(CONTENT), DIGEST, "0.5.21")

    def run_sync(self, listing, keep_old=False, rm_fails=False):
        state = {"rows": list(listing)}

        def fake_list(folder):
            self.assertEqual(folder, FOLDER)
            return [dict(r) for r in state["rows"]]

        def fake_upload(local, folder):
            self.uploaded.append(Path(local).name)
            state["rows"].append({"name": Path(local).name, "type": "file",
                                  "size": len(CONTENT)})

        def fake_remove(folder, names):
            if rm_fails:
                raise m.QuarkError("quark rm failed (category=unknown_error, exit=1)")
            self.removed.append(list(names))
            state["rows"] = [r for r in state["rows"] if r["name"] not in names]

        def fake_download(url, dest, size=None, sha256=None):
            Path(dest).write_bytes(CONTENT)
            return DIGEST

        with patch.object(m, "validate_published_source"), \
                patch.object(m, "list_folder_entries", side_effect=fake_list), \
                patch.object(m, "upload_file", side_effect=fake_upload), \
                patch.object(m, "remove_files", side_effect=fake_remove), \
                patch.object(m, "download", side_effect=fake_download):
            return m.sync_platform("ios", FOLDER, self.source, dict(MANIFEST),
                                   self.tmpdir, False, keep_old=keep_old)

    def test_present_package_prunes_older_versions(self):
        result = self.run_sync(rows(CURRENT, *OLD, folder_names=("Archive",)))
        self.assertEqual(self.uploaded, [])
        self.assertEqual(self.removed, [OLD])
        self.assertEqual(result["file"], CURRENT)

    def test_keep_old_never_prunes(self):
        self.run_sync(rows(CURRENT, *OLD), keep_old=True)
        self.assertEqual(self.removed, [])

    def test_upload_then_prunes(self):
        self.run_sync(rows(*OLD))
        self.assertEqual(self.uploaded, [CURRENT])
        self.assertEqual(self.removed, [OLD])

    def test_remove_failure_only_warns(self):
        with patch("builtins.print") as fake_print:
            result = self.run_sync(rows(CURRENT, *OLD), rm_fails=True)
        self.assertEqual(result["file"], CURRENT)
        printed = " ".join(str(c.args[0]) for c in fake_print.call_args_list)
        self.assertIn("warning: remove stale failed", printed)

    def test_manifest_mismatch_refuses_and_does_not_prune(self):
        bad = {"ios": {**MANIFEST["ios"], "sha256": "b" * 64}}
        with patch.object(m, "validate_published_source"), \
                patch.object(m, "list_folder_entries",
                             return_value=rows(CURRENT, *OLD)), \
                patch.object(m, "remove_files",
                             side_effect=AssertionError("must not delete")), \
                patch.object(m, "download",
                             side_effect=lambda u, d, size=None, sha256=None: Path(d).write_bytes(CONTENT)):
            with self.assertRaises(m.QuarkError):
                m.sync_platform("ios", FOLDER, self.source, bad,
                                self.tmpdir, False, keep_old=False)


if __name__ == "__main__":
    unittest.main()
