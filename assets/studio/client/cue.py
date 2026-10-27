"""Cue remote evidence adapter. Used only when explicitly selected for a public link."""
import json
from pathlib import Path
import time
import httpx
from client.security import unseal
from client.media import extract_url, safe_url

ENDPOINT='https://mcp.cuecue.cn/api/omni-reader/mcp/'


def legacy_key():
    path=Path.home()/'.cue/config.json'
    if not path.exists():return ''
    return json.loads(path.read_text(encoding='utf-8-sig')).get('api_key','').strip()


def key_for(root):
    path=root/'cue.json'
    if not path.exists():raise ValueError('请在设置中连接 Cue，或选择本机 OCR。')
    data=json.loads(path.read_text(encoding='utf-8'))
    if not data.get('encrypted_key'):raise ValueError('Cue 尚未配置 Key。')
    return unseal(data['encrypted_key'])


def call(key,name,args):
    with httpx.Client(timeout=65) as client:
        r=client.post(ENDPOINT,headers={'Authorization':'Bearer '+key,'Accept':'application/json, text/event-stream'},
          json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})
    if r.status_code>=400:raise RuntimeError(f'Cue 返回 HTTP {r.status_code}，请检查 Key 和服务状态。')
    candidates=[r.text] if r.text.lstrip().startswith('{') else [s[5:].strip() for s in r.text.splitlines() if s.startswith('data:')]
    for raw in candidates:
        try:env=json.loads(raw)
        except ValueError:continue
        if env.get('error'):raise RuntimeError('Cue 请求未被接受，请检查服务配置。')
        if 'result' not in env:continue
        result=env['result'];content='\n'.join(c.get('text','') for c in result.get('content',[]) if c.get('type')=='text')
        try:data=json.loads(content)
        except ValueError:data={'text':content}
        if result.get('isError'):
            if 'INSUFFICIENT_CREDITS' in content:raise RuntimeError('Cue 积分不足，请到 Cue 控制台补充额度，或改用本机 OCR。')
            raise RuntimeError('Cue 解析失败；可稍后重试或改用本机 OCR。')
        return data
    raise RuntimeError('Cue 未返回有效结果。')


def parse(key,source,notify):
    source=extract_url(source);safe_url(source)
    if httpx.URL(source).host=='v.douyin.com':
        r=httpx.get(source,headers={'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'},follow_redirects=True,timeout=25)
        source=str(r.url);safe_url(source)
    state=call(key,'parse',{'source':source,'detail':'text','output':'markdown','wait':False})
    op=state.get('operation_id');deadline=time.monotonic()+900
    while state.get('status') in ('processing','queued','pending'):
        if not op or time.monotonic()>deadline:raise RuntimeError('Cue 解析超时，可稍后重试；本机结果已保留。')
        notify('Cue 正在解析公开链接的画面与文字…')
        time.sleep(min(15,max(1,state.get('poll_after_seconds',10) or 10)))
        state=call(key,'get_parse_status',{'operation_id':op,'wait_ms':20000})
    result=state.get('result');text=result if isinstance(result,str) else (result or {}).get('text','')
    if state.get('status')!='completed' or not text:raise RuntimeError('Cue 未完成解析，请检查公开链接是否可访问。')
    return {'text':text,'operation_id':op,'billing':state.get('billing',{})}
