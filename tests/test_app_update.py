import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'assets/studio')]
import app_update_worker as worker
from client.app_updates import AppUpdates
from client.update_trust import verify


class AppUpdate(unittest.TestCase):
    def fixture(self,folder):
        root=folder/'客户端';root.mkdir();(root/'App').mkdir();(root/'App/VERSION').write_text('1.1.3')
        (root/'App/old.txt').write_text('previous program');(root/'VideoCopyStudio.exe').write_bytes(b'old launcher')
        (root/'offline-client.json').write_text(json.dumps({'format':'video-copy-studio-offline/v1','version':'1.1.3'}))
        for name in ('Models','Runtime','Browsers','Engine'):
            (root/name).mkdir();(root/name/'sentinel').write_bytes(b'keep resource')
        data=folder/'私有资料';data.mkdir();(data/'providers.json').write_bytes(b'encrypted-key-sentinel');(data/'job.txt').write_bytes(b'keep job')
        package=folder/'test.zip'
        with zipfile.ZipFile(package,'w') as archive:
            archive.writestr('App/VERSION','1.2.0');archive.writestr('App/assets/studio/client/app.py','# new')
            archive.writestr('App/scripts/offline_client.py','# new launcher')
            archive.writestr('VideoCopyStudio.exe',b'new launcher')
            archive.writestr('offline-client.json',json.dumps({'version':'1.2.0','resource_contract':1}))
        payload={'version':'1.2.0','min_version':'1.1.3','package':{'bytes':package.stat().st_size,'sha256':worker.sha256(package)}}
        return root,data,package,payload

    def unchanged_resources(self,root,data):
        for name in ('Models','Runtime','Browsers','Engine'):self.assertEqual((root/name/'sentinel').read_bytes(),b'keep resource')
        self.assertEqual((data/'providers.json').read_bytes(),b'encrypted-key-sentinel');self.assertEqual((data/'job.txt').read_bytes(),b'keep job')

    def test_success_replaces_only_program_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root,data,package,payload=self.fixture(Path(folder))
            with patch('client.update_trust.verify',return_value=payload):worker.apply(root,data,package,{},probe=lambda *_:None,relaunch=False)
            self.assertEqual((root/'App/VERSION').read_text(),'1.2.0');self.unchanged_resources(root,data)
            self.assertEqual(next((root/'.updates').glob('txn-*/backup/App/old.txt')).read_text(),'previous program')

    def test_startup_failure_restores_program_and_keeps_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            root,data,package,payload=self.fixture(Path(folder))
            with patch('client.update_trust.verify',return_value=payload),self.assertRaisesRegex(ValueError,'injected'):
                worker.apply(root,data,package,{},probe=lambda *_:(_ for _ in ()).throw(ValueError('injected startup error')),relaunch=False)
            self.assertEqual((root/'App/VERSION').read_text(),'1.1.3');self.assertEqual((root/'VideoCopyStudio.exe').read_bytes(),b'old launcher')
            self.unchanged_resources(root,data);self.assertEqual(worker.read_json(data/'updates/status.json')['phase'],'rolled_back')

    def test_recovery_after_process_dies_between_directory_moves(self):
        with tempfile.TemporaryDirectory() as folder:
            root,data,package,payload=self.fixture(Path(folder));txn=root/'.updates/txn-test';(txn/'backup').mkdir(parents=True)
            (root/'App').rename(txn/'backup/App');(txn/'journal.json').write_text('{"phase":"swapping"}')
            worker.recover(root,data);self.assertEqual((root/'App/VERSION').read_text(),'1.1.3');self.unchanged_resources(root,data)
            worker.recover(root,data);self.assertTrue((root/'App/old.txt').is_file())

    def test_corrupt_zip_and_downgrade_never_touch_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root,data,package,payload=self.fixture(Path(folder));package.write_bytes(b'corrupt')
            with patch('client.update_trust.verify',return_value=payload),self.assertRaises(ValueError):worker.apply(root,data,package,{},relaunch=False)
            self.assertEqual((root/'App/VERSION').read_text(),'1.1.3')
            payload['version']='1.1.2'
            with patch('client.update_trust.verify',return_value=payload),self.assertRaisesRegex(ValueError,'降级'):worker.apply(root,data,package,{},relaunch=False)

    def test_paths_and_resource_modifications_rejected(self):
        for name in ('../escape','App/../../escape','Models/model.pt','App/.studio/key.json','App/a:stream','App/a\\b','App/a./f'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);package=root/'bad.zip'
                with zipfile.ZipFile(package,'w') as archive:archive.writestr(name,'bad')
                with self.assertRaises(ValueError):worker.safe_extract(package,root/'new','1.2.0')
                self.assertFalse((root/'escape').exists())

    def test_busy_tasks_and_concurrent_writes_rejected(self):
        with patch.dict(os.environ,{'COPY_STUDIO_BUNDLE':'C:/bundle','COPY_STUDIO_CLIENT_DATA':'C:/data'}):manager=AppUpdates()
        with self.assertRaisesRegex(ValueError,'任务'):manager.begin('1.2.0',lambda:True)
        self.assertFalse(manager.busy);manager.writers=1
        with self.assertRaises(ValueError):manager.begin('1.2.0',lambda:False)
        self.assertFalse(manager.busy)

    def test_invalid_signature_never_accepted(self):
        for value in ({},{'payload':{},'signature':'bad'},{'payload':{},'signature':'AA=='}):
            with self.assertRaises(ValueError):verify(value)

    def test_relaunch_is_a_new_frozen_application_instance(self):
        with patch.object(worker.subprocess,'Popen') as launch:
            worker.launch(Path('C:/client'),Path('C:/private-data'))
        self.assertEqual(launch.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')

    def test_stale_or_unavailable_mirror_does_not_hide_newer_signed_release(self):
        from client.updates import signed_update
        from client.update_trust import MANIFEST_URLS
        def fetch(url,limit):
            if url==MANIFEST_URLS[0]:raise OSError('mirror down')
            latest='1.2.0' if url==MANIFEST_URLS[1] else '1.1.3'
            return json.dumps({'version':latest,'min_version':'1.1.3','package':{'bytes':99}}).encode()
        with patch('client.updates.public_get',side_effect=fetch),patch('client.updates.verify',side_effect=lambda x:x):
            result=signed_update('1.1.3')
        self.assertTrue(result['update_available']);self.assertEqual(result['latest'],'1.2.0')


if __name__=='__main__':unittest.main()
