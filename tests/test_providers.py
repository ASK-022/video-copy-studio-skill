import json
from pathlib import Path
import tempfile
import os
import sys
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from client.providers import ProviderStore
from client.security import seal

# Running this file alone must never import the application against real user jobs.
_isolated_app_state=tempfile.TemporaryDirectory(prefix='provider-app-tests-')
if 'client.app' not in sys.modules:
    os.environ['COPY_STUDIO_DATA']=_isolated_app_state.name


class ProviderFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='provider-tests-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.legacy={'base_url':'https://api.deepseek.com','model':'model-a','encrypted_key':seal('test-key-a')}
        (self.root/'ai.json').write_text(json.dumps(self.legacy),encoding='utf-8')
        (self.root/'tikhub.json').write_text('{"unchanged":true}',encoding='utf-8')
        self.store=ProviderStore(self.root)

    def add_second(self):
        return self.store.save(None,name='第二家',base_url='https://vendor-b.example/v1',model='model-b',key='test-key-b')


class ProviderProfiles(ProviderFixture):

    def test_migration_retains_encrypted_key_and_other_services(self):
        initial=self.store.listing()
        self.assertEqual(len(initial['providers']),1)
        self.assertEqual(self.store.active()['encrypted_key'],self.legacy['encrypted_key'])
        self.assertEqual(self.store.client().key,'test-key-a')
        self.assertEqual(json.loads((self.root/'tikhub.json').read_text()),{'unchanged':True})
        self.assertEqual(len(ProviderStore(self.root).listing()['providers']),1)

    def test_independent_profiles_selection_and_inflight_snapshot(self):
        first=self.store.active()['id'];running_client=self.store.client()
        second=self.add_second()
        self.assertEqual(self.store.active()['id'],first)
        self.store.select(second['id'])
        chosen=self.store.client()
        self.assertEqual((chosen.base_url,chosen.model,chosen.key),('https://vendor-b.example/v1','model-b','test-key-b'))
        self.assertEqual(running_client.key,'test-key-a')
        self.assertEqual(running_client.model,'model-a')
        self.assertEqual(ProviderStore(self.root).active()['id'],second['id'])
        public=json.dumps(self.store.listing())
        self.assertNotIn('test-key-a',public);self.assertNotIn('test-key-b',public);self.assertNotIn('encrypted_key',public)

    def test_blank_key_preserves_only_own_key_and_url_change_requires_reentry(self):
        second=self.add_second();self.store.select(second['id'])
        self.store.save(second['id'],name='第二家新模型',base_url=second['base_url'],model='model-b2')
        self.assertEqual(self.store.client().key,'test-key-b')
        with self.assertRaises(ValueError):
            self.store.save(second['id'],name='另一地址',base_url='https://other.example/v1',model='model-b2')
        self.assertEqual(self.store.client().base_url,second['base_url'])
        self.store.save('default-ai',name='第一家',base_url=self.legacy['base_url'],model='a2')
        self.assertEqual(json.loads((self.root/'ai.json').read_text())['model'],'model-b2')

    def test_no_key_cannot_be_selected_and_active_profile_cannot_be_removed(self):
        second=self.store.save(None,name='未配置',base_url='https://empty.example/v1',model='empty')
        with self.assertRaises(ValueError):self.store.select(second['id'])
        with self.assertRaises(ValueError):self.store.remove(self.store.active()['id'])
        self.store.remove(second['id'])
        self.assertEqual(len(self.store.listing()['providers']),1)
        with self.assertRaises(ValueError):self.store.client(second['id'])


class ProviderAPI(ProviderFixture):
    def setUp(self):
        super().setUp()
        # test_copy_studio configures a temporary application state before importing it.
        from client import app as studio
        self.studio=studio
        patcher=patch.object(studio,'PROVIDERS',self.store)
        patcher.start();self.addCleanup(patcher.stop)
        state_patcher=patch.object(studio,'STATE',self.root)
        state_patcher.start();self.addCleanup(state_patcher.stop)
        self.client=TestClient(studio.app,base_url=studio.ORIGIN);self.client.get('/')
        self.headers={'X-Studio-Request':'1'}

    def test_add_select_edit_routes_use_selected_provider(self):
        response=self.client.post('/api/providers',headers=self.headers,json={'name':'备用接口','base_url':'https://vendor-b.example/v1','model':'model-b','key':'test-key-b'})
        self.assertEqual(response.status_code,201);second=response.json()
        self.assertFalse(second['active'])
        self.assertNotIn('test-key-b',response.text)
        result=self.client.put('/api/services',headers=self.headers,json={'ai_provider_id':second['id'],'default_link_provider':'local'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.studio.ai_client().model,'model-b')
        self.assertEqual(self.studio.ai_client().key,'test-key-b')
        self.assertEqual(self.client.get('/api/settings').json()['provider_name'],'备用接口')

    def test_testing_inactive_provider_does_not_switch_active_or_use_other_key(self):
        second=self.add_second();requests=[];original=httpx.Client
        def handle(request):
            requests.append(request)
            return httpx.Response(200,json={'choices':[{'message':{'content':'OK'}}]})
        with patch('client.ai.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)):
            response=self.client.post('/api/providers/'+second['id']+'/test',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(requests[0].url.host,'vendor-b.example')
        self.assertEqual(requests[0].headers['authorization'],'Bearer test-key-b')
        self.assertEqual(json.loads(requests[0].content)['model'],'model-b')
        self.assertEqual(self.store.active()['id'],'default-ai')

    def test_invalid_link_choice_does_not_partially_change_ai_provider(self):
        second=self.add_second()
        with patch.object(self.studio,'tikhub_settings',return_value={'has_key':False}):
            result=self.client.put('/api/services',headers=self.headers,json={'ai_provider_id':second['id'],'default_link_provider':'tikhub'})
        self.assertEqual(result.status_code,400)
        self.assertEqual(self.store.active()['id'],'default-ai')

    def test_json_mode_can_be_disabled_per_provider(self):
        p=self.store.save(None,name='普通兼容接口',base_url='https://vendor-b.example/v1',model='model-b',key='test-key-b',json_mode=False)
        client=self.store.client(p['id']);requests=[];original=httpx.Client
        def handle(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"segments":[{"id":1,"role":"开场","text":"你好"}]}'}}]})
        with patch('client.ai.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)):
            self.assertEqual(client.analyze('你好')[0]['text'],'你好')
        self.assertNotIn('response_format',requests[0])
        self.assertTrue(self.store.client('default-ai').json_mode)


if __name__=='__main__':unittest.main()
