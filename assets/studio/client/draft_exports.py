"""Plain narration exports; no model calls or changes to saved generation results."""
import io
import re
import zipfile
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime

from pydantic import BaseModel, Field


class SelectedDraft(BaseModel):
    index: int = Field(ge=0, strict=True)
    text: str = Field(min_length=1, max_length=20000)
    revision: int | None = Field(default=None,ge=0,strict=True)


class TableOptions(BaseModel):
    product: str = Field(default='',max_length=200)
    reference_url: str = Field(default='',max_length=2000)
    required_time: str = Field(default='',max_length=100)
    completion: str = Field(default='',max_length=200)
    quantity: int | None = Field(default=None,ge=1,le=1000000,strict=True)
    shot_requirements: str = Field(default='',max_length=20000)
    shot_reference_1: str = Field(default='',max_length=2000)
    shot_reference_2: str = Field(default='',max_length=2000)


class DraftTextExport(BaseModel):
    batch_id: str = Field(min_length=1, max_length=100)
    format: str = Field(pattern=r'^(txt|zip|xlsx)$')
    items: list[SelectedDraft] = Field(min_length=1, max_length=10000)
    template: str = Field(default='archive',pattern=r'^(archive|script|shooting)$')
    table_options: TableOptions = Field(default_factory=TableOptions)


def narration_rows(item, request):
    batch = next((b for b in item['batches'] if b['id'] == request.batch_id), None)
    if batch is None:
        raise ValueError('这个生成批次不存在，请刷新后重试。')
    indices = [row.index for row in request.items]
    if len(set(indices)) != len(indices) or any(i >= len(batch['variants']) for i in indices):
        raise ValueError('所选文案与当前批次不匹配，请重新选择。')
    if sum(len(row.text) for row in request.items) > 5000000:
        raise ValueError('单次导出内容过多，请分次选择导出。')
    rows = []
    for row in sorted(request.items, key=lambda r: r.index):
        current=batch['variants'][row.index].get('manuscript',{'revision':0})
        if row.revision is not None and (row.revision!=current['revision'] or row.text.strip()!=current.get('text','\n\n'.join(s['text'] for s in batch['variants'][row.index]['segments'])).strip()):
            raise ValueError('所选成稿版本已变化，请刷新后重新导出。')
        text = row.text.replace('\r\n', '\n').replace('\r', '\n').strip()
        if not text or '\x00' in text:
            raise ValueError('所选文案存在空白或无效字符，请检查后再导出。')
        title = str(batch['variants'][row.index].get('title') or '文案')
        rows.append((row.index + 1, title, text))
    return batch,rows


def table_rows(item, request):
    batch,rows=narration_rows(item,request)
    mode={'same':'同商品裂变','switch':'换商品套结构','original':'原创脚本'}.get(batch.get('mode'),'脚本')
    created=datetime.fromtimestamp(batch.get('created',0)).strftime('%Y-%m-%d %H:%M:%S')
    return [[i,title,text,len(re.sub(r'\s','',text)),mode,item['title'],created,
             ('成稿 v'+str(batch['variants'][i-1]['manuscript']['revision'])) if batch['variants'][i-1].get('manuscript',{}).get('text','').strip()==text else
             '修改稿' if text != '\n\n'.join(s['text'] for s in batch['variants'][i-1]['segments']).strip() else '生成原稿']
            for i,title,text in rows]


TABLE_HEADERS=['序号','标题','完整口播','字数','生成方式','参考来源','生成时间','稿件版本']
SCRIPT_HEADERS=['产品','脚本文案','参考视频链接','需求时间','拍摄完成时间']
SHOOTING_HEADERS=['产品','素材需求数量','参考视频1','画面镜头需求','镜头参考1','镜头参考2','需求时间','完成情况']


def table_payload(item,request):
    batch,selected=narration_rows(item,request)
    if request.template=='archive':return {'headers':TABLE_HEADERS,'rows':table_rows(item,request),'template':'archive'}
    options=request.table_options
    reference=options.reference_url.strip() if 'reference_url' in options.model_fields_set else (item.get('source','') if item.get('kind')=='link' else '')
    product=options.product.strip()
    if request.template=='script':
        return {'headers':SCRIPT_HEADERS,'template':'script','rows':[
            [f'{product}-{i:02d}' if product else '',text,reference,options.required_time.strip(),options.completion.strip()]
            for i,_,text in selected]}
    requirements=options.shot_requirements.strip()
    if not requirements and 'shot_requirements' not in options.model_fields_set:
        suggestions=[]
        for i,_,_ in selected:
            for segment in batch['variants'][i-1].get('production_segments',[]):
                suggestion=str(segment.get('screen_suggestion') or '').strip()
                if suggestion and suggestion not in suggestions:suggestions.append(suggestion)
        if suggestions:requirements='【脚本生成的拍摄建议，待确认】\n'+'\n'.join(suggestions)
    return {'headers':SHOOTING_HEADERS,'template':'shooting','rows':[[product,options.quantity,reference,
        requirements,options.shot_reference_1.strip(),options.shot_reference_2.strip(),
        options.required_time.strip(),options.completion.strip()]]}


def export_workbook(item, request):
    root=Path(__file__).resolve().parents[1]
    node=shutil.which('node')
    if not node or not (root/'client/node_modules/@oai/artifact-tool').exists():
        from client.xlsx_portable import build_workbook
        return build_workbook(table_payload(item,request)),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    with tempfile.TemporaryDirectory(prefix='studio-xlsx-') as folder:
        path=Path(folder)/'narrations.xlsx'
        try:
            result=subprocess.run([node,str(root/'client/export_workbook.mjs'),str(path)],
                input=json.dumps(table_payload(item,request),ensure_ascii=False),
                text=True,encoding='utf-8',capture_output=True,timeout=180,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise ValueError('Excel 导出未完成，请减少所选条数后重试。') from exc
        if result.returncode or not path.exists():
            raise ValueError('Excel 导出组件运行失败，请检查本机表格运行环境。')
        return path.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def export_narrations(item, request):
    _,rows=narration_rows(item,request)
    if request.format=='xlsx':return export_workbook(item,request)
    if request.format == 'txt':
        # Headers are for the human-readable collection only, never individual narration files.
        body = '\n\n\n'.join(f'【{i:02d} · {title}】\n\n{text}' for i, title, text in rows)
        return (body + '\n').encode('utf-8-sig'), 'text/plain; charset=utf-8'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for i, title, text in rows:
            safe_title=re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', title).strip(' .')[:65] or '文案'
            archive.writestr(f'{i:02d}_{safe_title}.txt', (text + '\n').encode('utf-8-sig'))
    return output.getvalue(), 'application/zip'
