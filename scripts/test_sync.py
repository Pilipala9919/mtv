# Copyright (C) 2026 Pilipala
"""Offline checks: corrupt or unpublished update data must never replace a channel."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_release as sync

class SyncChecks(unittest.TestCase):
    def exercise(self, change=None, fail=False):
        data=b'APK fixture';sha=hashlib.sha256(data).hexdigest();name='MarcoTV-1.2.3.apk'
        url=f'https://github.com/{sync.SOURCE_REPO}/releases/download/v1.2.3/{name}'
        feed=dict(schema=1,versionCode=100,versionName='1.2.3',minSdk=23,size=len(data),sha256=sha,url=url,prerelease=False)
        release=dict(draft=False,prerelease=False,assets=[dict(name=name,browser_download_url=url,size=len(data),digest='sha256:'+sha),dict(name=name+'.sha256',browser_download_url=url+'.sha256')])
        altered=copy.deepcopy(feed)
        if change:change(altered,release)
        def fetch(address,binary=False):
            if address.endswith('/stable.json'):return json.dumps(feed)
            if address.endswith('/preview.json'):return json.dumps(altered)
            if '/releases/tags/' in address:return json.dumps(release)
            if address==url:return data
            if address==url+'.sha256':return sha+'  '+name
            raise AssertionError(address)
        with tempfile.TemporaryDirectory() as directory,patch.object(sync,'ROOT',Path(directory)),patch.object(sync,'fetch',fetch):
            existing=Path(directory)/'updates/stable.json';existing.parent.mkdir();existing.write_text('previous')
            if fail:
                with self.assertRaises(ValueError):sync.sync_update_channels()
                self.assertEqual(existing.read_text(),'previous')
            else:
                sync.sync_update_channels()
                self.assertEqual(json.loads(existing.read_text())['url'],'https://marcotv.wlj9919.top/'+name)
                self.assertEqual((Path(directory)/name).read_bytes(),data)
    def test_valid_channels(self):self.exercise()
    def test_bad_digest_keeps_old_index(self):self.exercise(lambda f,r:f.update(sha256='0'*64),True)
    def test_wrong_url_keeps_old_index(self):self.exercise(lambda f,r:f.update(url='https://example.org/test.apk'),True)
    def test_draft_keeps_old_index(self):self.exercise(lambda f,r:r.update(draft=True),True)
    def test_traversal_keeps_old_index(self):self.exercise(lambda f,r:f.update(versionName='../evil'),True)

if __name__=='__main__':unittest.main()
