import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile

import contenthub_progress as progress
import contenthub_offline_setup as offline


class ResourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='contenthub-resource-test-');self.root=Path(self.temp.name)
        self.payload=bytes(range(256))*1024;self.requests=[];self.events=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_args):pass
            def do_GET(self):
                owner.requests.append((self.path,self.headers.get('Range')))
                if self.path=='/error':self.send_error(503);return
                offset=int(self.headers.get('Range','bytes=0-')[6:].split('-')[0])
                if self.path=='/ignore':offset=0
                body=owner.payload[offset:]
                self.send_response(206 if offset else 200)
                if self.path!='/unknown':self.send_header('Content-Length',str(len(body)))
                if offset:self.send_header('Content-Range',f'bytes {offset}-{len(owner.payload)-1}/{len(owner.payload)}')
                self.end_headers()
                try:
                    if self.path=='/cut':self.wfile.write(body[:32768]);self.wfile.flush();return
                    if self.path=='/wrong':self.wfile.write(b'x'*len(body));return
                    if self.path=='/slow':
                        for index in range(0,len(body),64):self.wfile.write(body[index:index+64]);self.wfile.flush();time.sleep(.04)
                    else:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):self.server.shutdown();self.server.server_close();self.temp.cleanup()

    def emit(self,kind,**fields):self.events.append({'kind':kind,**fields})

    def download(self,paths,**kwargs):
        target=self.root/'resource.zip'
        progress.download_file([(f'线路 {i}',self.origin+path) for i,path in enumerate(paths,1)],target,hashlib.sha256(self.payload).hexdigest(),emit=self.emit,**kwargs)
        self.assertEqual(target.read_bytes(),self.payload);return target

    def test_dropped_connection_resumes_on_next_source_with_visible_reason(self):
        self.download(['/cut','/good'])
        self.assertEqual(self.requests[1],('/good','bytes=32768-'))
        switch=[e for e in self.events if e['kind']=='source'][1]
        self.assertEqual(switch['previous'],'线路 1');self.assertTrue(switch['reason']);self.assertEqual(switch['attempt'],2)

    def test_ignored_range_restarts_cleanly_and_explains_reset(self):
        target=self.root/'resource.zip';part=target.with_name(target.name+'.part');part.write_bytes(self.payload[:100])
        part.with_name(part.name+'.json').write_text(json.dumps({'sha256':hashlib.sha256(self.payload).hexdigest(),'name':target.name}))
        self.download(['/ignore']);self.assertEqual(self.requests[0][1],'bytes=100-')
        self.assertTrue(any('不支持断点' in e.get('message','') for e in self.events))

    def test_wrong_checksum_is_not_reused_on_backup(self):
        self.download(['/wrong','/good']);self.assertIsNone(self.requests[1][1])
        self.assertTrue(any('校验' in e.get('reason','') for e in self.events))

    def test_unknown_total_is_never_fabricated_during_transfer(self):
        self.download(['/unknown'])
        updates=[e for e in self.events if e['kind']=='progress']
        self.assertTrue(any(e['total'] is None for e in updates));self.assertEqual(updates[-1]['total'],len(self.payload))

    def test_slow_source_switches_and_keeps_partial_bytes(self):
        self.payload=self.payload[:4096]
        self.download(['/slow','/good'],slow_after=.18,min_speed=2048,timeout=2)
        self.assertTrue(self.requests[1][1].startswith('bytes='))
        self.assertTrue(any('过慢' in e.get('reason','') for e in self.events))

    def test_downloaded_file_is_verified_before_cache_reuse(self):
        target=self.download(['/good']);self.requests.clear();self.events.clear()
        self.download(['/good']);self.assertEqual(self.requests,[]);self.assertEqual(self.events[0]['kind'],'cached')
        target.write_bytes(b'broken');self.download(['/good']);self.assertTrue(self.requests)

    def test_live_pip_output_reaches_progress_without_waiting_for_process_exit(self):
        command=[sys.executable,'-u','-c',"import time;print('Downloading torch.whl',flush=True);print('Progress 32 of 64',end='\\r',flush=True);time.sleep(.1);print('Progress 64 of 64',flush=True)"]
        result=progress.run_logged(command,self.root/'pip.log',timeout=5,emit=self.emit)
        self.assertEqual(result.returncode,0)
        self.assertTrue(any(e.get('file')=='torch.whl' for e in self.events))
        self.assertEqual([e['received'] for e in self.events if e['kind']=='progress'],[32,64])

    def test_source_and_metrics_are_visible_without_reading_log(self):
        state=progress.ProgressState();state.apply({'kind':'phase','index':3,'steps':6,'name':'安装依赖'})
        state.apply({'kind':'source','source':'清华镜像','attempt':1,'attempts':3,'file':'torch.whl'})
        state.apply({'kind':'source','source':'华为镜像','attempt':2,'attempts':3,'file':'torch.whl','previous':'清华镜像','reason':'HTTPS 连接中断'})
        state.apply({'kind':'progress','received':5*1024**2,'total':10*1024**2,'speed':1024**2,'eta':5})
        shown=state.display();self.assertIn('华为',shown['source']);self.assertIn('2/3',shown['source'])
        self.assertIn('清华镜像 → 华为镜像',shown['switch']);self.assertIn('HTTPS',shown['switch'])
        self.assertIn('50.0%',shown['bytes']);self.assertIn('MB/s',shown['speed']);self.assertIn('5 秒',shown['eta'])
        state.apply({'kind':'activity','message':'正在安装已下载依赖'});self.assertEqual(state.display()['speed'],'当前未在传输')

    def test_tqdm_model_bytes_and_speed_are_parsed(self):
        event=progress.line_progress('Downloading [model.pt]: 50%|#####| 450M/900M [00:10<00:10,45.0MB/s]')
        self.assertEqual(event['file'],'model.pt');self.assertEqual(event['received']/event['total'],.5);self.assertGreater(event['speed'],0)

    def test_model_iteration_counter_is_not_displayed_as_downloaded_bytes(self):
        self.assertIsNone(progress.line_progress('100%|████████| 1/1 [00:00<00:00, 3.50it/s]'))

    def test_offline_extraction_reuses_good_files_and_preserves_unknown_user_files(self):
        archive=self.root/'offline.zip';target=self.root/'resources'
        with zipfile.ZipFile(archive,'w') as zipped:zipped.writestr('Models/first.bin',b'weights');zipped.writestr('Engine/config.json','{}')
        offline.extract_resources(archive,target,self.emit)
        (target/'personal-note.txt').write_text('keep');(target/'Engine/config.json').write_text('broken')
        result=offline.extract_resources(archive,target,self.emit)
        self.assertEqual(result['reused_files'],1);self.assertEqual((target/'Engine/config.json').read_text(),'{}')
        self.assertEqual((target/'personal-note.txt').read_text(),'keep')

    def test_offline_archive_cannot_escape_or_overwrite_profile(self):
        archive=self.root/'evil.zip';outside=self.root/'api-key.txt';outside.write_text('private-fixture')
        with zipfile.ZipFile(archive,'w') as zipped:zipped.writestr('../api-key.txt','replacement')
        with self.assertRaises(ValueError):offline.extract_resources(archive,self.root/'resources',self.emit)
        self.assertEqual(outside.read_text(),'private-fixture')

    def test_duplicate_case_paths_are_rejected_before_extraction(self):
        archive=self.root/'duplicate.zip'
        with zipfile.ZipFile(archive,'w') as zipped:zipped.writestr('Models/weight.bin','a');zipped.writestr('models/weight.bin','b')
        with self.assertRaises(ValueError):offline.extract_resources(archive,self.root/'resources',self.emit)

    def test_nonempty_unmanaged_directory_is_not_modified(self):
        target=self.root/'personal';target.mkdir();(target/'Key.txt').write_text('keep')
        archive=self.root/'offline.zip'
        with zipfile.ZipFile(archive,'w') as zipped:zipped.writestr('Models/weight.bin','a')
        with self.assertRaises(ValueError):offline.extract_resources(archive,target,self.emit)
        self.assertEqual(list(target.iterdir()),[target/'Key.txt'])

    def test_resource_registration_preserves_keys_and_previous_pointer(self):
        profile=self.root/'profile';profile.mkdir();(profile/'providers.json').write_text('key-fixture')
        old={'format':'contenthub/director-runtime/v1','root':str(self.root/'old-models')}
        (profile/'director-runtime.json').write_text(json.dumps(old))
        offline.register(profile,self.root/'new-models')
        self.assertEqual((profile/'providers.json').read_text(),'key-fixture')
        backups=list(profile.glob('director-runtime-before-offline-*.json'));self.assertEqual(len(backups),1)
        self.assertEqual(json.loads(backups[0].read_text()),old)


if __name__=='__main__':unittest.main(verbosity=2)
