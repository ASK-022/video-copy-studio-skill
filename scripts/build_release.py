"""Build an allowlisted, credential-free release ZIP and its SHA256 sidecar."""
import argparse
import sys
import hashlib
import json
from pathlib import Path
import re
import zipfile

TOP={'SKILL.md','VERSION','README.md','THIRD_PARTY_NOTICES.md','release.json','install.ps1','agents','references','scripts','assets','tests','.github','.gitignore'}
SKIP={'.git','.venv','node_modules','__pycache__','.studio','dist'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=Path('dist'));args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];version=(root/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('VERSION 必须为三段版本号。')
    bootstrap_assets={
        'python-3.12.10.nupkg':'0eb85c2dfccccf1b17352de4c397f69194035b7d37149eacc16f1147d93de3b8',
        'video-transcriber-pinned.zip':'3ee582c0b0b906769b9e0736965b7d715ab359fd82d5bcaabf87a5d44e042d08',
    }
    for name,digest in bootstrap_assets.items():
        path=root/'assets/bootstrap'/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('内置安装资源缺失或校验失败：'+name)
    files=[]
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if relative.parts[0] not in TOP or any(part in SKIP for part in relative.parts) or path.suffix in ('.pyc','.log') or path.is_dir():continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('发布包不能包含符号链接。')
        if path.name in ('.env','runtime.json','providers.json','ai.json','feishu.json','tikhub.json','cue.json','job.json'):raise ValueError('发布包包含运行时配置：'+str(relative))
        raw=path.read_bytes()
        if path.suffix in ('.py','.ps1','.json','.md','.js','.html','.yaml','.yml','.txt','.mjs'):
            text=raw.decode('utf-8')
            if re.search(r'\bsk-[A-Za-z0-9]{20,}\b|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}',text):raise ValueError('发布包发现疑似密钥：'+str(relative))
        files.append((relative,raw))
    args.output.mkdir(parents=True,exist_ok=True);target=args.output/f'video-copy-studio-v{version}.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as output:
        for relative,raw in files:output.writestr('video-copy-studio/'+relative.as_posix(),raw)
    digest=hashlib.sha256(target.read_bytes()).hexdigest();target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n',encoding='ascii')
    print(json.dumps({'archive':str(target.resolve()),'sha256':digest,'files':len(files),'bytes':target.stat().st_size},ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
