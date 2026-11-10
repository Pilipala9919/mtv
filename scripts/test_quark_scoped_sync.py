"""Synthetic release and CLI responses; never access an account or upload a file."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import sync_quark as sync


class ScopedUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.body = b"synthetic iOS package bytes"
        self.digest = hashlib.sha256(self.body).hexdigest()
        self.version = "0.5.15"
        self.name = "MarcoMovie-0.5.15-ios-iphone-ipad-unsigned.ipa"
        self.url = ("https://github.com/Pilipala9919/MarcoMovie/releases/download/"
                    "ios-v0.5.15/" + self.name)
        self.source = (self.name, self.url, len(self.body), self.digest, self.version)
        self.folder = sync.MOVIE_FOLDERS["ios"]
        self.old = {"name": "old.ipa", "type": "file", "size": 3}
        self.unrelated = {"name": "user-notes.txt", "type": "file", "size": 19}
        self.current = {"name": self.name, "type": "file", "size": len(self.body)}
        self.manifest = {
            "ios": {"folder": self.folder, "share_url": "https://pan.quark.cn/s/synthetic",
                    "file": "old.ipa", "version": "0.5.14", "sha256": "a" * 64,
                    "extra_metadata": "retain"},
            "android-tv": {"version": "0.5.15", "share_url": "synthetic-tv"},
            "windows-setup": {"version": "0.5.8", "custom": {"keep": True}},
        }
        self.release = {
            "tag_name": "ios-v0.5.15", "draft": False, "prerelease": False,
            "published_at": "2026-11-10T10:43:51Z",
            "assets": [
                {"name": self.name, "size": len(self.body), "state": "uploaded",
                 "digest": "sha256:" + self.digest, "browser_download_url": self.url},
                {"name": self.name + ".sha256", "state": "uploaded",
                 "browser_download_url": self.url + ".sha256"},
            ],
        }
        self.checksum = (self.digest + "  " + self.name + "\n").encode()
        self.commands = []
        self.listings = [[self.old, self.unrelated],
                         [self.old, self.unrelated, self.current]]
        self.start_patch(sync, "ROOT", self.root)
        self.manifest_path = self.root / "scripts/quark.json"
        self.manifest_path.parent.mkdir()
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        self.start_patch(sync, "MANIFEST", self.manifest_path)
        self.start_patch(sync, "published_bytes", side_effect=self.published)
        self.start_patch(sync, "download", side_effect=self.download)
        self.start_patch(sync, "run_quark", side_effect=self.cli)
        self.no_delete = self.start_patch(sync, "remove_files",
                                         side_effect=AssertionError("deletion forbidden"))
        self.no_mkdir = self.start_patch(sync, "ensure_folder",
                                        side_effect=AssertionError("mkdir forbidden"))
        self.no_share = self.start_patch(sync, "share_folder",
                                        side_effect=AssertionError("new share forbidden"))
        feed = {"schema": 1, "platform": "ios", "versionName": self.version,
                "prerelease": False,
                "release_url": self.url.rsplit("/", 1)[0].replace("/download/", "/tag/"),
                "packages": {self.name: {"url": self.url, "size": len(self.body),
                                         "sha256": self.digest}}}
        path = self.root / "movie/updates/ios.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(feed), encoding="utf-8")

    def start_patch(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def published(self, url, limit):
        if url == self.url + ".sha256":
            return self.checksum
        self.assertEqual(url, "https://api.github.com/repos/Pilipala9919/MarcoMovie/"
                             "releases/tags/ios-v0.5.15")
        return json.dumps(self.release).encode()

    def download(self, url, target, size, digest):
        self.assertEqual((url, size, digest), (self.url, len(self.body), self.digest))
        target.write_bytes(self.body)

    def cli(self, args):
        self.commands.append(args)
        self.assertNotIn(args[0], ("rm", "mkdir", "share", "whoami"))
        if args[0] == "ls":
            self.assertEqual(args, ["ls", self.folder])
            return self.listings.pop(0)
        self.assertEqual(args[0], "upload")
        self.assertEqual(args[2], self.folder)
        self.assertEqual(Path(args[1]).name, self.name)
        self.assertEqual(Path(args[1]).read_bytes(), self.body)
        return {"uploaded": [{"path": self.folder + "/" + self.name,
                              "size": len(self.body)}]}

    def run_main(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return sync.main(["--movie", "--platform", "ios", "--keep-old"])

    def run_scoped(self, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return sync.sync_platform("ios", self.folder, self.source, self.manifest,
                                      self.root, dry_run, keep_old=True)

    def test_only_ios_upload_preserves_other_manifest_and_existing_files(self):
        self.assertEqual(self.run_main(), 0)
        result = json.loads(self.manifest_path.read_text())
        for key in self.manifest:
            if key != "ios":
                self.assertEqual(result[key], self.manifest[key])
        self.assertEqual(result["ios"]["file"], self.name)
        self.assertEqual(result["ios"]["sha256"], self.digest)
        self.assertEqual(result["ios"]["share_url"], self.manifest["ios"]["share_url"])
        self.assertEqual(result["ios"]["extra_metadata"], "retain")
        self.assertEqual([c[0] for c in self.commands], ["ls", "upload", "ls"])
        self.no_delete.assert_not_called()
        self.no_mkdir.assert_not_called()
        self.no_share.assert_not_called()

    def test_selector_does_not_read_unselected_platform_feeds(self):
        self.assertEqual(sync.movie_sources("ios"), {"ios": self.source})
        self.assertFalse((self.root / "movie/updates/windows.json").exists())

    def test_selector_rejects_tv_unknown_platform_and_unscoped_keep_old(self):
        for args in (["--tv", "--platform", "ios"], ["--movie", "--platform", "unknown"],
                     ["--tv", "--keep-old"], ["--movie", "--keep-old"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    sync.main(args)
        self.assertEqual(self.commands, [])

    def test_same_name_conflict_fails_without_upload_or_manifest_change(self):
        self.listings = [[self.old, self.current]]
        before = self.manifest_path.read_bytes()
        self.assertEqual(self.run_main(), 1)
        self.assertEqual([c[0] for c in self.commands], ["ls"])
        self.assertEqual(self.manifest_path.read_bytes(), before)
        self.no_delete.assert_not_called()

    def test_verified_existing_package_is_idempotent_without_upload(self):
        self.manifest["ios"].update(file=self.name, sha256=self.digest, version=self.version)
        self.listings = [[self.old, self.current]]
        result = self.run_scoped()
        self.assertEqual(result, self.manifest["ios"])
        self.assertEqual([c[0] for c in self.commands], ["ls"])

    def test_existing_same_name_wrong_or_missing_size_fails(self):
        self.manifest["ios"].update(file=self.name, sha256=self.digest)
        for size in (None, len(self.body) - 1, str(len(self.body))):
            with self.subTest(size=size):
                self.listings = [[{**self.current, "size": size}]]
                with self.assertRaises(sync.QuarkError):
                    self.run_scoped()
        self.assertTrue(all(c[0] == "ls" for c in self.commands))

    def test_post_upload_missing_wrong_size_or_duplicate_fails(self):
        for after in ([self.old, self.unrelated],
                      [self.old, self.unrelated, {**self.current, "size": 1}],
                      [self.old, self.unrelated, self.current, self.current]):
            with self.subTest(after=after):
                self.listings = [[self.old, self.unrelated], after]
                before = self.manifest_path.read_bytes()
                self.assertEqual(self.run_main(), 1)
                self.assertEqual(self.manifest_path.read_bytes(), before)
        self.no_delete.assert_not_called()

    def test_removed_unrelated_file_prevents_claiming_success(self):
        self.listings = [[self.old, self.unrelated], [self.old, self.current]]
        with self.assertRaises(sync.QuarkError):
            self.run_scoped()
        self.no_delete.assert_not_called()

    def test_invalid_publication_or_metadata_never_reaches_cloud(self):
        original = copy.deepcopy(self.release)
        mutations = [lambda r: r.update(draft=True), lambda r: r.update(prerelease=True),
                     lambda r: r.update(published_at=None),
                     lambda r: r.update(tag_name="ios-v0.5.14"),
                     lambda r: r["assets"][0].update(size=1),
                     lambda r: r["assets"][0].update(digest="sha256:" + "0" * 64),
                     lambda r: r["assets"][0].update(browser_download_url="https://example.invalid/file"),
                     lambda r: r["assets"].pop()]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.release = copy.deepcopy(original)
                mutate(self.release)
                with self.assertRaises(sync.QuarkError):
                    self.run_scoped()
        self.assertEqual(self.commands, [])
        sync.download.assert_not_called()

    def test_invalid_feed_size_hash_url_or_platform_name_is_rejected(self):
        for position, value in ((0, "../escape.ipa"), (1, "https://evil.invalid/package.ipa"),
                                (2, None), (2, True), (3, "bad-sha"), (4, "1;echo secret"),
                                (0, "MarcoMovie-0.5.15-windows-setup.exe")):
            source = list(self.source)
            source[position] = value
            with self.subTest(position=position, value=value):
                with self.assertRaises(sync.QuarkError):
                    sync.validate_published_source("ios", source)
        self.assertEqual(self.commands, [])

    def test_official_checksum_mismatch_prevents_download_and_upload(self):
        self.checksum = ("0" * 64 + "  " + self.name).encode()
        with self.assertRaises(sync.QuarkError):
            self.run_scoped()
        sync.download.assert_not_called()
        self.assertEqual(self.commands, [])

    def test_local_hash_or_size_failure_prevents_upload(self):
        for body in (b"short", b"x" * len(self.body)):
            with self.subTest(body=body):
                sync.download.side_effect = lambda url, path, size, digest: path.write_bytes(body)
                with self.assertRaises(sync.QuarkError):
                    self.run_scoped()
        self.assertEqual(self.commands, [])

    def test_missing_or_changed_existing_folder_or_share_is_rejected(self):
        original = copy.deepcopy(self.manifest["ios"])
        for mutation in ({"share_url": ""}, {"folder": "/other"},
                         {"share_url": "https://pan.quark.cn.evil/s/synthetic"}):
            self.manifest["ios"] = {**original, **mutation}
            with self.subTest(mutation=mutation):
                with self.assertRaises(sync.QuarkError):
                    self.run_scoped()
        sync.download.assert_not_called()
        self.assertEqual(self.commands, [])

    def test_dry_run_verifies_metadata_without_cloud_or_download(self):
        self.assertEqual(self.run_scoped(dry_run=True), self.manifest["ios"])
        self.assertEqual(self.commands, [])
        sync.download.assert_not_called()

    def finish_manifest(self, snapshot):
        current = copy.deepcopy(self.manifest)
        current['ios'].update(snapshot['manifest'])
        self.manifest_path.write_text(json.dumps(current), encoding='utf-8')

    def test_publication_snapshot_checks_before_upload_and_after_success(self):
        snapshot = sync.capture_ios_publication(self.root, self.version)
        sync.verify_ios_publication(self.root, snapshot, before_upload=True)
        with self.assertRaises(sync.QuarkError):
            sync.verify_ios_publication(self.root, snapshot)
        self.finish_manifest(snapshot)
        sync.verify_ios_publication(self.root, snapshot)
        with self.assertRaises(sync.QuarkError):
            sync.verify_ios_publication(self.root, snapshot, before_upload=True)

    def test_same_version_package_field_changes_stop_publication(self):
        snapshot = sync.capture_ios_publication(self.root, self.version)
        self.finish_manifest(snapshot)
        path = self.root / 'movie/updates/ios.json'
        original = json.loads(path.read_text())
        mutations = [
            lambda f: f['packages'][self.name].update(url=self.url + '?changed'),
            lambda f: f['packages'][self.name].update(size=len(self.body) + 1),
            lambda f: f['packages'][self.name].update(sha256='b' * 64),
            lambda f: f['packages'].update({'MarcoMovie-0.5.15-ios-unsigned.ipa': f['packages'].pop(self.name)}),
            lambda f: f.update(platform='macos'),
            lambda f: f.update(prerelease=True),
            lambda f: f.update(release_url='https://example.invalid/same-version'),
            lambda f: f.update(versionName='0.5.16'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                feed = copy.deepcopy(original)
                mutate(feed)
                path.write_text(json.dumps(feed), encoding='utf-8')
                with self.assertRaises(sync.QuarkError):
                    sync.verify_ios_publication(self.root, snapshot)

    def test_manifest_field_changes_stop_publication(self):
        snapshot = sync.capture_ios_publication(self.root, self.version)
        for key, value in [('folder', '/other'), ('share_url', 'https://pan.quark.cn/s/other'),
                           ('file', 'other.ipa'), ('sha256', 'f' * 64), ('version', '0.5.16')]:
            with self.subTest(field=key):
                self.finish_manifest(snapshot)
                manifest = json.loads(self.manifest_path.read_text())
                manifest['ios'][key] = value
                self.manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
                with self.assertRaises(sync.QuarkError):
                    sync.verify_ios_publication(self.root, snapshot)

    def test_notes_only_change_is_allowed_before_and_after_upload(self):
        snapshot = sync.capture_ios_publication(self.root, self.version)
        path = self.root / 'movie/updates/ios.json'
        feed = json.loads(path.read_text())
        feed['notes'] = 'Corrected release notes; package bytes and share are unchanged.'
        path.write_text(json.dumps(feed), encoding='utf-8')
        sync.verify_ios_publication(self.root, snapshot, before_upload=True)
        self.finish_manifest(snapshot)
        sync.verify_ios_publication(self.root, snapshot)

    def test_requested_version_is_not_interpreted_as_shell_or_other_release(self):
        for version in ['0.5.15; echo unsafe', '0.5.15\n', '../0.5.15', '0.5.14']:
            with self.subTest(version=version):
                with self.assertRaises(sync.QuarkError):
                    sync.capture_ios_publication(self.root, version)


class WorkflowAndLoggingTests(unittest.TestCase):
    def test_cli_errors_do_not_repeat_account_or_cookie_output(self):
        for response in (subprocess.CompletedProcess([], 1, "account-secret", "cookie-secret"),
                         subprocess.CompletedProcess([], 0, "cookie-secret", "")):
            with patch.object(sync.subprocess, "run", return_value=response):
                with self.assertRaises(sync.QuarkError) as error:
                    sync.run_quark(["ls", "/synthetic"])
            self.assertNotIn("secret", str(error.exception))

    def test_workflow_is_manual_main_only_scoped_and_same_concurrency_group(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/sync-ios-package.yml"
        text = path.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("if: github.ref == 'refs/heads/main'", text)
        self.assertIn("group: sync-movie", text)
        self.assertIn("EXPECTED_VERSION: ${{ inputs.version }}", text)
        self.assertIn("os.environ['EXPECTED_VERSION']", text)
        self.assertIn("--movie --platform ios --keep-old", text)
        self.assertNotIn("whoami", text)
        self.assertNotIn("sync_platform_packages.py", text)
        self.assertIn("git add -- scripts/quark.json", text)
        self.assertNotIn("git add movie", text)
        self.assertIn("git pull --rebase origin main", text)
        self.assertIn("Path(os.environ['RUNNER_TEMP'])", text)
        self.assertIn("verify_ios_publication(Path('.'), snapshot, before_upload=True)", text)
        self.assertEqual(text.count("verify_ios_publication(Path('.'), snapshot)"), 2)
        before_commit = text.index("verify_ios_publication(Path('.'), snapshot)")
        after_rebase = text.rindex("verify_ios_publication(Path('.'), snapshot)")
        self.assertLess(before_commit, text.index('git add -- scripts/quark.json'))
        self.assertGreater(after_rebase, text.index('git pull --rebase origin main'))
        self.assertLess(after_rebase, text.index('git push origin HEAD:main'))


if __name__ == "__main__":
    unittest.main()
