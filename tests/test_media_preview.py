import copy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
import wave

_state=tempfile.TemporaryDirectory(prefix='preview-app-tests-')
if 'client.app' not in sys.modules:os.environ['COPY_STUDIO_DATA']=_state.name
from client import app as studio
from fastapi.testclient import TestClient


class ReferencePreview(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(studio.app,base_url=studio.ORIGIN);self.client.get('/')
        item=studio.new_job('预览测试','upload','')
        self.id=item['id'];self.folder=studio.directory(self.id);self.media=self.folder/'source.wav'
        with wave.open(str(self.media),'wb') as file:
            file.setnchannels(1);file.setsampwidth(2);file.setframerate(16000)
            file.writeframes(b''.join(struct.pack('<h',int(4000*math.sin(2*math.pi*500*i/16000))) for i in range(32000)))
        studio.update(self.id,status='done',input_file='source.wav',raw='这是一段口播。',corrected='这是一段口播。',
                      structure=[{'id':1,'role':'开场','text':'这是一段口播。'}])

    def test_preview_uses_measured_timestamps_without_starting_models(self):
        studio.update(self.id,asr_timed=True)
        (self.folder/'asr.json').write_text(json.dumps({'segments':[{'text':'这是一段口播。','start_time':.1,'end_time':1.8}]}),encoding='utf-8')
        before=copy.deepcopy(studio.get_job(self.id))
        probe=Mock(returncode=0,stdout='{"streams":[{"codec_type":"audio"}],"format":{"duration":"2"}}')
        with patch.object(studio.subprocess,'run',return_value=probe),patch.object(studio,'run_process') as models:
            response=self.client.get(f'/api/jobs/{self.id}/reference/info')
        self.assertEqual(response.status_code,200);info=response.json()
        self.assertFalse(info['has_video']);self.assertTrue(info['has_audio'])
        self.assertEqual(info['corrected_segments'][0]['start'],.1)
        self.assertEqual(info['raw_segments'][0]['end'],1.8)
        models.assert_not_called();self.assertEqual(studio.get_job(self.id),before)

    def test_untimed_asr_is_not_presented_as_real_alignment(self):
        (self.folder/'asr.json').write_text(json.dumps({'segments':[{'text':'估计整段','start_time':0,'end_time':2}]}),encoding='utf-8')
        self.assertEqual(studio.cached_speech_rows(studio.get_job(self.id),self.media),[])

    def test_real_audio_preview_range_cache_and_original_integrity(self):
        if not Path(studio.FFMPEG).exists():self.skipTest('FFmpeg unavailable')
        before=hashlib.sha256(self.media.read_bytes()).hexdigest();snapshot=copy.deepcopy(studio.get_job(self.id))
        info=self.client.get(f'/api/jobs/{self.id}/reference/info').json()
        self.assertTrue(info['has_audio']);self.assertFalse(info['has_video']);self.assertAlmostEqual(info['duration'],2,places=1)
        url=f'/api/jobs/{self.id}/reference/audio'
        response=self.client.get(url,headers={'Range':'bytes=0-63'})
        self.assertEqual(response.status_code,206);self.assertEqual(len(response.content),64)
        self.assertTrue(response.headers['content-type'].startswith('audio/mpeg'))
        cached=list(self.folder.glob('preview-audio-*.mp3'));self.assertEqual(len(cached),1)
        stamp=cached[0].stat().st_mtime_ns
        self.assertEqual(self.client.get(url,headers={'Range':'bytes=-32'}).status_code,206)
        self.assertEqual(cached[0].stat().st_mtime_ns,stamp)
        self.assertEqual(hashlib.sha256(self.media.read_bytes()).hexdigest(),before)
        self.assertEqual(studio.get_job(self.id),snapshot)


if __name__=='__main__':unittest.main()
