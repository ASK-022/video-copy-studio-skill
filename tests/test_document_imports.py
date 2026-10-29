import copy
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
from zipfile import ZipFile

_state=tempfile.TemporaryDirectory(prefix='document-tests-')
if 'client.app' not in sys.modules:os.environ['COPY_STUDIO_DATA']=_state.name
from fastapi.testclient import TestClient
from PIL import Image
from client import document_imports as docs,app as studio
from client.ai import AIClient,Structure

SOURCE='晴禾便携杯，配有杯盖。\n\n通勤路上，可以随身携带。'
PROFILE={'product':{'value':'晴禾便携杯','source_excerpt':'晴禾便携杯'},'selling_points':[{'value':'配有杯盖','source_excerpt':'配有杯盖'}],'needs_confirmation':[]}
SEGMENTS=[{'id':i+1,'role':role,'text':p} for i,(p,role) in enumerate(zip(SOURCE.split('\n\n'),['商品介绍','使用场景']))]

def word_bytes():
    buf=io.BytesIO()
    with ZipFile(buf,'w') as z:
        z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>晴禾便携杯，配有杯盖。</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>通勤路上，可以随身携带。</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    return buf.getvalue()


class DocumentReading(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_txt_encodings_and_paragraphs(self):
        p=self.root/'脚本.txt'
        for encoding in ['utf-8-sig','gb18030','utf-16']:
            p.write_bytes(SOURCE.encode(encoding));self.assertEqual(docs.document_text(p),SOURCE)
    def test_docx_reads_body_and_table_in_order(self):
        p=self.root/'商品.docx';p.write_bytes(word_bytes());self.assertEqual(docs.document_text(p),SOURCE)
    def test_bad_word_and_binary_text_are_rejected(self):
        p=self.root/'broken.docx';p.write_bytes(b'bad');
        with self.assertRaisesRegex(ValueError,'Word'):docs.document_text(p)
        p=self.root/'binary.txt';p.write_bytes(b'a\x00b')
        with self.assertRaisesRegex(ValueError,'非文本'):docs.document_text(p)
    def test_dtd_and_oversized_word_body_are_rejected(self):
        p=self.root/'danger.docx'
        with ZipFile(p,'w') as z:z.writestr('word/document.xml','<!DOCTYPE x [<!ENTITY a "x">]><x/>')
        with self.assertRaises(ValueError):docs.document_text(p)
        with ZipFile(p,'w') as z:z.writestr('word/document.xml','x'*(4*1024*1024+1))
        with self.assertRaisesRegex(ValueError,'正文过大'):docs.document_text(p)
    def test_limits_no_silent_truncation(self):
        p=self.root/'long.txt';p.write_text('文'*20001,encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'2 万字'):docs.document_text(p)
        with patch.object(docs,'MAX_BYTES',8):
            with self.assertRaisesRegex(ValueError,'20 MB'):docs.document_text(p)
    def test_scanned_pdf_uses_local_ocr(self):
        p=self.root/'scan.pdf';Image.new('RGB',(300,300),'white').save(p,'PDF')
        with patch('client.product_imports.image_text',return_value='图片 1：\n'+SOURCE) as ocr:
            self.assertEqual(docs.document_text(p),SOURCE);self.assertEqual(ocr.call_count,1)
            self.assertFalse(Path(ocr.call_args.args[0][0]).exists())
    def test_native_pdf_text_does_not_use_ocr(self):
        # Minimal valid PDF with Helvetica text and a byte-correct xref.
        stream=b'BT /F1 18 Tf 50 700 Td (A portable cup.) Tj ET'
        objs=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
        content=b'%PDF-1.4\n';offsets=[0]
        for i,o in enumerate(objs,1):offsets.append(len(content));content+=str(i).encode()+b' 0 obj\n'+o+b'\nendobj\n'
        xref=len(content);content+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{v:010d} 00000 n \n'.encode() for v in offsets[1:])+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
        p=self.root/'native.pdf';p.write_bytes(content)
        with patch('client.product_imports.image_text') as ocr:self.assertEqual(docs.document_text(p),'A portable cup.');ocr.assert_not_called()
    def test_pdf_page_limit(self):
        p=self.root/'two.pdf';im=Image.new('RGB',(30,30),'white');im.save(p,'PDF',save_all=True,append_images=[im])
        with patch.object(docs,'MAX_PAGES',1),self.assertRaisesRegex(ValueError,'1–40'):docs.document_text(p)


class DocumentWorkflow(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(studio.app,base_url=studio.ORIGIN);self.client.get('/');self.headers={'X-Studio-Request':'1'}
        self.ai=Mock();self.ai.analyze_script.return_value=copy.deepcopy(SEGMENTS);self.ai.extract_product.return_value=copy.deepcopy(PROFILE);self.ai.extract_product_material.return_value=copy.deepcopy(PROFILE)
    def post_script(self,**body):
        with patch.object(studio,'ai_client',return_value=self.ai),patch.object(studio.AI_POOL,'submit',side_effect=lambda f,*a:f(*a)):
            return self.client.post('/api/jobs/script',headers=self.headers,json={'text':SOURCE,**body})
    def test_script_import_skips_asr_and_correction_preserves_source(self):
        with patch.object(studio.ASR_POOL,'submit') as asr:
            r=self.post_script();self.assertEqual(r.status_code,202,r.text);asr.assert_not_called()
        item=studio.get_job(r.json()['id']);self.assertEqual(item['raw'],SOURCE);self.assertEqual(item['corrected'],SOURCE);self.assertEqual(item['structure'],SEGMENTS);self.assertEqual(item['status'],'done');self.assertFalse(item['asr_timed']);self.ai.correct.assert_not_called()
        self.ai.analyze_script.assert_called_once_with(SOURCE)
        listed=self.client.get('/api/jobs').json();self.assertEqual(next(j for j in listed if j['id']==item['id'])['kind'],'script')
    def test_script_upload_and_both_generation_modes_reuse_original_structure(self):
        with patch.object(studio,'ai_client',return_value=self.ai),patch.object(studio.AI_POOL,'submit',side_effect=lambda f,*a:f(*a)):
            r=self.client.post('/api/jobs/script/upload',headers=self.headers,data={'auto_ai':'true'},files={'file':('我的脚本.docx',word_bytes())})
            self.assertEqual(r.status_code,202,r.text);job=studio.get_job(r.json()['id'])
            self.assertEqual(job['raw'],SOURCE);self.assertEqual(job['kind'],'script');self.assertFalse(job['input_file'])
            for mode in ['same','switch']:
                def generate(reference,mode,facts,count,direction):return {'variants':[{'title':'新版本','segments':[dict(s,text='新表达'+s['text']) for s in reference]} for _ in range(count)],'review_notes':[]}
                self.ai.generate.side_effect=generate
                r=self.client.post('/api/jobs/'+job['id']+'/drafts/generate',headers=self.headers,json={'mode':mode,'facts':'商品：晴禾便携杯；配有杯盖。','count':3,'reference_text':SOURCE,'quality_check':False})
                self.assertEqual(r.status_code,202,r.text);batch=studio.get_job(job['id'])['batches'][-1];self.assertEqual(len(batch['variants']),3)
                self.assertEqual(batch['reference'],SEGMENTS);self.assertTrue(batch['complete']);self.assertEqual(studio.get_job(job['id'])['raw'],SOURCE)
    def test_no_ai_import_does_not_require_credentials_and_retry_is_not_asr(self):
        r=self.post_script(auto_ai=False);job=studio.get_job(r.json()['id']);self.assertEqual(job['structure'],[]);self.ai.analyze_script.assert_not_called()
        with patch.object(studio.AI_POOL,'submit',side_effect=lambda f,*a:f(*a)),patch.object(studio.ASR_POOL,'submit') as asr:
            r=self.client.post('/api/jobs/'+job['id']+'/retry',headers=self.headers);self.assertEqual(r.status_code,202);asr.assert_not_called()
    def test_material_document_only_sends_own_body_and_keeps_reference(self):
        job=studio.new_job('其他参考','upload','另一个商品');studio.update(job['id'],status='done',raw='原参考',corrected='原参考');before=copy.deepcopy(studio.get_job(job['id']))
        with patch.object(studio,'ai_client',return_value=self.ai),patch.object(studio.PRODUCT_POOL,'submit',side_effect=lambda f,*a:f(*a)):
            r=self.client.post('/api/jobs/'+job['id']+'/product-imports/document',headers=self.headers,data={'mode':'switch'},files={'file':('商品.docx',word_bytes())})
        self.assertEqual(r.status_code,202,r.text);record=studio.MATERIAL_IMPORTS[r.json()['id']];self.assertEqual(record['status'],'done');self.assertEqual(record['kind'],'document');self.assertEqual(record['document_name'],'商品.docx');self.ai.extract_product_material.assert_called_once_with(SOURCE);self.assertEqual(studio.get_job(job['id']),before)
    def test_invalid_uploads_and_local_session(self):
        self.assertEqual(self.client.post('/api/jobs/script',json={'text':SOURCE}).status_code,403)
        self.assertEqual(self.post_script(text=' ').status_code,400)
        r=self.client.post('/api/jobs/script/upload',headers=self.headers,files={'file':('old.doc',b'x')});self.assertEqual(r.status_code,400)
        with patch.object(docs,'MAX_BYTES',10):
            r=self.client.post('/api/jobs/script/upload',headers=self.headers,data={'auto_ai':'false'},files={'file':('large.txt',SOURCE.encode())});self.assertEqual(r.status_code,400)


class ParagraphValidation(unittest.TestCase):
    def test_ai_cannot_merge_or_change_written_paragraphs(self):
        client=object.__new__(AIClient)
        def call(prompt,body,schema,validator):return validator(Structure.model_validate({'segments':copy.deepcopy(SEGMENTS)}))
        with patch.object(client,'call',side_effect=call):self.assertEqual(client.analyze_script(SOURCE),SEGMENTS)
        bad=[{'id':1,'role':'合段','text':SOURCE}]
        with patch.object(client,'call',side_effect=lambda p,b,s,v:v(Structure.model_validate({'segments':bad}))),self.assertRaisesRegex(ValueError,'段落'):client.analyze_script(SOURCE)


if __name__=='__main__':unittest.main()
