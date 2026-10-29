import copy
import io
import os
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

_state=tempfile.TemporaryDirectory(prefix='narration-export-tests-')
if 'client.app' not in sys.modules:os.environ['COPY_STUDIO_DATA']=_state.name
from client import app as studio
from fastapi.testclient import TestClient
from client.draft_exports import DraftTextExport,table_payload,SCRIPT_HEADERS,SHOOTING_HEADERS


class NarrationExport(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(studio.app,base_url=studio.ORIGIN);self.client.get('/')
        self.headers={'X-Studio-Request':'1'}
        item=studio.new_job('导出测试','upload','');self.id=item['id']
        self.before=studio.update(self.id,status='done',batches=[{
            'id':'old','mode':'switch','variants':[{'title':'不应混入','segments':[{'text':'别的批次'}]}]},
            {'id':'current','mode':'same','variants':[
                {'title':'../香薰:茶香?','segments':[{'id':1,'role':'钩子','text':'第一段。'},{'id':2,'role':'卖点','text':'第二段。'}]},
                {'title':'未勾选','segments':[{'text':'不应导出。'}]},
                {'title':'第三条','segments':[{'text':'第三条口播。'}]}]}])

    def send(self,format='zip',items=None,batch='current'):
        return self.client.post(f'/api/jobs/{self.id}/drafts/text-export',headers=self.headers,json={
            'format':format,'batch_id':batch,'items':items if items is not None else [{'index':2,'text':'第三条口播。'},{'index':0,'text':'修改后的开头。\n\n保留原来的结尾。'}]})

    def test_zip_is_sorted_selected_plain_narration_with_safe_unicode_names(self):
        result=self.send();self.assertEqual(result.status_code,200)
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            names=archive.namelist();self.assertEqual(len(names),2)
            self.assertTrue(names[0].startswith('01_'));self.assertTrue(names[1].startswith('03_'))
            self.assertTrue(all('/' not in n and '\\' not in n and ':' not in n for n in names))
            self.assertEqual(archive.read(names[0]).decode('utf-8-sig'),'修改后的开头。\n\n保留原来的结尾。\n')
            self.assertEqual(archive.read(names[1]).decode('utf-8-sig'),'第三条口播。\n')
        self.assertEqual(studio.job(self.id),self.before)

    def test_collection_preserves_paragraphs_and_separates_scripts(self):
        result=self.send('txt');self.assertEqual(result.status_code,200)
        text=result.content.decode('utf-8-sig')
        self.assertIn('【01 · ',text);self.assertIn('【03 · 第三条】',text)
        self.assertIn('修改后的开头。\n\n保留原来的结尾。',text)
        self.assertNotIn('不应',text);self.assertNotIn('钩子',text)
        self.assertEqual(studio.job(self.id),self.before)

    def test_invalid_selection_does_not_fall_back_to_other_batches(self):
        self.assertEqual(self.send(batch='missing').status_code,400)
        self.assertEqual(self.send(items=[{'index':3,'text':'口播'}]).status_code,400)
        self.assertEqual(self.send(items=[{'index':0,'text':'甲'},{'index':0,'text':'乙'}]).status_code,400)
        self.assertEqual(self.send(items=[]).status_code,422)
        self.assertEqual(self.send(items=[{'index':0,'text':'  \n '}]).status_code,400)
        self.assertEqual(self.send(items=[{'index':0,'text':'甲\x00乙'}]).status_code,400)
        self.assertEqual(self.send(items=[{'index':-1,'text':'口播'}]).status_code,422)
        self.assertEqual(self.send(items=[{'index':0,'text':'长'*20001}]).status_code,422)
        self.assertEqual(studio.job(self.id),self.before)

    def test_xlsx_contains_selected_edited_narration_and_freezes_header(self):
        result=self.send('xlsx',items=[{'index':0,'text':'=这是一段文案\n\n第二段保留。'}])
        self.assertEqual(result.status_code,200,result.text[:200] if result.status_code!=200 else '')
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(sheet.find('.//s:pane',ns).get('state'),'frozen')
            self.assertEqual(len(sheet.findall('.//s:sheetData/s:row',ns)),2)
            self.assertFalse(sheet.findall('.//s:f',ns),'Narration must never become an executable formula')
            text=''.join(sheet.itertext())
            if 'xl/sharedStrings.xml' in archive.namelist():text+=''.join(ET.fromstring(archive.read('xl/sharedStrings.xml')).itertext())
            self.assertIn('=这是一段文案',text);self.assertIn('第二段保留。',text)
            self.assertNotIn('不应导出',text)
        self.assertEqual(studio.job(self.id),self.before)

    def test_script_template_matches_reference_columns_and_preserves_selected_copy(self):
        item=copy.deepcopy(self.before);item.update(kind='link',source='https://example.com/reference')
        request=DraftTextExport(batch_id='current',format='xlsx',template='script',table_options={'product':'动力红油','required_time':'10月30日前'},
                                items=[{'index':2,'text':'第三条改稿。'},{'index':0,'text':'开头。\n\n结尾。'}])
        payload=table_payload(item,request)
        self.assertEqual(payload['headers'],SCRIPT_HEADERS);self.assertEqual(len(payload['rows']),2)
        self.assertEqual(payload['rows'][0],['动力红油-01','开头。\n\n结尾。','https://example.com/reference','10月30日前',''])
        self.assertEqual(payload['rows'][1][0],'动力红油-03')

    def test_shooting_template_aggregates_selected_suggestions_without_invented_quantity(self):
        item=copy.deepcopy(self.before)
        item['batches'][1]['variants'][0]['production_segments']=[{'screen_suggestion':'产品特写'},{'screen_suggestion':'使用过程'}]
        item['batches'][1]['variants'][1]['production_segments']=[{'screen_suggestion':'未选择的镜头'}]
        item['batches'][1]['variants'][2]['production_segments']=[{'screen_suggestion':'产品特写'}]
        request=DraftTextExport(batch_id='current',format='xlsx',template='shooting',items=[{'index':0,'text':'甲'},{'index':2,'text':'乙'}])
        payload=table_payload(item,request)
        self.assertEqual(payload['headers'],SHOOTING_HEADERS);self.assertEqual(len(payload['rows']),1)
        row=payload['rows'][0];self.assertIsNone(row[1]);self.assertEqual(row[6:8],['',''])
        self.assertIn('待确认',row[3]);self.assertEqual(row[3].count('产品特写'),1);self.assertNotIn('未选择的镜头',row[3])
        request.table_options.shot_requirements='';self.assertEqual(table_payload(item,request)['rows'][0][3],'')
        request.table_options.quantity=60;self.assertEqual(table_payload(item,request)['rows'][0][1],60)


if __name__=='__main__':unittest.main()
