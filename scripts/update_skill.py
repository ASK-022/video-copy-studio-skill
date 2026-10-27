"""Read GitHub release metadata, then explicitly update from its verified skill ZIP."""
import argparse
import sys
import hashlib
import json
from pathlib import Path
import re
import tempfile
import urllib.request
import zipfile

from install_skill import install


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'video-copy-studio-updater/1.0','Accept':'application/vnd.github+json'}),timeout=60) as response:return response.read()


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo');parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    manifest=json.loads((root/'release.json').read_text(encoding='utf-8'));repo=args.repo or manifest.get('repository')
    if not repo or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('请用 --repo GitHub账号/仓库名 指定已发布的仓库。')
    release=json.loads(fetch('https://api.github.com/repos/'+repo+'/releases/latest'))
    assets={item['name']:item for item in release.get('assets',[])}
    package=next((a for n,a in assets.items() if re.fullmatch(r'video-copy-studio-v[0-9.]+\.zip',n)),None)
    if not package:raise ValueError('此 Release 没有团队 Skill ZIP；请使用带正式发布附件的版本。')
    checksum=assets.get(package['name']+'.sha256')
    if not checksum:raise ValueError('此 Release 缺少 SHA256 校验文件，未更新。')
    current=(root/'VERSION').read_text().strip();version=release['tag_name'].removeprefix('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('最新 Release 版本号格式无效。')
    available=tuple(map(int,current.split('.')))<tuple(map(int,version.split('.')))
    result={'current':current,'latest':version,'update_available':available,'release_url':release['html_url']}
    if not args.apply or not available:print(json.dumps(result,ensure_ascii=False));return
    # Download only release assets hosted by GitHub, never arbitrary redirect URLs in metadata.
    for asset in (package,checksum):
        if not asset['browser_download_url'].startswith(f'https://github.com/{repo}/releases/download/'):
            raise ValueError('Release 附件地址不匹配，未更新。')
    raw=fetch(package['browser_download_url']);expected=fetch(checksum['browser_download_url']).decode().split()[0]
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('SHA256 不匹配，未更新。')
    with tempfile.TemporaryDirectory(prefix='studio-skill-update-') as temp:
        archive=Path(temp)/'skill.zip';archive.write_bytes(raw)
        with zipfile.ZipFile(archive) as source:
            for item in source.infolist():
                path=Path(temp)/item.filename
                if not path.resolve().is_relative_to(Path(temp).resolve()) or '\\' in item.filename:
                    raise ValueError('压缩包包含无效路径，未更新。')
            source.extractall(temp)
        result.update(install(Path(temp)/'video-copy-studio',root.parent,True))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
