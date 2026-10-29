import copy
from dataclasses import asdict
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

from client import markers
_state=tempfile.TemporaryDirectory(prefix='marker-app-tests-')
if 'client.app' not in sys.modules:os.environ['COPY_STUDIO_DATA']=_state.name
from client import app as studio
from fastapi.testclient import TestClient


class LocalMarkerAlgorithms(unittest.TestCase):
    def test_real_media_known_silence_and_two_hard_cuts(self):
        if not Path(studio.FFMPEG).exists():self.skipTest('FFmpeg unavailable')
        with tempfile.TemporaryDirectory() as temp:
            media=Path(temp)/'fixture.mp4'
            command=[studio.FFMPEG,'-v','error','-y']
            for color in ('red','blue','green'):command+=['-f','lavfi','-i',f'color=c={color}:s=320x180:r=12:d=1']
            for audio in ('sine=frequency=600:sample_rate=16000:duration=1','anullsrc=r=16000:cl=mono:d=1','sine=frequency=900:sample_rate=16000:duration=1'):
                command+=['-f','lavfi','-i',audio]
            command+=['-filter_complex','[0:v][3:a][1:v][4:a][2:v][5:a]concat=n=3:v=1:a=1[v][a]',
                      '-map','[v]','-map','[a]','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(media)]
            made=subprocess.run(command,capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(made.returncode,0,made.stderr.decode(errors='replace'))
            original=media.read_bytes();silences=markers.detect_silences(media,studio.FFMPEG,3,markers.Options())
            self.assertEqual(len(silences),1)
            self.assertAlmostEqual(silences[0]['start'],1,delta=.05);self.assertAlmostEqual(silences[0]['end'],2,delta=.05)
            cuts=markers.detect_cuts(media,markers.Options(),lambda _:None)
            self.assertEqual(len(cuts),2);self.assertAlmostEqual(cuts[0]['start'],1,delta=.1);self.assertAlmostEqual(cuts[1]['start'],2,delta=.1)
            self.assertEqual(media.read_bytes(),original)

    def test_silence_threshold_duration_and_unclosed_tail(self):
        log='silence_start: -0.02\nsilence_end: 0.1\nsilence_start: 1.5\nsilence_end: 2.3\nsilence_start: 4.1'
        result=markers.parse_silences(log,5,.6)
        self.assertEqual([(s['start'],s['end']) for s in result],[(1.5,2.3),(4.1,5)])
        self.assertTrue(all(s['kind']=='silence' and '保留' in s['suggestion'] for s in result))

    def test_repeated_speech_matches_separate_spans_without_editing(self):
        rows=[{'start':0,'end':2,'text':'打开车门的一瞬间，仿佛来到了一片花海。'},
              {'start':3,'end':5,'text':'今天我们来讲一个完全不同的话题。'},
              {'start':8,'end':10,'text':'打开车门的一瞬间，仿佛来到一片花海！'}]
        before=copy.deepcopy(rows);result,limited=markers.detect_repeats(rows,88)
        self.assertFalse(limited);self.assertTrue(result);self.assertEqual(rows,before)
        self.assertTrue(all(r['original']['end']<r['repeated']['start'] for r in result))
        self.assertGreaterEqual(result[0]['similarity'],88)
        self.assertIn('强调',result[0]['reason'])

    def test_short_filler_and_overlapping_windows_not_flagged(self):
        rows=[{'start':0,'end':1,'text':'好好好。'},{'start':1,'end':2,'text':'好好好。'}]
        self.assertEqual(markers.detect_repeats(rows)[0],[])
        self.assertEqual(markers.detect_repeats([{'start':0,'end':3,'text':'这是一句话只说一次，没有重复。'}])[0],[])

    def test_cache_and_partial_failure_are_distinguished(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);media=folder/'source.wav';media.write_bytes(b'unchanged')
            with patch.object(markers,'detect_silences',return_value=[]),patch.object(markers,'detect_repeats',return_value=([],False)),patch.object(markers,'detect_cuts',side_effect=RuntimeError('failed')):
                result=markers.analyze(media,folder,'ffmpeg',3,[{'start':0,'end':2,'text':'文本'}],True,markers.Options())
            self.assertEqual(result['statuses'],{'silences':'done','repeats':'done','cuts':'error'})
            self.assertEqual(list(folder.glob('markers-*.json')),[])
            with patch.object(markers,'detect_silences',return_value=[]) as detect:
                markers.analyze(media,folder,'ffmpeg',3,[],False,markers.Options())
                markers.analyze(media,folder,'ffmpeg',3,[],False,markers.Options())
            # Missing timestamps are an explicit error, so this result also cannot be cached.
            self.assertEqual(detect.call_count,2)
            self.assertEqual(media.read_bytes(),b'unchanged')


class MarkerAPI(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(studio.app,base_url=studio.ORIGIN);self.client.get('/')
        self.headers={'X-Studio-Request':'1'}
        item=studio.new_job('检测测试','upload','已确认资料');self.id=item['id']
        studio.update(self.id,status='done',raw='原始口播',corrected='校对口播',structure=[{'id':1,'role':'钩子','text':'校对口播'}],
                      batches=[{'id':'existing','mode':'same','variants':[]}],input_file='source.mp4')
        (studio.directory(self.id)/'source.mp4').write_bytes(b'original-file')
        self.result={'source_hash':'known','settings':asdict(markers.Options()),'policy':'mark_only','created':1,
                     'silences':[{'id':'s1','kind':'silence','start':1,'end':2,'duration':1,'reason':'低音量','suggestion':'保留'}],
                     'repeats':[],'cuts':[],'statuses':{'silences':'done','repeats':'done','cuts':'done'},'warnings':[],
                     'limitations':[],'duration':3,'decisions':{}}

    def test_inspection_never_replaces_reference_structure_or_copy(self):
        before=copy.deepcopy(studio.get_job(self.id))
        with (patch.object(studio,'speech_rows',return_value=[]),
              patch.object(studio.subprocess,'run',return_value=Mock(returncode=0,stdout='{"streams":[{"codec_type":"video"}],"format":{"duration":"3"}}')),
              patch.object(markers,'analyze',return_value=copy.deepcopy(self.result))):
            studio.inspect_reference(self.id,{})
        after=studio.get_job(self.id)
        for key in ('raw','corrected','structure','batches','facts','input_file'):self.assertEqual(before[key],after[key])
        self.assertEqual((studio.directory(self.id)/'source.mp4').read_bytes(),b'original-file')

    def test_decisions_export_busy_guard_and_project_isolation(self):
        studio.update(self.id,markers=copy.deepcopy(self.result))
        other=studio.new_job('其他参考','upload','')['id'];studio.update(other,status='done')
        url=f'/api/jobs/{self.id}/markers/s1/decision'
        self.assertEqual(self.client.put(url,headers=self.headers,json={'decision':'keep'}).status_code,200)
        self.assertEqual(studio.get_job(self.id)['markers']['decisions']['s1'],'keep')
        self.assertIsNone(studio.get_job(other)['markers'])
        self.assertEqual(self.client.put(url,headers=self.headers,json={'decision':'delete'}).status_code,422)
        self.assertEqual(self.client.get(f'/api/jobs/{self.id}/markers/export?format=json').json()['policy'],'mark_only')
        studio.update(self.id,status='working')
        self.assertEqual(self.client.post(f'/api/jobs/{self.id}/markers/run',headers=self.headers,json={}).status_code,409)

    def test_start_validation_and_source_media_range(self):
        with patch.object(studio.ASR_POOL,'submit') as submit:
            self.assertEqual(self.client.post(f'/api/jobs/{self.id}/markers/run',headers=self.headers,json={'repeat_similarity':140}).status_code,422)
            self.assertEqual(self.client.post(f'/api/jobs/{self.id}/markers/run',headers=self.headers,json={}).status_code,202)
        self.assertEqual(submit.call_count,1)
        response=self.client.get(f'/api/jobs/{self.id}/reference/media',headers={'Range':'bytes=0-3'})
        self.assertEqual(response.status_code,206);self.assertEqual(response.content,b'orig')


if __name__=='__main__':unittest.main()
