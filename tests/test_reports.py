import copy
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from client import reports as r
from client.evidence import segment_times, timeline, screen_groups


class ReportValidation(unittest.TestCase):
    def setUp(self):
        self.segments=[{'id':1,'role':'钩子','text':'这款清禾香薰。','start':0.,'end':2.},
                       {'id':2,'role':'卖点','text':'茶香很清新。','start':2.,'end':4.}]
        self.item={'title':'测试参考','corrected':'这款清禾香薰。茶香很清新。','duration':4}
        self.evidence={'frames':[{'id':1,'time':.2,'file':'000.jpg','ocr':[{'text':'茶香','confidence':.9}]}],
                       'limitations':['OCR 为抽样']}

    def test_score_requires_all_six_and_real_quotes(self):
        good=r.Quality(scores=[{'dimension':d,'score':7.5,'quote':'茶香','reason':'可理解'} for d in r.DIMENSIONS],suggestions=[])
        r.quality_valid(good,self.item['corrected']);self.assertEqual(r.score_result(good)['grade'],'A')
        bad=copy.deepcopy(good);bad.scores[0].quote='免费包邮'
        with self.assertRaises(ValueError):r.quality_valid(bad,self.item['corrected'])
        bad=copy.deepcopy(good);bad.scores[0].dimension=bad.scores[1].dimension
        with self.assertRaises(ValueError):r.quality_valid(bad,self.item['corrected'])

    def test_source_coverage_cannot_drop_reorder_or_duplicate(self):
        for ids in ([1],[2,1],[1,1,2],[1,2,3]):
            with self.assertRaises(ValueError):r.source_ids(ids,self.segments,True)

    def test_timestamps_map_from_audio_instead_of_inventing(self):
        rows=[{'start':1,'end':3,'text':'这款清和香薰。'},{'start':4,'end':6,'text':'茶香很清新。'}]
        mapped=segment_times(self.segments,rows,self.item['corrected'])
        self.assertEqual([(x['start'],x['end']) for x in mapped],[(1,3),(4,6)])
        unmapped=segment_times([{'id':1,'role':'x','text':'全新写的段落'}],rows,'全新写的段落')
        self.assertIsNone(unmapped[0]['start'])
        self.assertEqual(timeline({'segments':[{'start_time':1,'end_time':0,'text':'bad'}]}),[])

    def test_screen_text_deduplicates_first_timestamp(self):
        frames=self.evidence['frames']+[{**self.evidence['frames'][0],'time':3}]
        self.assertEqual(len(screen_groups(frames)),1)
        self.assertEqual(screen_groups(frames)[0]['time'],.2)

    def test_transcript_and_summary_validation_and_markdown(self):
        clean=r.CleanReport(overview='介绍香薰',paragraphs=[{'title':'产品','source_ids':[1,2],
            'clean_text':self.item['corrected'],'spoken_highlight':'清禾香薰','clean_highlight':'茶香'}])
        client=Mock()
        def call(task,ctx,schema,validator):return validator(clean)
        client.call.side_effect=call
        result=r.generate_report(client,'transcript',self.item,self.evidence,self.segments)
        md=r.markdown('transcript',result,self.item,self.evidence,self.segments)
        for title in ('口播全文','净稿','画面文字稿','时间线合并稿','**茶香**'):self.assertIn(title,md)
        clean.paragraphs[0].source_ids=[2]
        with self.assertRaises(ValueError):r.generate_report(client,'transcript',self.item,self.evidence,self.segments)

    def test_tts_cannot_silently_change_words(self):
        client=Mock()
        def call(task,ctx,schema,validator):
            return validator(r.Prompts(style_prompt='建议自然光',shots=[{'segment_id':s['id'],'prompt':'p','motion':'建议固定','tool_tips':'t'} for s in self.segments],
              narration='茶香 / **销量第一**',adaptation_notes=[]))
        client.call.side_effect=call
        with self.assertRaises(ValueError):r.generate_report(client,'prompts',self.item,self.evidence,self.segments)

    def test_low_score_rewrites_once_and_keeps_second_assessment(self):
        variant={'title':'脚本','segments':self.segments};client=Mock();client.generate.return_value={'variants':[variant]}
        low={'scores':[{'dimension':d,'score':6,'quote':'茶香','reason':'弱'} for d in r.DIMENSIONS],
             'suggestions':['提升钩子'],'average':6,'grade':'B','needs_revision':True}
        with patch.object(r,'assess',return_value=low) as assess:
            result=r.enrich_variant(client,variant,self.segments,'same','茶香','',60)
        self.assertEqual(client.generate.call_count,1);self.assertEqual(assess.call_count,2)
        self.assertTrue(result['revision']['performed']);self.assertTrue(result['quality']['needs_revision'])
        self.assertEqual([x['id'] for x in result['production_segments']],[1,2])

    def test_report_worker_keeps_completed_scene_when_later_scene_fails(self):
        # Import the already isolated app used by the API test suite.
        import os, tempfile, sys
        temp=tempfile.TemporaryDirectory()
        if 'client.app' not in sys.modules:os.environ['COPY_STUDIO_DATA']=temp.name
        from client import app
        job=app.new_job('场景保存测试','upload','')
        app.update(job['id'],corrected=self.item['corrected'],structure=self.segments,status='done',input_file='test.mp4')
        client=Mock();client.provider_name='测试';client.model='test'
        result={'thesis':'测试'}
        with patch.object(app,'prepare_evidence',return_value={'speech_timeline':[]}),\
             patch.object(r,'generate_report',side_effect=[result,RuntimeError('测试第二类失败')]),\
             patch.object(r,'markdown',return_value='报告一'):
            app.report_work(job['id'],{'visual_mode':'local','scene':'all'},client)
        saved=app.get_job(job['id'])
        self.assertEqual(saved['status'],'error');self.assertEqual(saved['reports']['transcript']['markdown'],'报告一')
        self.assertNotIn('summary',saved['reports']);self.assertEqual(saved['corrected'],self.item['corrected'])

    def test_revision_failure_preserves_initial_valid_score_and_script(self):
        variant={'title':'脚本','segments':self.segments};client=Mock();client.generate.side_effect=RuntimeError('临时不可用')
        q={'scores':[{'dimension':d,'score':6,'quote':'茶香','reason':'弱'} for d in r.DIMENSIONS],
           'suggestions':['提升钩子'],'average':6,'grade':'B','needs_revision':True}
        with patch.object(r,'assess',return_value=q):result=r.enrich_variant(client,variant,self.segments,'same','茶香','',60)
        self.assertEqual(result['quality'],q);self.assertEqual(result['segments'],variant['segments'])
        self.assertFalse(result['revision']['performed']);self.assertIn('保留',result['revision_error'])


if __name__=='__main__':unittest.main()
