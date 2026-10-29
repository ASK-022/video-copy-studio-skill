from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from setup_gpu import locations
from studio_agent import invoke

class GPUSetup(unittest.TestCase):
    def test_registered_online_and_offline_paths_keep_cpu_dependencies(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);engine=root/'Engine';engine.mkdir();(engine/'webmain.py').touch()
            for relative in ('online/Scripts/python.exe','Runtime/python/python.exe'):
                python=root/relative;python.parent.mkdir(parents=True,exist_ok=True);python.touch()
                site=python.parents[1]/'Lib/site-packages' if python.parent.name=='Scripts' else python.parent/'Lib/site-packages'
                (site/'funasr').mkdir(parents=True)
                path=root/'runtime.json';path.write_text(json.dumps({'python':str(python),'asr_root':str(engine)}),encoding='utf-8')
                self.assertEqual(locations(path),(python.resolve(),engine.resolve(),site.resolve()))

    def test_agent_compute_requests_have_separate_generation_and_device_modes(self):
        client=Mock();invoke(client,{'action':'compute','refresh':True});client.request.assert_called_with('/compute?refresh=true')
        invoke(client,{'action':'compute','compute_mode':'cpu'});client.request.assert_called_with('/compute','PUT',{'mode':'cpu'})
        with self.assertRaises(ValueError):invoke(client,{'action':'compute','compute_mode':'same'})
        with self.assertRaises(ValueError):invoke(client,{'action':'compute','refresh':'false'})
