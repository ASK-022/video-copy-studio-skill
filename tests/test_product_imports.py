import copy
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

_state=tempfile.TemporaryDirectory(prefix='product-material-tests-')
if 'client.app' not in sys.modules:os.environ['COPY_STUDIO_DATA']=_state.name
from fastapi.testclient import TestClient
from PIL import Image
from client import app as studio,product_imports

SOURCE='晴禾便携杯，配有杯盖，19.9元。'
PROFILE={'product':{'value':'晴禾便携杯','source_excerpt':'晴禾便携杯'},
         'selling_points':[{'value':'配有杯盖','source_excerpt':'配有杯盖'}],
         'needs_confirmation':[{'value':'19.9元价格待核对','source_excerpt':'19.9元'}]}


class ProductImports(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(studio.app,base_url=studio.ORIGIN);self.client.get('/');self.headers={'X-Studio-Request':'1'}
        self.id=studio.new_job('原参考商品','upload','原商品：蓝色香薰')['id']
        studio.update(self.id,status='done',corrected='原参考口播',product_facts='蓝色香薰，茶香')
        self.ai=Mock();self.ai.extract_product_material.return_value=copy.deepcopy(PROFILE)
        self.base=f'/api/jobs/{self.id}'

    def extract_text(self,mode='switch'):
        with patch.object(studio,'ai_client',return_value=self.ai),patch.object(studio.PRODUCT_POOL,'submit',side_effect=lambda fn,*args:fn(*args)):
            return self.client.post(self.base+'/product-imports/text',headers=self.headers,json={'mode':mode,'text':SOURCE})

    def test_own_copy_is_the_only_ai_input_and_reference_is_unchanged(self):
        before=copy.deepcopy(studio.get_job(self.id));reply=self.extract_text();self.assertEqual(reply.status_code,202,reply.text)
        value=self.client.get(self.base+'/product-imports/'+reply.json()['id']).json()
        self.assertEqual(value['status'],'done');self.ai.extract_product_material.assert_called_once_with(SOURCE)
        self.assertNotIn('19.9',value['facts']);self.assertEqual(value['profile']['needs_confirmation'],PROFILE['needs_confirmation'])
        self.assertEqual(studio.get_job(self.id),before)

    def test_apply_is_mode_scoped_durable_and_does_not_change_reference(self):
        record=self.extract_text().json();result=self.client.put(self.base+'/product-material',headers=self.headers,json={
            'mode':'switch','source_id':record['id'],'text':'商品：晴禾便携杯\n卖点：配有杯盖'})
        self.assertEqual(result.status_code,200,result.text)
        saved=self.client.get(self.base).json();self.assertEqual(saved['product_facts'],'蓝色香薰，茶香')
        self.assertNotIn('same',saved['material_drafts']);self.assertEqual(saved['material_drafts']['switch']['profile'],PROFILE)
        raw=(studio.directory(self.id)/'job.json').read_text(encoding='utf-8');self.assertIn('晴禾便携杯',raw)
        result=self.client.put(self.base+'/product-material',headers=self.headers,json={'mode':'switch','active':False})
        self.assertFalse(result.json()['switch']['active'])

    def test_another_reference_or_mode_cannot_apply_the_result(self):
        record=self.extract_text().json();other=studio.new_job('另一个参考','upload','')['id'];studio.update(other,status='done')
        body={'mode':'switch','source_id':record['id'],'text':'不应填入'}
        self.assertEqual(self.client.put('/api/jobs/'+other+'/product-material',headers=self.headers,json=body).status_code,404)
        self.assertEqual(self.client.put(self.base+'/product-material',headers=self.headers,json={**body,'mode':'same'}).status_code,409)

    def test_images_send_ocr_text_only_to_ai(self):
        image=io.BytesIO();Image.new('RGB',(100,80),'white').save(image,format='PNG')
        with patch.object(studio,'ai_client',return_value=self.ai),patch.object(studio.product_imports,'image_text',return_value=SOURCE) as ocr,patch.object(studio.PRODUCT_POOL,'submit',side_effect=lambda fn,*args:fn(*args)):
            response=self.client.post(self.base+'/product-imports/images',headers=self.headers,data={'mode':'switch'},files=[('files',('product.png',image.getvalue(),'image/png'))])
        self.assertEqual(response.status_code,202,response.text);self.assertEqual(ocr.call_count,1)
        self.ai.extract_product_material.assert_called_once_with(SOURCE)
        value=self.client.get(self.base+'/product-imports/'+response.json()['id']).json();self.assertEqual(value['kind'],'images');self.assertEqual(value['status'],'done')

    def test_no_readable_text_does_not_call_ai(self):
        with patch.object(studio,'ai_client',return_value=self.ai):record=studio.new_material(self.id,'switch','images',self.ai)
        with patch.object(studio.product_imports,'image_text',side_effect=ValueError('没有识别到清晰文字。')):
            studio.material_work(record['id'],self.ai,paths=[Path('not-read-by-mock.png')])
        self.assertEqual(studio.MATERIAL_IMPORTS[record['id']]['status'],'error');self.ai.extract_product_material.assert_not_called()

    def test_unverifiable_ai_quotes_are_not_applied(self):
        self.ai.extract_product_material.return_value={'product':None,'selling_points':[{'value':'编造卖点','source_excerpt':'不存在的来源'}],'needs_confirmation':[]}
        record=self.extract_text().json();value=self.client.get(self.base+'/product-imports/'+record['id']).json()
        self.assertEqual(value['status'],'error');self.assertNotIn('material_drafts',studio.get_job(self.id))

    def test_pending_import_prevents_double_submission(self):
        with patch.object(studio,'ai_client',return_value=self.ai),patch.object(studio.PRODUCT_POOL,'submit'):
            first=self.client.post(self.base+'/product-imports/text',headers=self.headers,json={'mode':'switch','text':SOURCE})
            second=self.client.post(self.base+'/product-imports/text',headers=self.headers,json={'mode':'switch','text':SOURCE})
        self.assertEqual(first.status_code,202);self.assertEqual(second.status_code,409)
        self.assertGreater(self.client.get('/api/health').json()['product_imports_active'],0)
        self.assertEqual(self.client.delete(self.base,headers=self.headers).status_code,409)

    def test_input_limits_and_local_session_are_enforced(self):
        self.assertEqual(self.client.post(self.base+'/product-imports/text',json={'mode':'switch','text':SOURCE}).status_code,403)
        self.assertEqual(self.client.post(self.base+'/product-imports/text',headers=self.headers,json={'mode':'switch','text':' '}).status_code,400)
        self.assertEqual(self.client.post(self.base+'/product-imports/images',headers=self.headers,data={'mode':'switch'},files=[('files',('a.png',b'x'*50,'image/png'))]*6).status_code,400)
        with patch.object(studio,'ai_client',return_value=self.ai),patch.object(studio.product_imports,'MAX_IMAGE_BYTES',32):
            result=self.client.post(self.base+'/product-imports/images',headers=self.headers,data={'mode':'switch'},files=[('files',('a.png',b'x'*50,'image/png'))])
        self.assertEqual(result.status_code,400);self.ai.extract_product_material.assert_not_called()

    def test_ocr_uses_actual_image_format_and_pixel_limits(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(product_imports,'_ENGINE',Mock()) as engine:
            root=Path(tmp);bad=root/'fake.png';bad.write_bytes(b'not an image')
            with self.assertRaises(ValueError):product_imports.image_text([bad])
            image=root/'real.png';Image.new('RGB',(100,80),'white').save(image)
            with patch.object(product_imports,'MAX_PIXELS',100):
                with self.assertRaises(ValueError):product_imports.image_text([image])
            engine.assert_not_called()


if __name__=='__main__':unittest.main()
