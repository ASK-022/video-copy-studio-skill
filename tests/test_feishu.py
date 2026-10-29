import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from client.feishu import FeishuStore,FeishuSettings,target_parts
from client.draft_exports import DraftTextExport,TABLE_HEADERS,SCRIPT_HEADERS,SHOOTING_HEADERS


class FeishuExports(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.calls=[];self.values=[];self.failure=None
        self.store=FeishuStore(self.temp.name,httpx.MockTransport(self.respond))
        self.seal=patch('client.feishu.seal',side_effect=lambda s:'sealed:'+s).start()
        patch('client.feishu.unseal',side_effect=lambda s:s.removeprefix('sealed:')).start()
        self.addCleanup(patch.stopall)
        self.store.save(FeishuSettings(app_id='cli_test',secret='test-secret',target_url='https://example.feishu.cn/sheets/testToken?sheet=sheetA'))
        self.item={'id':'job-A','title':'参考A','batches':[{'id':'batch-A','created':1,'mode':'same','variants':[
            {'title':'第一条','segments':[{'text':'原段落甲'},{'text':'原段落乙'}]},
            {'title':'第二条','segments':[{'text':'不可混入'}]}]}]}
        self.request=DraftTextExport(batch_id='batch-A',format='xlsx',items=[{'index':0,'text':'已编辑甲\n\n已编辑乙'}])

    def respond(self,request):
        self.assertEqual(request.url.host,'open.feishu.cn');self.calls.append(request)
        if request.url.path.endswith('/tenant_access_token/internal'):
            self.assertEqual(json.loads(request.content)['app_secret'],'test-secret')
            return httpx.Response(200,json={'code':0,'tenant_access_token':'fake-access-token'})
        self.assertEqual(request.headers['Authorization'],'Bearer fake-access-token')
        if request.url.path.endswith('/sheets/query'):
            return httpx.Response(200,json={'code':0,'data':{'sheets':[{'sheet_id':'sheetA','title':'文案库','grid_properties':{'row_count':200}}]}})
        if '/values/' in request.url.path:return httpx.Response(200,json={'code':0,'data':{'valueRange':{'values':copy.deepcopy(self.values)}}})
        if request.url.path.endswith('/values_append'):
            if self.failure=='timeout':raise httpx.ReadTimeout('test timeout')
            if self.failure=='permission':return httpx.Response(200,json={'code':99991672,'msg':'do not echo test-secret'})
            body=json.loads(request.content);self.assertEqual(request.url.params['insertDataOption'],'INSERT_ROWS')
            self.values.extend(body['valueRange']['values'])
            return httpx.Response(200,json={'code':0,'data':{'updates':{'updatedRange':body['valueRange']['range']}}})
        self.fail('Unexpected endpoint '+str(request.url))

    def test_read_only_connection_and_safe_settings(self):
        result=self.store.test();self.assertEqual(result['sheet_id'],'sheetA')
        self.assertFalse(any(r.url.path.endswith('/values_append') for r in self.calls))
        self.assertNotIn('test-secret',json.dumps(self.store.public()));self.assertNotIn('fake-access-token',self.store.path.read_text())
        with self.assertRaises(ValueError):self.store.save(FeishuSettings(app_id='cli_other',target_url='https://example.feishu.cn/sheets/testToken'))

    def test_selected_edited_text_is_appended_once_with_header(self):
        before=copy.deepcopy(self.item);result=self.store.sync(self.item,self.request)
        self.assertEqual(result['count'],1);self.assertEqual(self.values[0],TABLE_HEADERS)
        self.assertEqual(self.values[1][2],'已编辑甲\n\n已编辑乙');self.assertEqual(self.values[1][7],'修改稿')
        self.assertNotIn('不可混入',json.dumps(self.values,ensure_ascii=False))
        self.assertTrue(self.store.sync(self.item,self.request)['duplicate'])
        self.assertEqual(len([r for r in self.calls if r.url.path.endswith('/values_append')]),1)
        self.assertEqual(self.item,before)

    def test_wrong_header_blocks_write(self):
        self.values=[['已有客户资料']]
        with self.assertRaisesRegex(ValueError,'表头'):self.store.sync(self.item,self.request)
        self.assertFalse(any(r.url.path.endswith('/values_append') for r in self.calls))

    def test_timeout_is_not_silently_retried_but_known_rejection_can_be_fixed(self):
        self.failure='permission'
        with self.assertRaises(ValueError) as error:self.store.sync(self.item,self.request)
        self.assertNotIn('test-secret',str(error.exception))
        self.failure='timeout'
        with self.assertRaises(ValueError):self.store.sync(self.item,self.request)
        self.failure=None
        with self.assertRaisesRegex(ValueError,'上次写入的结果尚未确认'):self.store.sync(self.item,self.request)
        self.assertEqual(len([r for r in self.calls if r.url.path.endswith('/values_append')]),2)

    def test_target_rejects_other_hosts_and_document_types(self):
        for url in ['http://example.feishu.cn/sheets/test','https://evil.test/sheets/test','https://example.feishu.cn.evil.test/sheets/test','https://example.feishu.cn/base/test']:
            with self.assertRaises(ValueError):target_parts(url)
        self.assertEqual(target_parts('https://example.feishu.cn/sheets/test?sheet=abc'),('test','abc'))

    def test_reference_templates_use_matching_column_ranges_and_block_mixed_headers(self):
        self.request.template='script';self.request.table_options.product='测试产品'
        result=self.store.sync(self.item,self.request)
        self.assertEqual(self.values[0],SCRIPT_HEADERS);self.assertIn(':E',result['range'])
        self.assertEqual(self.values[1][1],'已编辑甲\n\n已编辑乙')
        self.request.template='shooting'
        with self.assertRaisesRegex(ValueError,'所选模板不一致'):self.store.sync(self.item,self.request)
        self.values=[]
        result=self.store.sync(self.item,self.request)
        self.assertEqual(self.values[0],SHOOTING_HEADERS);self.assertEqual(result['count'],1)
        self.assertIn(':H',result['range'])


class FeishuEncryption(unittest.TestCase):
    def test_secret_is_encrypted_and_blank_save_preserves_it(self):
        with tempfile.TemporaryDirectory() as folder:
            store=FeishuStore(folder)
            config=FeishuSettings(app_id='cli_encrypttest',secret='test-only-feishu-secret',target_url='https://example.feishu.cn/sheets/test')
            store.save(config)
            self.assertNotIn(config.secret,store.path.read_text(encoding='utf-8'))
            encrypted=store.read()['encrypted_secret']
            store.save(FeishuSettings(app_id=config.app_id,target_url=config.target_url))
            self.assertEqual(store.read()['encrypted_secret'],encrypted)
            self.assertNotIn('secret',store.public())


if __name__=='__main__':unittest.main()
