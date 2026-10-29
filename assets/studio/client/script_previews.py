"""Durable local intake drafts; importing requires explicit confirmation."""
import copy
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import uuid


def suggest_parts(text,title):
    # Only explicit script headings qualify, not every numbered selling point.
    pattern=r'(?m)^[ \t]*(?:(?:脚本|文案)[ \t]*[一二三四五六七八九十\d]+|第[一二三四五六七八九十\d]+[条篇份](?:脚本|文案)?)[^\n]{0,60}$'
    matches=list(re.finditer(pattern,text))
    if len(matches)<2:return [{'title':title,'text':text}]
    starts=[m.start() for m in matches];starts[0]=0
    return [{'title':matches[i].group().strip()[:160] or f'{title} · {i+1}','text':text[start:starts[i+1] if i+1<len(starts) else len(text)].strip()} for i,start in enumerate(starts)]


class PreviewStore:
    def __init__(self,root):
        self.root=Path(root)/'script-previews';self.root.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.records={}
        for path in self.root.glob('*/preview.json'):
            try:
                row=json.loads(path.read_text(encoding='utf-8'));self.records[row['id']]=row
                if row['status'] in ('queued','working'):self.update(row['id'],status='error',error='读取已中断，请重新上传。')
            except (ValueError,KeyError):pass

    def folder(self,id):
        if not re.fullmatch(r'[a-f0-9]{32}',id):raise ValueError('预览编号无效。')
        return self.root/id

    def create(self,title):
        with self.lock:
            id=uuid.uuid4().hex;self.folder(id).mkdir()
            self.records[id]={'id':id,'title':title[:160],'status':'queued','message':'准备在本机读取正文…','error':'','created':time.time(),'source_text':'','parts':[],'jobs':[]}
            return self.update(id)

    def get(self,id):
        with self.lock:
            if id not in self.records:raise ValueError('导入预览不存在。')
            return copy.deepcopy(self.records[id])

    def update(self,id,**values):
        with self.lock:
            row=self.records[id];row.update(values,updated=time.time());path=self.folder(id)/'preview.json'
            temp=path.with_suffix('.tmp');temp.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
            return copy.deepcopy(row)

    def active(self):
        with self.lock:return sum(row['status'] in ('queued','working') for row in self.records.values())

    @staticmethod
    def digest(payload):return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
