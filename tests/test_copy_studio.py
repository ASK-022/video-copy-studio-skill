import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import httpx

_data=tempfile.TemporaryDirectory(prefix='copy-studio-test-')
os.environ['COPY_STUDIO_DATA']=_data.name
from client import app as studio
from client.ai import (AIClient, CorrectionPlan, Structure, Drafts, apply_corrections,
                       validate_structure, validate_drafts, ProductProfile, validate_product, product_facts_text)
from client.media import extract_url, safe_url
from client.security import seal, unseal
from fastapi.testclient import TestClient


class OutputValidation(unittest.TestCase):
    def test_product_extraction_keeps_unverified_claims_out_of_autofill(self):
        text='清禾桌面香薰是茶香，可用半年。'
        profile=ProductProfile(product={'value':'清禾桌面香薰','source_excerpt':'清禾桌面香薰'},
             selling_points=[{'value':'茶香','source_excerpt':'茶香'}],
             needs_confirmation=[{'value':'可用半年','source_excerpt':'可用半年'}])
        validate_product(profile,text,'')
        summary=product_facts_text(profile.model_dump())
        self.assertIn('清禾桌面香薰',summary);self.assertIn('茶香',summary)
        self.assertNotIn('半年',summary)
        profile.selling_points[0].source_excerpt='纯天然精油'
        with self.assertRaises(ValueError):validate_product(profile,text,'')

    def test_non_product_video_can_return_empty_profile(self):
        profile=ProductProfile(product=None,selling_points=[],needs_confirmation=[])
        validate_product(profile,'今天讲一个历史故事','')
        self.assertEqual(product_facts_text(profile.model_dump()),'')

    def test_correction_is_a_local_edit_and_preserves_other_text(self):
        text='这是科厅味。别错过，真的太香了。'
        plan=CorrectionPlan(corrections=[{'original':'科厅味','replacement':'科净威','reason':'已确认商品名'}],uncertainties=[])
        self.assertEqual(apply_corrections(text,plan),'这是科净威。别错过，真的太香了。')

    def test_ambiguous_or_overlapping_edits_rejected(self):
        with self.assertRaises(ValueError):
            apply_corrections('香香',CorrectionPlan(corrections=[{'original':'香','replacement':'想','reason':'错字'}],uncertainties=[]))
        with self.assertRaises(ValueError):
            apply_corrections('这味道太差了',CorrectionPlan(corrections=[
                {'original':'这味道太差了','replacement':'这味道太香了','reason':'纠错'},
                {'original':'太差了','replacement':'太香了','reason':'纠错'}],uncertainties=[]))

    def test_structure_must_cover_exact_original_in_order(self):
        good=Structure(segments=[{'id':1,'role':'钩子','text':'你好！'},{'id':2,'role':'卖点','text':'很清新。'}])
        validate_structure('你好！\n很清新。',good)
        for text in ('你好！很清新。再买一件。','很清新。你好！','你好！很清新'):
            with self.assertRaises(ValueError):validate_structure(text,good)

    def test_generation_keeps_count_roles_and_order(self):
        reference=[{'id':1,'role':'钩子','text':'原文1'},{'id':2,'role':'卖点','text':'原文2'}]
        good=Drafts(variants=[{'title':'版本1','segments':[
            {'id':1,'role':'钩子','text':'新钩子'},{'id':2,'role':'卖点','text':'新卖点'}]}])
        validate_drafts(reference,good,1)
        with self.assertRaises(ValueError):validate_drafts(reference,good,2)
        good.variants[0].segments.reverse()
        with self.assertRaises(ValueError):validate_drafts(reference,good,1)

    def test_invalid_model_json_retried_once(self):
        calls=[]
        def reply(request):
            calls.append(json.loads(request.content))
            content='not json' if len(calls)==1 else '{"segments":[{"id":1,"role":"钩子","text":"你好"}]}'
            return httpx.Response(200,json={'choices':[{'message':{'content':content},'finish_reason':'stop'}]})
        original=httpx.Client
        transport=httpx.MockTransport(reply)
        with patch('client.ai.httpx.Client',side_effect=lambda **kw:original(transport=transport,**kw)):
            result=AIClient('https://api.deepseek.com','test','dummy').analyze('你好')
        self.assertEqual(result[0]['text'],'你好');self.assertEqual(len(calls),2)

    def test_editorial_notes_not_allowed_in_spoken_copy(self):
        drafts=Drafts(variants=[{'title':'测试','segments':[{'id':1,'role':'卖点','text':'资料没写，我不替它说。'}]}])
        with self.assertRaises(ValueError):
            validate_drafts([{'id':1,'role':'卖点','text':'参考'}],drafts,1)

    def test_auth_error_not_retried_and_key_not_in_error(self):
        calls=[]
        def reply(request):
            calls.append(request)
            return httpx.Response(401,text='dummy-secret-key')
        original=httpx.Client
        with patch('client.ai.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(reply),**kw)):
            with self.assertRaises(RuntimeError) as error:
                AIClient('https://api.deepseek.com','test','dummy-secret-key').analyze('你好')
        self.assertNotIn('dummy-secret-key',str(error.exception));self.assertEqual(len(calls),1)

    def test_share_text_and_private_links(self):
        self.assertEqual(extract_url('复制打开看看 https://v.douyin.com/abc/ ：测试'),'https://v.douyin.com/abc/')
        with self.assertRaises(ValueError):safe_url('http://127.0.0.1:22/')
        with self.assertRaises(ValueError):safe_url('file:///C:/Windows')


class LocalAPI(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(studio.app,base_url=studio.ORIGIN)
        self.client.get('/')
        self.headers={'X-Studio-Request':'1'}
        for item in studio.JOBS.values():item['pinned']=False

    def make_job(self):
        item=studio.new_job('测试参考','upload','测试商品')
        studio.update(item['id'],status='done',raw='你好',corrected='你好',structure=[{'id':1,'role':'钩子','text':'你好'}])
        return item['id']

    def test_local_session_and_csrf(self):
        other=TestClient(studio.app,base_url=studio.ORIGIN)
        self.assertEqual(other.get('/api/settings').status_code,403)
        self.assertEqual(self.client.post('/api/settings/test').status_code,403)
        self.assertEqual(self.client.post('/api/settings/test',headers={**self.headers,'Origin':'https://untrusted.example'}).status_code,403)

    def test_key_is_encrypted_and_never_returned(self):
        key='unit-test-secret-not-real'
        response=self.client.put('/api/settings',headers=self.headers,json={
            'base_url':'https://api.deepseek.com','model':'deepseek-flash','key':key})
        self.assertEqual(response.status_code,200)
        config=(studio.STATE/'ai.json').read_text()
        self.assertNotIn(key,config)
        self.assertEqual(unseal(json.loads(config)['encrypted_key']),key)
        self.assertNotIn(key,self.client.get('/api/settings').text)
        self.assertNotIn('encrypted_key',self.client.get('/api/settings').text)
        # Switching destination must not silently send an existing key there.
        result=self.client.put('/api/settings',headers=self.headers,json={'base_url':'https://other.example','model':'test'})
        self.assertEqual(result.status_code,400)

    def test_edited_reference_requires_reanalysis(self):
        job=self.make_job()
        response=self.client.post('/api/jobs/'+job+'/drafts/generate',headers=self.headers,json={
            'mode':'same','facts':'测试商品','count':1,'reference_text':'我修改了文案'})
        self.assertEqual(response.status_code,409)

    def test_busy_job_does_not_start_a_second_operation(self):
        job=self.make_job();studio.update(job,status='working')
        response=self.client.post('/api/jobs/'+job+'/analyze',headers=self.headers,json={'text':'你好'})
        self.assertEqual(response.status_code,409)

    def test_failed_generation_preserves_previous_results(self):
        job=self.make_job()
        studio.update(job,batches=[{'id':'existing','variants':[]}],status='working')
        client=Mock();client.generate.side_effect=RuntimeError('模拟连接失败')
        studio.ai_work(job,'generate',{'mode':'same','facts':'测试商品','count':1,'direction':''},client)
        self.assertEqual(studio.get_job(job)['status'],'error')
        self.assertEqual(studio.get_job(job)['batches'][0]['id'],'existing')

    def test_analysis_automatically_extracts_product(self):
        job=self.make_job();client=Mock()
        client.analyze.return_value=[{'id':1,'role':'钩子','text':'你好'}]
        client.extract_product.return_value={'product':{'value':'测试商品','source_excerpt':'测试商品'},
                  'selling_points':[{'value':'茶香','source_excerpt':'茶香'}],'needs_confirmation':[]}
        studio.ai_work(job,'analyze',{'text':'你好','facts':'测试商品，茶香'},client)
        item=studio.get_job(job)
        client.extract_product.assert_called_once_with('你好','测试商品，茶香')
        self.assertIn('茶香',item['product_facts']);self.assertEqual(item['status'],'done')

    def test_product_extraction_failure_keeps_structure(self):
        job=self.make_job();client=Mock();client.extract_product.side_effect=RuntimeError('模拟失败')
        studio.ai_work(job,'extract-product',{'text':'你好','facts':''},client)
        self.assertEqual(len(studio.get_job(job)['structure']),1)
        self.assertTrue(studio.get_job(job)['product_warning'])

    def test_custom_count_above_five_accepted(self):
        job=self.make_job()
        with patch.object(studio,'ai_client',return_value=Mock()),patch.object(studio.AI_POOL,'submit'):
            response=self.client.post('/api/jobs/'+job+'/drafts/generate',headers=self.headers,json={
                'mode':'same','facts':'测试商品','count':50,'reference_text':'你好'})
        self.assertEqual(response.status_code,202)
        self.assertEqual(studio.get_job(job)['generation_progress']['total'],50)
        for invalid in (0,-1,1.5,True):
            studio.update(job,status='done')
            response=self.client.post('/api/jobs/'+job+'/drafts/generate',headers=self.headers,json={
                'mode':'same','facts':'测试商品','count':invalid,'reference_text':'你好'})
            self.assertEqual(response.status_code,422)
        studio.CANCEL_EVENTS.pop(job,None)

    @staticmethod
    def fake_drafts(reference,mode,facts,count,direction):
        return {'variants':[{'title':f'版本{i+1}','segments':reference} for i in range(count)],'review_notes':[]}

    def test_seven_variants_are_generated_in_bounded_batches(self):
        job=self.make_job();client=Mock();client.generate.side_effect=self.fake_drafts
        studio.ai_work(job,'generate',{'mode':'same','facts':'测试商品','count':7,'direction':''},client)
        item=studio.get_job(job)
        self.assertEqual([call.args[3] for call in client.generate.call_args_list],[2,2,2,1])
        self.assertEqual(len(item['batches'][-1]['variants']),7)
        self.assertTrue(item['batches'][-1]['complete'])
        self.assertEqual(item['generation_progress'],{'completed':7,'total':7,'batch_id':item['batches'][-1]['id']})

    def test_stop_keeps_completed_variants(self):
        import threading
        job=self.make_job();client=Mock();event=threading.Event();studio.CANCEL_EVENTS[job]=event
        def reply(*args):
            event.set()
            return self.fake_drafts(*args)
        client.generate.side_effect=reply
        studio.ai_work(job,'generate',{'mode':'same','facts':'测试商品','count':10,'direction':''},client)
        item=studio.get_job(job)
        self.assertEqual(client.generate.call_count,1)
        self.assertEqual(len(item['batches'][-1]['variants']),2)
        self.assertFalse(item['batches'][-1]['complete'])
        self.assertIn('已停止',item['message'])

    def test_later_batch_failure_keeps_completed_work(self):
        job=self.make_job();client=Mock()
        client.generate.side_effect=[self.fake_drafts(studio.get_job(job)['structure'],None,None,2,None),RuntimeError('模拟失败')]
        studio.ai_work(job,'generate',{'mode':'same','facts':'测试商品','count':7,'direction':''},client)
        item=studio.get_job(job)
        self.assertEqual(item['status'],'error');self.assertEqual(len(item['batches'][-1]['variants']),2)

    def test_pin_limit_order_and_unpin(self):
        ids=[self.make_job() for _ in range(4)]
        for job in ids[:3]:
            self.assertEqual(self.client.post('/api/jobs/'+job+'/history/pin',headers=self.headers,json={'pinned':True}).status_code,200)
        response=self.client.post('/api/jobs/'+ids[3]+'/history/pin',headers=self.headers,json={'pinned':True})
        self.assertEqual(response.status_code,409)
        listed=self.client.get('/api/jobs').json()
        self.assertEqual({j['id'] for j in listed[:3]},set(ids[:3]))
        self.assertEqual(self.client.post('/api/jobs/'+ids[0]+'/history/pin',headers=self.headers,json={'pinned':True}).status_code,200)
        self.client.post('/api/jobs/'+ids[0]+'/history/pin',headers=self.headers,json={'pinned':False})
        self.assertEqual(self.client.post('/api/jobs/'+ids[3]+'/history/pin',headers=self.headers,json={'pinned':True}).status_code,200)

    def test_single_delete_recoverable_and_unpins(self):
        job=self.make_job();marker=studio.directory(job)/'original-test-media.txt';marker.write_text('keep')
        self.client.post('/api/jobs/'+job+'/history/pin',headers=self.headers,json={'pinned':True})
        response=self.client.delete('/api/jobs/'+job,headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertTrue(response.json()['recoverable'])
        self.assertTrue(marker.exists());self.assertFalse(studio.get_job(job)['pinned'])
        self.assertNotIn(job,[x['id'] for x in self.client.get('/api/jobs').json()])
        self.assertIn(job,[x['id'] for x in self.client.get('/api/jobs?trash=true').json()])
        self.assertEqual(self.client.get('/api/jobs/'+job).status_code,404)
        self.client.post('/api/jobs/'+job+'/history/restore',headers=self.headers)
        self.assertEqual(self.client.get('/api/jobs/'+job).status_code,200)
        self.assertTrue(marker.exists())

    def test_busy_reference_cannot_be_deleted(self):
        job=self.make_job();studio.update(job,status='working')
        self.assertEqual(self.client.delete('/api/jobs/'+job,headers=self.headers).status_code,409)

    def test_saved_source_retry_uses_its_own_options(self):
        job=self.make_job();studio.update(job,input_file='source.mp4',auto_ai=True)
        with patch.object(studio.ASR_POOL,'submit'):
            response=self.client.post('/api/jobs/'+job+'/retry',headers=self.headers,json={'facts':'独立备注','auto_ai':False,'provider':'local'})
        self.assertEqual(response.status_code,202)
        item=studio.get_job(job)
        self.assertEqual(item['input_file'],'source.mp4');self.assertEqual(item['facts'],'独立备注');self.assertFalse(item['auto_ai'])

    def test_tikhub_key_is_separate_and_encrypted(self):
        from client.tikhub import config_path
        key='tikhub-test-dummy-key'
        response=self.client.put('/api/tikhub/settings',headers=self.headers,json={'key':key})
        self.assertEqual(response.status_code,200)
        self.assertNotIn(key,config_path(studio.STATE).read_text())
        self.assertNotIn(key,self.client.get('/api/tikhub/settings').text)
        self.client.put('/api/tikhub/settings',headers=self.headers,json={'clear_key':True})
        response=self.client.post('/api/tikhub/test',headers=self.headers,json={'url':'https://v.douyin.com/test/'})
        self.assertEqual(response.status_code,400)

    def test_default_provider_requires_key_and_does_not_change_existing_project(self):
        job=self.make_job()
        self.client.put('/api/tikhub/settings',headers=self.headers,json={'clear_key':True})
        response=self.client.put('/api/preferences',headers=self.headers,json={'default_link_provider':'tikhub'})
        self.assertEqual(response.status_code,400)
        self.client.put('/api/tikhub/settings',headers=self.headers,json={'key':'dummy-tikhub-key'})
        response=self.client.put('/api/preferences',headers=self.headers,json={'default_link_provider':'tikhub'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/api/preferences').json()['default_link_provider'],'tikhub')
        self.assertEqual(studio.get_job(job)['link_provider'],'local')
        self.client.put('/api/tikhub/settings',headers=self.headers,json={'clear_key':True})
        self.assertEqual(self.client.get('/api/preferences').json()['default_link_provider'],'local')


class TikHubResolver(unittest.TestCase):
    def test_video_and_nested_metadata_response(self):
        from client.tikhub import video_candidates
        item={'aweme_id':'123','desc':'test','video':{'play_addr':{'url_list':['https://media.example/video.mp4']}}}
        for data in (item,{'aweme_detail':item},{'item_list':[item]}):
            result=video_candidates({'data':data})
            self.assertEqual(result['video_id'],'123');self.assertEqual(len(result['urls']),1)
        with self.assertRaises(ValueError):video_candidates({'data':{'music':{'play_url':'https://music.example/a.mp3'}}})

    def test_tikhub_uses_exact_fixed_endpoint_and_masks_errors(self):
        from client.tikhub import TikHubClient,ENDPOINT
        requests=[]
        def handler(request):
            requests.append(request)
            return httpx.Response(401,text='dummy-tikhub-secret')
        original=httpx.Client
        with patch('client.tikhub.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            with self.assertRaises(ValueError) as error:TikHubClient('dummy-tikhub-secret').resolve('https://v.douyin.com/test/')
        self.assertNotIn('dummy-tikhub-secret',str(error.exception))
        self.assertEqual(str(requests[0].url).split('?')[0],ENDPOINT)
        self.assertEqual(requests[0].headers['authorization'],'Bearer dummy-tikhub-secret')
        with self.assertRaises(ValueError):TikHubClient('dummy').resolve('https://private.example/video')


if __name__=='__main__':
    unittest.main()
