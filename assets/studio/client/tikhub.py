"""TikHub public Douyin URL resolver. Credentials go only to the fixed API origin."""
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from client.media import extract_url, stream_download
from client.security import unseal

ENDPOINT='https://api.tikhub.io/api/v1/douyin/app/v3/fetch_one_video_by_share_url'


def config_path(state):
    return Path(state)/'tikhub.json'


def key_from_config(state):
    path=config_path(state)
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not data.get('encrypted_key'):
        raise ValueError('请先打开 TikHub 设置，填写单独的 TikHub API Key。')
    return unseal(data['encrypted_key'])


def video_candidates(payload):
    data=payload.get('data',{})
    items=[]
    def visit(node):
        if isinstance(node,list):
            for child in node[:30]:visit(child)
        elif isinstance(node,dict):
            if isinstance(node.get('video'),dict):items.append(node)
            for key in ('aweme_detail','aweme_details','aweme_list','item_list','items','data'):
                if key in node:visit(node[key])
    visit(data)
    if not items:
        raise ValueError('TikHub 未返回公开视频数据，可能是内容不可用、私密或接口暂不可用。')
    item=items[0];video=item['video'];urls=[]
    for field in ('play_addr','play_addr_h264','play_addr_265','download_addr'):
        block=video.get(field,{})
        if isinstance(block,dict):urls.extend(block.get('url_list',[]))
    for bitrate in video.get('bit_rate',[]):
        if isinstance(bitrate,dict):urls.extend(bitrate.get('play_addr',{}).get('url_list',[]))
    urls=list(dict.fromkeys(u for u in urls if isinstance(u,str) and u.startswith(('https://','http://'))))
    if not urls:
        raise ValueError('TikHub 返回了作品信息，但没有可下载的视频地址；图文作品暂不支持转写。')
    return {'urls':urls,'title':str(item.get('desc',''))[:300],'video_id':str(item.get('aweme_id',''))}


class TikHubClient:
    def __init__(self,key):self.key=key

    def resolve(self,share_text):
        url=extract_url(share_text);host=(urlparse(url).hostname or '').lower()
        if not (host in ('douyin.com','iesdouyin.com') or host.endswith(('.douyin.com','.iesdouyin.com'))):
            raise ValueError('TikHub 测试入口目前支持抖音分享链接。')
        start=time.monotonic()
        try:
            with httpx.Client(timeout=httpx.Timeout(60,connect=15),trust_env=False) as client:
                response=client.get(ENDPOINT,params={'share_url':url},headers={'Authorization':'Bearer '+self.key})
            if response.status_code>=400:
                raise ValueError(f'TikHub HTTP {response.status_code}，请检查 API Key、余额或接口状态。')
            payload=response.json()
            if payload.get('code',200) not in (0,200):
                raise ValueError('TikHub 返回业务错误，请检查余额和链接可访问性。')
            result=video_candidates(payload)
            result.update(elapsed_seconds=round(time.monotonic()-start,2),
                          request_id=str(payload.get('request_id',''))[:120])
            return result
        except httpx.HTTPError as exc:
            raise ValueError('TikHub 连接失败或超时，请检查网络后重试。') from exc

    def download(self,share_text,directory,progress):
        progress('TikHub 正在解析抖音分享链接…')
        result=self.resolve(share_text)
        target=Path(directory)/'source.mp4'
        progress('TikHub 解析成功，正在下载视频…')
        for url in result['urls'][:3]:
            try:
                return stream_download(url,target,'https://www.douyin.com/')
            except (ValueError,httpx.HTTPError):
                continue
        raise ValueError('TikHub 已返回播放地址，但下载未成功，可能已失效或被媒体站点拒绝。')
