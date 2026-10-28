"""Read-only public GitHub release checks; never sends local settings or files."""
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

REPOSITORY = 'ASK-022/video-copy-studio-skill'


def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):
        raise ValueError('版本号格式无效。')
    return tuple(map(int,value.split('.')))


def local_version(root=None):
    root = Path(root) if root else Path(__file__).resolve().parents[3]
    value=(root/'VERSION').read_text(encoding='utf-8').strip()
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


def check_update(current):
    request=urllib.request.Request(f'https://api.github.com/repos/{REPOSITORY}/releases/latest',
        headers={'User-Agent':'VideoCopyStudio-Update','Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request,timeout=20) as response:raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('更新信息过大，请稍后重试。')
        return describe_release(json.loads(raw),current)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'GitHub 更新检查失败（HTTP {exc.code}），请稍后重试；不影响本机使用。') from exc
    except (OSError,urllib.error.URLError) as exc:
        raise ValueError('暂时无法连接 GitHub，请检查网络后重试；不影响本机使用。') from exc
