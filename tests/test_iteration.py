import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

_state=tempfile.TemporaryDirectory(prefix='iteration-tests-')
if 'client.app' not in sys.modules:os.environ['COPY_STUDIO_DATA']=_state.name
from fastapi.testclient import TestClient
from client import app as s,manuscripts
from client.editorial import text_review
from client.script_previews import suggest_parts,PreviewStore

REFERENCE=[{'id':1,'role':'开场','text':'出门带水吗？'},{'id':2,'role':'商品介绍','text':'晴禾杯配有杯盖。'}]


class Iteration(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(s.app,base_url=s.ORIGIN);self.client.get('/');self.headers={'X-Studio-Request':'1'}
        self.job=s.new_job('测试参考','script','原参考备注')['id'];s.update(self.job,status='done',corrected='原参考文字',raw='原始正文',structure=copy.deepcopy(REFERENCE))
        self.ai=Mock();self.ai.provider_id='test-provider';self.ai.provider_name='测试服务';self.ai.model='test-model';self.ai.base_url='https://example.com'
        self.ai.extract_product.return_value={'product':None,'selling_points':[],'needs_confirmation':[]}
        self.ai.analyze_script.side_effect=lambda text:[{'id':1,'role':'原文','text':text}]
        self.ai.generate.side_effect=lambda reference,mode,facts,count,direction:{'variants':[{'title':'新稿','segments':[dict(p,text='新表达'+p['text']) for p in reference]} for _ in range(count)],'review_notes':[]}
    def batch(self,count=3,existing=1):
        batch={'id':'batch-'+self.job,'created':1,'mode':'same','facts':'商品：晴禾杯；配有杯盖。','direction':'自然表达','reference':copy.deepcopy(REFERENCE),
            'variants':[{'title':'已有稿','segments':copy.deepcopy(REFERENCE)} for _ in range(existing)],'requested_count':count,'complete':False,
            'focus':{},'quality_check':False,'product_snapshot':{'name':'晴禾杯','version':1},
            'ai_provider':{'id':self.ai.provider_id,'model':self.ai.model,'base_url':self.ai.base_url},'review_notes':[]}
        s.update(self.job,batches=[batch],status='error',error='上轮失败');return batch
    def resume(self,batch):
        with patch.object(s.PROVIDERS,'client',return_value=self.ai),patch.object(s.AI_POOL,'submit',side_effect=lambda fn,*a:fn(*a)):
            return self.client.post(f'/api/jobs/{self.job}/drafts/{batch["id"]}/resume',headers=self.headers)
    def test_resume_appends_only_missing_and_preserves_batch_manuscript_metadata(self):
        b=self.batch();saved=manuscripts.save(s.directory(self.job),s.get_job(self.job),b['id'],0,0,'人工定稿，不能覆盖。')
        b['editorial']={'0':{'status':'adopted','version':1}};s.update(self.job,batches=[b],facts='后来换成了别的商品',corrected='后来修改的参考文字',structure=[{'id':1,'role':'别的结构','text':'不同'}])
        r=self.resume(b);self.assertEqual(r.status_code,202,r.text);value=s.job(self.job);self.assertEqual(value['status'],'done');self.assertEqual(len(value['batches']),1)
        result=value['batches'][0];self.assertEqual(result['id'],b['id']);self.assertEqual(len(result['variants']),3);self.assertEqual(result['variants'][0]['segments'],REFERENCE)
        self.assertEqual(result['variants'][0]['manuscript']['revision'],saved['revision']);self.assertEqual(result['editorial']['0']['status'],'adopted')
        args=self.ai.generate.call_args.args;self.assertEqual(args[0],REFERENCE);self.assertEqual(args[2],b['facts']);self.assertEqual(args[3],2)
        self.assertEqual(self.resume(result).status_code,409)
    def test_failure_before_first_result_persists_resumable_zero_batch(self):
        self.ai.generate.side_effect=ValueError('校验失败')
        with patch.object(s,'ai_client',return_value=self.ai),patch.object(s.AI_POOL,'submit',side_effect=lambda fn,*a:fn(*a)):
            r=self.client.post(f'/api/jobs/{self.job}/drafts/generate',headers=self.headers,json={'mode':'same','facts':'杯子','count':2,'reference_text':'原参考文字','quality_check':False})
        self.assertEqual(r.status_code,202);item=s.get_job(self.job);self.assertEqual(item['status'],'error');self.assertEqual(len(item['batches']),1);self.assertEqual(item['batches'][0]['variants'],[])
    def test_resume_refuses_changed_provider_configuration_and_busy_job(self):
        b=self.batch();self.ai.model='changed';self.assertEqual(self.resume(b).status_code,409)
        s.update(self.job,status='working');self.assertEqual(self.resume(b).status_code,409)
    def test_metadata_versions_and_search_current_saved_manuscript(self):
        b=self.batch();s.update(self.job,status='done');manuscripts.save(s.directory(self.job),s.get_job(self.job),b['id'],0,0,'青柠特别版本')
        body={'title':'通勤杯项目','project':'春季新品','product_label':'杯子','tags':['通勤','口播'],'base_version':0}
        r=self.client.patch(f'/api/jobs/{self.job}/metadata',headers=self.headers,json=body);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.patch(f'/api/jobs/{self.job}/metadata',headers=self.headers,json=body).status_code,409)
        rows=self.client.get('/api/jobs',params={'q':'青柠特别','project':'春季新品','product':'杯','tag':'口播'}).json();self.assertEqual([row['id'] for row in rows],[self.job])
        self.assertEqual(self.client.get('/api/jobs',params={'q':'青柠特别','project':'其他项目'}).json(),[])
        self.assertEqual(self.client.get('/api/jobs?start=invalid').status_code,400)
        self.assertEqual(self.client.get('/api/jobs?start=2026-10-30&end=2026-10-01').status_code,400)
        self.assertIn('春季新品',self.client.get('/api/library/catalog').json()['projects'])
        self.assertEqual(json.loads((s.directory(self.job)/'job.json').read_text(encoding='utf-8'))['project'],'春季新品')
    def test_adoption_bulk_is_atomic_and_conflicts_do_not_overwrite(self):
        b=self.batch(existing=2);url=f'/api/jobs/{self.job}/drafts/{b["id"]}/editorial'
        r=self.client.put(url,headers=self.headers,json={'items':[{'index':0,'status':'adopted','note':'可拍摄','base_version':0}]});self.assertEqual(r.status_code,200,r.text)
        before=copy.deepcopy(s.get_job(self.job)['batches'][0]['editorial'])
        r=self.client.put(url,headers=self.headers,json={'items':[{'index':1,'status':'shoot','base_version':0},{'index':0,'status':'discarded','base_version':0}]})
        self.assertEqual(r.status_code,409);self.assertEqual(s.get_job(self.job)['batches'][0]['editorial'],before)
        self.assertEqual(s.get_job(self.job)['batches'][0]['variants'][0]['segments'],REFERENCE)
    def test_similarity_uses_latest_saved_text_not_immutable_generation(self):
        b=self.batch(existing=2);manuscripts.save(s.directory(self.job),s.get_job(self.job),b['id'],0,0,'甲'*50);manuscripts.save(s.directory(self.job),s.get_job(self.job),b['id'],1,0,'乙'*50)
        r=self.client.post(f'/api/jobs/{self.job}/drafts/{b["id"]}/review',headers=self.headers,json={'indices':[0,1]});self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['pairs'],[])
        self.assertIn('本机文本',r.json()['method'])
    def test_preview_reads_and_suggests_without_creating_jobs_or_calling_ai(self):
        before=len(s.JOBS);text='脚本1\n第一个开场。\n\n脚本2\n第二个开场。'
        with patch.object(s,'ai_client') as ai:
            r=self.client.post('/api/script-previews/document',headers=self.headers,files={'file':('多条脚本.txt',text.encode())})
            self.assertEqual(r.status_code,202);id=r.json()['id']
            # Finish the local read deterministically if it was queued on the worker.
            import time
            for _ in range(50):
                value=self.client.get('/api/script-previews/'+id).json()
                if value['status'] not in ('working','queued'):break
                time.sleep(.01)
            self.assertEqual(value['status'],'ready',value);self.assertEqual(len(value['parts']),2);self.assertEqual(value['source_text'],text);ai.assert_not_called()
        self.assertEqual(len(s.JOBS),before)
    def test_confirm_is_idempotent_parts_are_independent_and_original_is_retained(self):
        text='脚本1\n第一段。\n\n脚本2\n第二段。';preview=self.client.post('/api/script-previews/text',headers=self.headers,json={'text':text}).json()
        body={'parts':[{'title':'脚本A','text':'第一段。'},{'title':'脚本B','text':'第二段。'}],'auto_ai':False,'project':'拆分验收'}
        with patch.object(s.AI_POOL,'submit',side_effect=lambda f,*a:f(*a)),patch.object(s,'ai_client') as ai:
            first=self.client.post('/api/script-previews/'+preview['id']+'/confirm',headers=self.headers,json=body);second=self.client.post('/api/script-previews/'+preview['id']+'/confirm',headers=self.headers,json=body)
            self.assertEqual(first.status_code,202,first.text);self.assertEqual(first.json()['jobs'],second.json()['jobs']);self.assertTrue(second.json()['reused']);ai.assert_not_called()
        ids=first.json()['jobs'];self.assertNotEqual(ids[0],ids[1]);self.assertEqual([s.get_job(id)['raw'] for id in ids],['第一段。','第二段。']);self.assertEqual(s.SCRIPT_PREVIEWS.get(preview['id'])['source_text'],text)
        self.assertEqual(s.get_job(ids[0])['project'],'拆分验收')
        body['parts'][0]['text']='改变后不可重复确认';self.assertEqual(self.client.post('/api/script-previews/'+preview['id']+'/confirm',headers=self.headers,json=body).status_code,409)
    def test_bad_confirmation_does_not_create_partial_jobs(self):
        preview=self.client.post('/api/script-previews/text',headers=self.headers,json={'text':'待拆分原文'}).json();before=len(s.JOBS)
        r=self.client.post('/api/script-previews/'+preview['id']+'/confirm',headers=self.headers,json={'parts':[{'title':'有效','text':'正文'},{'title':'空白','text':' '}],'auto_ai':False})
        self.assertEqual(r.status_code,400);self.assertEqual(len(s.JOBS),before)
    def test_local_session_and_task_progress(self):
        self.assertEqual(self.client.post('/api/script-previews/text',json={'text':'原文'}).status_code,403)
        b=self.batch();s.update(self.job,generation_progress={'completed':1,'total':3,'batch_id':b['id']})
        row=next(row for row in self.client.get('/api/tasks').json() if row['id']==self.job);self.assertEqual(row['remaining'],2)


class SplitAndSimilarity(unittest.TestCase):
    def test_numbered_selling_points_are_not_independent_scripts(self):
        text='1. 配有杯盖。\n2. 容量300mL。';self.assertEqual(len(suggest_parts(text,'商品介绍')),1)
        source='开头说明\n脚本一\n甲。\n脚本二\n乙。';parts=suggest_parts(source,'文档');self.assertEqual(len(parts),2)
        self.assertEqual(''.join(''.join(p['text'].split()) for p in parts),''.join(source.split()))
    def test_identical_openings_and_body_are_explicit_text_hints(self):
        rows=[{'index':0,'revision':1,'text':'相同开场。\n晴禾杯，配有杯盖。'},{'index':1,'revision':0,'text':'相同开场。\n晴禾杯，配有杯盖。'}]
        report=text_review('参考原文',rows);self.assertEqual(report['pairs'][0]['similarity'],100);self.assertIn('商品名',report['method'])


if __name__=='__main__':unittest.main()
