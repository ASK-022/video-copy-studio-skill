"""Read document bodies locally; neither documents nor PDF page images leave the PC."""
from pathlib import Path
import re
import tempfile
import threading
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile

MAX_BYTES=20*1024*1024
MAX_TEXT=20000
MAX_PAGES=40
SUFFIXES=('.docx','.pdf','.txt')
_PDF_LOCK=threading.Lock()  # PDFium is not thread safe across document instances.


def clean_text(text):
    text=text.replace('\r\n','\n').replace('\r','\n').replace('\ufeff','').strip()
    if not text:raise ValueError('文档没有可读取的正文，请检查文件内容或换用清晰的 PDF。')
    if len(text)>MAX_TEXT:raise ValueError('文档正文超过 2 万字，请按单份脚本或商品资料拆分后上传。')
    if '\x00' in text:raise ValueError('文件包含非文本内容，请另存为 UTF-8 TXT 后上传。')
    return text


def _docx(path):
    try:
        with ZipFile(path) as archive:
            if len(archive.infolist())>3000:raise ValueError('Word 文件内容过多，请另存为仅含正文的文档。')
            info=archive.getinfo('word/document.xml')
            if info.file_size>4*1024*1024:raise ValueError('Word 正文过大，请拆分文档后上传。')
            xml=archive.read(info)
        if re.search(br'<!\s*(DOCTYPE|ENTITY)',xml,re.I):raise ValueError('无法读取此 Word 文档，请另存为新的 .docx 文件。')
        root=ET.fromstring(xml)
        ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        paragraphs=[]
        for p in root.iter(ns+'p'):
            # Word paragraphs in tables are retained in document order.
            value=''.join(n.text or '' if n.tag==ns+'t' else '\t' if n.tag==ns+'tab' else '\n' if n.tag in (ns+'br',ns+'cr') else '' for n in p.iter())
            if value.strip():paragraphs.append(value.strip())
        return '\n\n'.join(paragraphs)
    except (BadZipFile,KeyError,ET.ParseError,RuntimeError,OSError) as exc:
        raise ValueError('Word 文档无法读取，请重新另存为 .docx 后上传。') from exc


def _txt(path):
    raw=path.read_bytes()
    encodings=['utf-16'] if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else ['utf-8-sig','gb18030']
    for encoding in encodings:
        try:return raw.decode(encoding)
        except UnicodeError:pass
    raise ValueError('TXT 编码无法识别，请另存为 UTF-8 后上传。')


def _pdf(path,notify):
    import pypdfium2 as pdfium
    from client.product_imports import image_text
    pages=[]
    with _PDF_LOCK:
        try:document=pdfium.PdfDocument(path.read_bytes())
        except Exception as exc:raise ValueError('PDF 无法打开，可能已加密或损坏；请解除密码或重新导出。') from exc
        try:
            if not 1<=len(document)<=MAX_PAGES:raise ValueError('PDF 每次支持 1–40 页，请拆分后上传。')
            for index in range(len(document)):
                notify(f'本机正在读取 PDF 第 {index+1} / {len(document)} 页…')
                page=document[index]
                try:
                    textpage=page.get_textpage()
                    try:text=textpage.get_text_bounded()
                    finally:textpage.close()
                    if not text.strip():
                        notify(f'本机正在识别 PDF 第 {index+1} 页的扫描文字…')
                        width,height=page.get_size()
                        if width<=0 or height<=0:raise ValueError('PDF 页面尺寸异常，请重新导出。')
                        bitmap=page.render(scale=min(2.5,2000/max(width,height)))
                        try:
                            with tempfile.TemporaryDirectory(prefix='studio-pdf-') as tmp:
                                image=Path(tmp)/'page.png';bitmap.to_pil().save(image)
                                try:text=re.sub(r'^图片 1：\n','',image_text([image]))
                                except ValueError as exc:
                                    if '没有识别到清晰文字' in str(exc):text=''
                                    else:raise
                        finally:bitmap.close()
                    if text.strip():pages.append(text.strip())
                    if sum(map(len,pages))>MAX_TEXT:raise ValueError('文档正文超过 2 万字，请拆分后上传。')
                finally:page.close()
        finally:document.close()
    return '\n\n'.join(pages)


def document_text(path,notify=lambda _:None):
    path=Path(path)
    if path.suffix.lower() not in SUFFIXES:raise ValueError('支持 Word（.docx）、PDF、TXT；旧版 .doc 请另存为 .docx。')
    if path.stat().st_size>MAX_BYTES:raise ValueError('文档超过 20 MB，请拆分后上传。')
    notify('正在本机读取文档正文…')
    try:
        text=_docx(path) if path.suffix.lower()=='.docx' else _pdf(path,notify) if path.suffix.lower()=='.pdf' else _txt(path)
        return clean_text(text)
    except (ValueError,RuntimeError):raise
    except Exception as exc:raise ValueError('文档读取失败，请检查内容或另存为 TXT / DOCX 后重试。') from exc
