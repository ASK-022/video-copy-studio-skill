"""Read-only public GitHub release checks; never sends local settings or files."""
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from client.update_trust import MANIFEST_URLS,public_get,verify

REPOSITORY = 'ASK-022/video-copy-studio-skill'


def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):
        raise ValueError('版本号格式无效。')
    return tuple(map(int,value.split('.')))


def local_version(root=None):
    if root is None:
        candidates=(Path(__file__).resolve().parents[3]/'VERSION',Path(__file__).parent/'VERSION')
        path=next((p for p in candidates if p.is_file()),candidates[0])
    else:path=Path(root)/'VERSION'
    value=path.read_text(encoding='utf-8').strip()
    version_tuple(value)
    return value


def describe_release(release,current):
    version_tuple(current)
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('更新源不是正式版本。')
    tag=release.get('tag_name','')
    if not re.fullmatch(r'v\d+\.\d+\.\d+',tag):raise ValueError('正式版本标签无效。')
    latest=tag[1:]
    prefix=f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
    expected=f'video-copy-studio-{tag}.zip'
    assets={a.get('name'):a for a in release.get('assets',[]) if isinstance(a,dict)}
    for name in (expected,expected+'.sha256'):
        asset=assets.get(name,{})
        if asset.get('browser_download_url') != prefix+name:
            raise ValueError('正式版缺少有效的安装包或 SHA256 文件。')
    exe=f'VideoCopyStudio-Setup-{tag}.exe'
    setup_url=prefix+exe if assets.get(exe,{}).get('browser_download_url')==prefix+exe else ''
    return {'current':current,'latest':latest,'update_available':version_tuple(latest)>version_tuple(current),
        'release_url':f'https://github.com/{REPOSITORY}/releases/tag/{tag}',
        'notes':str(release.get('body') or '')[:12000],'setup_url':setup_url,'tag':tag}


def signed_update(current):
    version_tuple(current)
    def fetch(url):
        try:
            envelope=json.loads(public_get(url,128*1024));payload=verify(envelope)
            return (payload,envelope,url)
        except (OSError,ValueError):return None
    with ThreadPoolExecutor(max_workers=len(MANIFEST_URLS)) as pool:
        results=[item for item in pool.map(fetch,MANIFEST_URLS) if item]
    if not results:raise ValueError('暂时无法连接版本清单镜像和 GitHub，请稍后重试；不影响本机使用。')
    payload,envelope,url=max(results,key=lambda item:version_tuple(item[0]['version']))
    latest=payload['version']
    return {'current':current,'latest':latest,'update_available':version_tuple(latest)>version_tuple(current),
        'release_url':f'https://github.com/{REPOSITORY}/releases/tag/v{latest}',
        'setup_url':f'https://github.com/{REPOSITORY}/releases/download/v{latest}/VideoCopyStudio-Setup-v{latest}.exe',
        'tag':'v'+latest,'notes':str(payload.get('notes',''))[:12000],'source':url,
        'signature_verified':True,'compatible':version_tuple(current)>=version_tuple(payload['min_version']),
        'package_bytes':payload['package']['bytes'],'envelope':envelope}


def check_update(current):
    try:return signed_update(current)
    except ValueError:pass
    # Read-only fallback supports old releases. Unsigned API results cannot be applied.
    request=urllib.request.Request(f'https://api.github.com/repos/{REPOSITORY}/releases/latest',
        headers={'User-Agent':'VideoCopyStudio-Update','Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request,timeout=20) as response:raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('更新信息过大，请稍后重试。')
        return dict(describe_release(json.loads(raw),current),signature_verified=False,compatible=False,source='GitHub API')
    except urllib.error.HTTPError as exc:
        raise ValueError(f'GitHub 更新检查失败（HTTP {exc.code}），请稍后重试；不影响本机使用。') from exc
    except (OSError,urllib.error.URLError) as exc:
        raise ValueError('暂时无法连接 GitHub，请检查网络后重试；不影响本机使用。') from exc
