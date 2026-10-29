from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from client.compute import ComputeStore,process_environment,cuda_failure


class ComputeTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        root=Path(self.folder.name);self.cpu=root/'cpu/Scripts/python.exe';self.gpu=root/'gpu/Scripts/python.exe'
        for path in (self.cpu,self.gpu):path.parent.mkdir(parents=True);path.touch()
        self.probe=Mock(return_value={'available':True,'name':'RTX test','torch':'test','cuda':'12.8'})
        self.store=ComputeStore(root,self.cpu,self.gpu,self.probe)

    def test_auto_gpu_cpu_modes_persist_and_do_not_change_inflight_plan(self):
        first=self.store.plan();self.assertEqual(first['python'],str(self.gpu));self.assertEqual(first['device'],'gpu')
        self.store.started('test-job',first);self.store.save('cpu')
        self.assertEqual(self.store.plan()['python'],str(self.cpu));self.assertEqual(first['device'],'gpu')
        self.assertEqual(self.store.peek()['last_run']['device'],'gpu')
        self.assertNotIn('python',self.store.peek()['last_run'])
        restarted=ComputeStore(self.folder.name,self.cpu,self.gpu,self.probe);self.assertEqual(restarted.mode(),'cpu')
        self.store.save('gpu');self.assertEqual(self.store.plan()['device'],'gpu')

    def test_unavailable_gpu_falls_back_only_in_auto_and_failed_save_preserves_preference(self):
        self.probe.return_value={'available':False,'reason':'CUDA unavailable'}
        self.assertEqual(self.store.plan()['device'],'cpu')
        with self.assertRaisesRegex(ValueError,'CUDA unavailable'):self.store.save('gpu')
        self.assertEqual(self.store.mode(),'auto')
        self.probe.return_value={'available':True,'name':'RTX test'};self.store.save('gpu')
        self.probe.return_value={'available':False,'reason':'Disconnected'};self.store.status(True)
        self.assertEqual(self.store.peek()['selected_device'],'unavailable')
        with self.assertRaisesRegex(ValueError,'Disconnected'):self.store.plan()

    def test_probe_is_cached_and_explicit_refresh_recovers(self):
        self.store.status();self.store.status();self.assertEqual(self.probe.call_count,1)
        self.store.status(True);self.assertEqual(self.probe.call_count,2)
        self.assertEqual(process_environment('cpu')['ENABLE_GPU'],'false')
        self.assertEqual(process_environment('cpu')['CUDA_VISIBLE_DEVICES'],'-1')
        self.assertEqual(process_environment('gpu')['ENABLE_GPU'],'true')
        self.assertTrue(cuda_failure('CUDA out of memory'))
        self.assertFalse(cuda_failure('Invalid audio input'))

    def test_offline_layout_uses_registered_engine_for_gpu_sidecar(self):
        root=Path(self.folder.name);engine=root/'Engine';cpu=root/'Runtime/python/python.exe'
        store=ComputeStore(root,cpu,probe=self.probe,asr_root=engine)
        self.assertEqual(store.gpu,engine/'.venv-gpu/Scripts/python.exe')


class TranscriptionDeviceIntegration(ComputeTests):
    def test_auto_retries_cuda_failure_on_cpu_and_keeps_actual_device(self):
        import json,os,sys
        global _app_state
        if 'client.app' not in sys.modules:
            _app_state=tempfile.TemporaryDirectory();os.environ['COPY_STUDIO_DATA']=_app_state.name
        from client import app as s
        item=s.new_job('设备集成测试','upload','');id=item['id'];s.update(id,input_file='test.wav',auto_ai=False)
        calls=[]
        def run(command,cwd,log,**options):
            calls.append(options['extra_env'])
            if len(calls)==1:log.write_text('CUDA out of memory',encoding='utf-8');raise ValueError('GPU failed')
            Path(command[command.index('--output')+1]).write_text(json.dumps({'text':'设备测试口播','segments':[]}),encoding='utf-8')
        probe=Mock(returncode=0,stdout=json.dumps({'streams':[{'codec_type':'audio'}],'format':{'duration':'5'}}))
        with patch.object(s,'COMPUTE',self.store),patch.object(s.subprocess,'run',return_value=probe),patch.object(s,'run_process',side_effect=run),patch.object(s,'inspect_reference'),patch.object(s,'load_config',return_value={}):
            s.transcribe(id)
        saved=s.get_job(id);self.assertEqual(saved['status'],'done');self.assertEqual(saved['asr_compute']['device'],'cpu')
        self.assertEqual([r['ENABLE_GPU'] for r in calls],['true','false'])
        self.assertTrue((s.directory(id)/'transcribe-gpu-error.log').exists())
        self.assertEqual(self.store.peek()['last_run']['device'],'cpu')

    def test_explicit_gpu_failure_is_not_silently_reported_as_cpu_success(self):
        import json,os,sys
        global _app_state
        if 'client.app' not in sys.modules:
            _app_state=tempfile.TemporaryDirectory();os.environ['COPY_STUDIO_DATA']=_app_state.name
        from client import app as s
        self.store.save('gpu');item=s.new_job('GPU 显式错误测试','upload','');id=item['id'];s.update(id,input_file='test.wav',auto_ai=False)
        def run(command,cwd,log,**options):log.write_text('CUDA out of memory');raise ValueError('GPU failed')
        probe=Mock(returncode=0,stdout=json.dumps({'streams':[{'codec_type':'audio'}],'format':{'duration':'5'}}))
        with patch.object(s,'COMPUTE',self.store),patch.object(s.subprocess,'run',return_value=probe),patch.object(s,'run_process',side_effect=run) as process:
            s.transcribe(id)
        self.assertEqual(process.call_count,1);self.assertEqual(s.get_job(id)['status'],'error')

    def test_compute_api_validation_and_preference_persistence(self):
        import os,sys
        global _app_state
        if 'client.app' not in sys.modules:
            _app_state=tempfile.TemporaryDirectory();os.environ['COPY_STUDIO_DATA']=_app_state.name
        from client import app as s
        from fastapi.testclient import TestClient
        c=TestClient(s.app,base_url=s.ORIGIN);c.get('/');headers={'X-Studio-Request':'1'}
        with patch.object(s,'COMPUTE',self.store):
            self.assertEqual(c.get('/api/compute').json()['selected_device'],'gpu')
            self.assertEqual(c.put('/api/compute',headers=headers,json={'mode':'cpu'}).json()['mode'],'cpu')
            self.assertEqual(c.put('/api/compute',headers=headers,json={'mode':'bad'}).status_code,422)
            self.probe.return_value={'available':False,'reason':'No CUDA'}
            self.assertEqual(c.put('/api/compute',headers=headers,json={'mode':'gpu'}).status_code,400)
            self.assertEqual(self.store.mode(),'cpu')
