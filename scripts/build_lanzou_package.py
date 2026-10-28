"""Wrap tested offline archives in genuine ZIPs below the account's 100 MB limit."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from offline_setup import VERSION,digest,manifest as original_manifest

ROOT=Path(__file__).resolve().parents[1]
CHUNK=99_000_000
VCREDIST_SHA256='843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c'


def wrap_archive(source,output,index,chunk_size=CHUNK):
    pieces=[];offset=0
    with source.open('rb') as stream:
        while offset<source.stat().st_size:
            name=f'VideoCopyStudio-Offline-v{VERSION}-data{index:03d}.zip';target=output/name
            length=min(chunk_size,source.stat().st_size-offset)
            with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as archive:
                with archive.open('payload.bin','w',force_zip64=True) as payload:
                    remaining=length
                    while remaining:
                        block=stream.read(min(4*1024*1024,remaining))
                        if not block:raise ValueError('来源资源提前结束。')
                        payload.write(block);remaining-=len(block)
                archive.writestr('README.txt','文案工坊完整离线资源分包。请与安装器放在同一目录，无需单独解压。\n')
            if target.stat().st_size>=100_000_000:raise ValueError('小分包超过 100 MB 上限。')
            pieces.append({'name':name,'archive':source.name,'offset':offset,'payload_bytes':length,'bytes':target.stat().st_size,'sha256':digest(target)})
            print('Prepared '+name,flush=True);offset+=length;index+=1
    return pieces


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    source=args.input.resolve();output=args.output.resolve();work=args.work.resolve()
    if output.exists():raise ValueError('输出目录已存在，请指定新的蓝奏云分发目录。')
    original=original_manifest(source)
    if original.get('version')!=VERSION:raise ValueError('来源离线包版本不一致。')
    output.mkdir(parents=True);work.mkdir(parents=True,exist_ok=True);pieces=[]
    for item in original['parts']:
        path=source/item['name']
        if path.stat().st_size!=item['bytes'] or digest(path)!=item['sha256']:raise ValueError('来源离线包校验失败。')
        pieces+=wrap_archive(path,output,len(pieces)+1)
    description={'format':'video-copy-studio-lanzou/v1','version':VERSION,'original':original,'pieces':pieces}
    manifest=work/f'lanzou-downloads-v{VERSION}.json';manifest.write_text(json.dumps(description,ensure_ascii=False,indent=2),encoding='utf-8')
    name='VideoCopyStudio-Lanzou-Offline-Setup-v'+VERSION
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx','--name',name,
        '--distpath',str(output),'--workpath',str(work/'freeze'),'--specpath',str(work),
        '--add-data',str(ROOT/'VERSION')+os.pathsep+'.','--add-data',str(manifest)+os.pathsep+'.',str(ROOT/'scripts/lanzou_setup.py')],check=True)
    if (source/'VC_redist.x64.exe').is_file():
        if digest(source/'VC_redist.x64.exe')!=VCREDIST_SHA256:raise ValueError('微软运行库与本版已验证的官方文件不匹配。')
        shutil.copy2(source/'VC_redist.x64.exe',output/'VC_redist.x64.exe')
    (output/'先读我-离线安装说明.txt').write_text(f'文案工坊 v{VERSION} 蓝奏云完整离线版（AI辅助开发）\n\n请下载本文件夹全部 {len(pieces)} 个 data*.zip 资源分包和 Lanzou-Offline-Setup.exe，保持原名放在同一目录，不必手工解压。\n新电脑可先运行微软官方 VC_redist.x64.exe 准备 C++ x64 运行库；已有更新版本可关闭，按微软界面处理权限或重启提示。\n双击 Lanzou-Offline-Setup.exe，选择位置，等待自动校验、合并、解压完成后打开客户端。以后双击解压目录内的 VideoCopyStudio.exe。安装时建议预留 12 GB 空间。\n本地视频/音频转写可断网；AI改写、链接解析、飞书和检查更新仍需联网及自己的服务配置。\n这是蓝奏云的小分包版本，勿与 GitHub 的 4 个大 ZIP 分包混放。SHA256 校验清单已内置安装器，同目录 TXT 校验表便于人工核对。\n微软运行库来源：https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist\n',encoding='utf-8-sig')
    files=sorted(path for path in output.iterdir() if path.is_file())
    (output/'SHA256SUMS.txt').write_text(''.join(digest(path)+'  '+path.name+'\n' for path in files),encoding='utf-8')
    print(json.dumps({'output':str(output),'pieces':len(pieces),'bytes':sum(path.stat().st_size for path in output.iterdir())},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
