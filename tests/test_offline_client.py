import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from asr_compat import offline_model_path
from offline_client import request
from offline_client import single_client
from bootstrap import upstream,patch_runtime
from build_offline_client import copy_tree


class OfflineClient(unittest.TestCase):
    def test_offline_models_do_not_fall_back_to_network_ids(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'VIDEO_COPY_STUDIO_OFFLINE_MODELS':folder}):
            with self.assertRaises(FileNotFoundError):offline_model_path('iic/SenseVoiceSmall')
            with self.assertRaises(ValueError):offline_model_path('unknown/remote-model')
            target=Path(folder)/'sensevoice';target.mkdir();(target/'model.pt').write_bytes(b'local');(target/'config.yaml').write_text('model: local')
            self.assertEqual(offline_model_path('iic/SenseVoiceSmall'),str(target.resolve()))

    def test_online_mode_keeps_original_model_id(self):
        with patch.dict('os.environ',{'VIDEO_COPY_STUDIO_OFFLINE_MODELS':''}):
            self.assertEqual(offline_model_path('iic/SenseVoiceSmall'),'iic/SenseVoiceSmall')

    def test_runtime_patches_are_idempotent_and_compile(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'engine';upstream(target);patch_runtime(target)
            first=(target/'core/sensevoice_transcriber.py').read_text(encoding='utf-8')
            patch_runtime(target)
            self.assertEqual(first,(target/'core/sensevoice_transcriber.py').read_text(encoding='utf-8'))
            for name in ('core/sensevoice_transcriber.py','utils/forced_aligner.py'):
                source=(target/name).read_text(encoding='utf-8');compile(source,name,'exec')
                self.assertIn('offline_model_path(',source)

    def test_client_control_never_contacts_remote_hosts(self):
        with self.assertRaises(ValueError):request('https://example.com')

    def test_dependency_data_is_kept_while_private_state_is_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';(source/'package/data').mkdir(parents=True);(source/'.studio').mkdir()
            (source/'package/data/resource.bin').write_bytes(b'public-package-resource')
            (source/'.studio/private.json').write_text('{}')
            copy_tree(source,root/'target')
            self.assertTrue((root/'target/package/data/resource.bin').is_file())
            self.assertFalse((root/'target/.studio').exists())

    @unittest.skipUnless(sys.platform=='win32','Windows client')
    def test_second_window_cannot_close_an_existing_client(self):
        import threading
        with tempfile.TemporaryDirectory() as folder:
            results=[]
            def second():
                with single_client(folder) as acquired:results.append(acquired)
            with single_client(folder) as acquired:
                self.assertTrue(acquired);worker=threading.Thread(target=second);worker.start();worker.join()
            self.assertEqual(results,[False])
            with single_client(folder) as acquired:self.assertTrue(acquired)

    @unittest.skipUnless(sys.platform=='win32','Windows installer')
    def test_resource_installer_rejects_corrupt_or_escaping_parts(self):
        import offline_setup as setup
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);name=f'VideoCopyStudio-Offline-v{setup.VERSION}-part01.zip'
            archive=folder/name
            with zipfile.ZipFile(archive,'w') as output:output.writestr('../escaped.txt','bad')
            value={'format':'video-copy-studio-offline-downloads/v1','version':setup.VERSION,'client_dir':'VideoCopyStudio-Offline-v'+setup.VERSION,
                   'parts':[{'name':name,'bytes':archive.stat().st_size,'sha256':setup.digest(archive)}]}
            (folder/f'offline-downloads-v{setup.VERSION}.json').write_text(json.dumps(value))
            with self.assertRaises(ValueError):setup.install(folder,folder/'target')
            self.assertFalse((folder/'escaped.txt').exists())
            value['parts'][0]['sha256']='0'*64
            (folder/f'offline-downloads-v{setup.VERSION}.json').write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'校验失败'):setup.install(folder,folder/'target')


if __name__=='__main__':unittest.main()
