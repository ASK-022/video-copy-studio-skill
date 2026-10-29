"""Build a resource-free client ZIP and canonical payload for external signing.

First run creates payload.json. Sign its exact bytes with the publisher RSA-3072
key (PKCS#1 v1.5 SHA256); rerun with --signature to create update.json.
Private signing keys must never be placed in this repository.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/studio'))
from client.update_trust import canonical,CDNS,REPOSITORY,verify
from build_release import TOP,SKIP


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--launcher',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--signature',type=Path);args=parser.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=True);version=(ROOT/'VERSION').read_text().strip()
    name=f'client-v{version}.zip';target=out/name
    if not args.signature:
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for source in sorted(ROOT.rglob('*')):
                relative=source.relative_to(ROOT)
                if relative.parts[0] not in TOP or any(p in SKIP for p in relative.parts) or not source.is_file() or source.suffix in ('.log','.pyc'):continue
                if relative.parts[:2]==('assets','bootstrap'):continue
                if source.is_symlink() or source.name in ('.env','runtime.json','providers.json','feishu.json','job.json'):raise ValueError('更新源含私有配置或链接。')
                archive.write(source,'App/'+relative.as_posix())
            archive.write(args.launcher,'VideoCopyStudio.exe')
            archive.writestr('offline-client.json',json.dumps({'format':'video-copy-studio-offline/v1','version':version,'platform':'windows-x64','resource_contract':1}))
        if target.stat().st_size>=20*1024*1024:raise ValueError('程序增量超过 CDN 的 20MB 限制。')
        payload={'format':'video-copy-studio-update/v1','repository':REPOSITORY,'version':version,'min_version':'1.1.3','resource_contract':1,
            'notes':'新增客户端一键更新、启动失败回滚和中断恢复；国内直连版本清单镜像优先。更新只替换程序，保留资料和 Key，继续使用本机模型及运行环境。',
            'package':{'name':name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                'urls':[f'{host}/gh/{REPOSITORY}@v{version}/releases/files/{name}' for host in CDNS]+[f'https://github.com/{REPOSITORY}/releases/download/v{version}/{name}']}}
        (out/'payload.json').write_bytes(canonical(payload))
    else:
        payload=json.loads((out/'payload.json').read_text(encoding='utf-8'))
        if hashlib.sha256(target.read_bytes()).hexdigest()!=payload['package']['sha256']:raise ValueError('签名前后的 ZIP 变化。')
        envelope={'payload':payload,'signature':base64.b64encode(args.signature.read_bytes()).decode('ascii')}
        verify(envelope);(out/'update.json').write_bytes(canonical(envelope))
    print(json.dumps({'package':str(target),'bytes':target.stat().st_size},ensure_ascii=False))


if __name__=='__main__':main()
