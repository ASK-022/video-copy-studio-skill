"""Pinned publisher signature and bounded public downloads. No account data is sent."""
import base64
import hashlib
import hmac
import json
import re
import time
import urllib.request
from urllib.parse import urlsplit

REPOSITORY='ASK-022/video-copy-studio-skill'
CDNS=('https://fastly.jsdelivr.net','https://gcore.jsdelivr.net')
MANIFEST_URLS=tuple(f'{host}/gh/{REPOSITORY}@main/releases/latest.json' for host in CDNS)+(f'https://raw.githubusercontent.com/{REPOSITORY}/main/releases/latest.json',)
MODULUS='tnXHDkOdxXriwMJuqoEPn3uEQfoUTnrGHJ7TE344GrybKoHJ/SPFUmKZAgkipCzqxLbU9Hh8nR0eAQthgr8PDv5NUKdvpoEz0dEwUv+9TxUa6qTzIpD0zwO8++NLvWpqBCfshG6BciwAn1McogBwRhZ93KL3p0yKchrMiC9qoHJfQmU3ZSF3OX/LOvauRRAlqvWZQKEUXV6VRN8pFPzouv2zOLS3Y4kiAaF2nHLjjLbAGkQrJ2pVAKR0XLMf2okdmTwgUWmrYs63tyA9kHp0P3taSMxWoZ1AmjrxTFdCQogmgV+uHx/0AlX4ZG0vKlVyrqqQyLHgvpCS1iH9C6iMxKupOG/AN0mZxjzoZcBKtb+yRgITWw0waypPnq7jSbPCNrcXCHK5TM9i3ZInp8Uwd0x466arOwO/hR+W237aBdENzp4ZaAolUXrauuC0jaahQtb5QMLZYMnc4ysyGV3gCveGh+3bagdbkOnEWCcRP2IgfJo+hHHUvy4lyVDu0FI9'
MAX_PACKAGE=60*1024*1024


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')


def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,5}\.\d{1,5}\.\d{1,5}',value):raise ValueError('版本号格式无效。')
    return tuple(map(int,value.split('.')))


def verify(envelope):
    try:
        payload=envelope['payload'];signature=base64.b64decode(envelope['signature'],validate=True)
        modulus=int.from_bytes(base64.b64decode(MODULUS),'big');size=(modulus.bit_length()+7)//8
        if len(signature)!=size or int.from_bytes(signature,'big')>=modulus:raise ValueError()
        encoded=pow(int.from_bytes(signature,'big'),65537,modulus).to_bytes(size,'big')
        digest_info=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(canonical(payload)).digest()
        expected=b'\0\1'+b'\xff'*(size-len(digest_info)-3)+b'\0'+digest_info
        if not hmac.compare_digest(encoded,expected):raise ValueError()
        if payload['format']!='video-copy-studio-update/v1' or payload['repository']!=REPOSITORY:raise ValueError()
        latest=payload['version'];version(latest);version(payload['min_version'])
        if payload['resource_contract']!=1:raise ValueError('新版需要不同的运行资源，请使用完整安装包。')
        package=payload['package'];name=f'client-v{latest}.zip'
        if package['name']!=name or not re.fullmatch('[0-9a-f]{64}',package['sha256']):raise ValueError()
        if type(package['bytes']) is not int or not 1<=package['bytes']<=MAX_PACKAGE:raise ValueError()
        expected_urls=[f'{host}/gh/{REPOSITORY}@v{latest}/releases/files/{name}' for host in CDNS]
        expected_urls+=[f'https://github.com/{REPOSITORY}/releases/download/v{latest}/{name}']
        if package['urls']!=expected_urls:raise ValueError()
        return payload
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        raise ValueError('更新清单签名或内容校验失败，请使用官方发布包。') from exc


def public_get(url,limit,timeout=6):
    request=urllib.request.Request(url,headers={'User-Agent':'VideoCopyStudio-Update','Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=timeout) as response:raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('更新信息超出大小限制。')
    return raw


def download(payload,target,emit=lambda *_:None):
    item=payload['package'];errors=[]
    for index,url in enumerate(item['urls']):
        try:
            emit(f'正在下载程序增量（线路 {index+1}/{len(item["urls"])}），复用本机模型…')
            request=urllib.request.Request(url,headers={'User-Agent':'VideoCopyStudio-Update'})
            digest=hashlib.sha256();received=0;deadline=time.monotonic()+120
            with urllib.request.urlopen(request,timeout=12) as response,target.open('wb') as output:
                while True:
                    block=response.read(256*1024)
                    if not block:break
                    received+=len(block)
                    if received>item['bytes'] or time.monotonic()>deadline:raise ValueError('下载超时或大小不匹配。')
                    output.write(block);digest.update(block)
            if received!=item['bytes'] or digest.hexdigest()!=item['sha256']:raise ValueError('下载包 SHA256 校验失败。')
            return
        except (OSError,ValueError) as exc:
            errors.append(str(exc));target.unlink(missing_ok=True)
    raise ValueError('各下载线路均未完成，请重试或从蓝奏云下载升级器。'+errors[-1][:160])
