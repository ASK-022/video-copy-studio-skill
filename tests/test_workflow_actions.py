from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from studio_agent import invoke


class Client:
    def request(self,path,*args):
        if path=='/jobs/j':return {'id':'j','title':'参考','batches':[{'id':'b','variants':[{},{}],'editorial':{'0':{'status':'adopted','version':2}}}]}
        return {'path':path,'args':args}
    def upload(self,*args,**kwargs):return {'args':args,'kwargs':kwargs}


class WorkflowActions(unittest.TestCase):
    def test_preview_is_local_intake_and_confirmation_is_explicit(self):
        c=Client();r=invoke(c,{'action':'preview-script','file':'example.docx'});self.assertTrue(r['kwargs']['preview'])
        self.assertEqual(invoke(c,{'action':'get-preview','preview_id':'p'})['path'],'/script-previews/p')
        with self.assertRaises(ValueError):invoke(c,{'action':'confirm-preview','preview_id':'p','parts':[]})
        r=invoke(c,{'action':'confirm-preview','preview_id':'p','confirmed':True,'parts':[{'title':'A','text':'正文'}]});self.assertEqual(r['path'],'/script-previews/p/confirm')
    def test_resume_does_not_send_new_facts_or_count(self):
        r=invoke(Client(),{'action':'resume','job_id':'j','facts':'不能替换','count':99});self.assertEqual(r['path'],'/jobs/j/drafts/b/resume');self.assertEqual(r['args'],('POST',{}))
    def test_review_and_adoption_use_one_based_indices(self):
        r=invoke(Client(),{'action':'review-drafts','job_id':'j','indices':[1,2]});self.assertEqual(r['args'][1]['indices'],[0,1])
        r=invoke(Client(),{'action':'set-editorial','job_id':'j','indices':[1],'status':'shoot'});self.assertEqual(r['args'][1]['items'][0]['base_version'],2)
    def test_list_search_and_metadata_preserve_current_title(self):
        c=Client();self.assertIn('project=',invoke(c,{'action':'list','project':'新品'})['path'])
        r=invoke(c,{'action':'set-metadata','job_id':'j','metadata':{'project':'新品'}});self.assertEqual(r['args'][1]['title'],'参考');self.assertEqual(r['args'][0],'PATCH')


if __name__=='__main__':unittest.main()
