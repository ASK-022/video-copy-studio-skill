"""Reassemble independent program/resource pieces, then install entirely offline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import zipfile
import contenthub_offline_setup as core
from contenthub_progress import Meter,file_sha


def validate(item):
    name=item.get('name','')
    if not name or Path(name).name!=name or any(c in name for c in ('/',chr(92),':')):raise ValueError('离线包文件名无效')
    if not 0<item.get('bytes',0)<8*1024**3 or len(item.get('sha256',''))!=64:raise ValueError('离线包大小或校验值无效')
    parts=item.get('parts',[])
    if not parts or len(parts)>100 or sum(p['bytes'] for p in parts)!=item['bytes']:raise ValueError('分包长度与清单不匹配')
    seen=set()
    for part in parts:
        if Path(part['name']).name!=part['name'] or any(c in part['name'] for c in ('/',chr(92),':')) or part['name'] in seen:raise ValueError('分包文件名无效或重复')
        if not 0<part['bytes']<100_000_000 or len(part.get('sha256',''))!=64:raise ValueError('分包校验值无效')
        seen.add(part['name'])
    return item


def load_manifest(directory=None):
    root=core.FILES if getattr(sys,'frozen',False) else Path(directory or Path.cwd())
    data=json.loads((root/'contenthub-offline-cloud.json').read_text(encoding='utf-8'))
    if data.get('format')!='contenthub/offline-cloud/v1':raise ValueError('完整离线分包格式无效')
    validate(data['program']);validate(data['resources']);return data


def assemble(directory,item,emit):
    validate(item);directory=Path(directory).resolve();target=directory/item['name']
    if target.is_file() and target.stat().st_size==item['bytes'] and file_sha(target)==item['sha256']:
        emit('cached',file=item['name'],total=item['bytes'],source='本机已校验资源，无需重新合并');return target
    temporary=directory/(item['name']+'.'+secrets.token_hex(6)+'.partial');whole=hashlib.sha256();done=0
    meter=Meter(emit,item['bytes'])
    try:
        with temporary.open('xb') as output:
            for index,part in enumerate(item['parts'],1):
                source=directory/part['name'];meter.context={'file':f"{part['name']}（{index}/{len(item['parts'])}）"}
                if not source.is_file():raise ValueError('缺少分包：'+part['name']+'。请把全部 ZIP 分包与安装器放在同一文件夹。')
                digest=hashlib.sha256();size=0
                with zipfile.ZipFile(source) as archive:
                    entries=archive.infolist()
                    if len(entries)!=1 or entries[0].filename!=part['entry'] or entries[0].file_size!=part['bytes']:raise ValueError('分包结构不匹配：'+part['name'])
                    with archive.open(entries[0]) as incoming:
                        for block in iter(lambda:incoming.read(1024**2),b''):
                            size+=len(block);done+=len(block)
                            if size>part['bytes'] or done>item['bytes']:raise ValueError('分包数据超出声明长度')
                            output.write(block);digest.update(block);whole.update(block);meter.update(done)
                if size!=part['bytes'] or digest.hexdigest()!=part['sha256']:raise ValueError('分包校验失败，请重新下载：'+part['name'])
        if done!=item['bytes'] or whole.hexdigest()!=item['sha256']:raise ValueError('完整离线资源总校验失败')
        meter.update(done,True)
        if target.exists():os.replace(target,target.with_name(target.name+'.invalid-'+secrets.token_hex(6)))
        os.replace(temporary,target);return target
    finally:temporary.unlink(missing_ok=True)


def prepare(directory,emit):
    manifest=load_manifest(directory);paths={}
    for index,key in enumerate(('program','resources'),1):
        emit('phase',index=index,steps=6,name='校验并合并程序分包' if key=='program' else '校验并合并独立资源 '+manifest['resource_revision'])
        emit('source',source='本机已下载离线分包（不联网）',attempt=1,attempts=1,file=manifest[key]['name'])
        paths[key]=assemble(directory,manifest[key],emit)
    return paths


def install(directory,root,profile,emit,**kwargs):
    prepare(directory,emit)
    def forward(kind,**fields):
        if kind=='phase':fields={**fields,'index':fields['index']+2,'steps':6}
        emit(kind,**fields)
    return core.install(directory,root,profile,forward,**kwargs)


def main():
    if '--verify-parts' in sys.argv:
        parser=argparse.ArgumentParser();parser.add_argument('--verify-parts',type=Path,required=True);parser.add_argument('--result',type=Path,required=True);args=parser.parse_args()
        args.result=args.result.resolve();args.result.parent.mkdir(parents=True,exist_ok=True)
        sys.stdout=args.result.with_suffix('.log').open('a',encoding='utf-8',buffering=1);sys.stderr=sys.stdout
        try:
            paths=prepare(args.verify_parts,lambda kind,**fields:print(json.dumps({'kind':kind,**fields},ensure_ascii=False),flush=True))
            result={'ok':True,'program_sha256':file_sha(paths['program']),'resources_sha256':file_sha(paths['resources']),'resource_revision':load_manifest(args.verify_parts)['resource_revision']}
        except Exception as error:
            import traceback
            traceback.print_exc();result={'ok':False,'error':str(error)}
        args.result.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return 0 if result['ok'] else 1
    manifest=load_manifest();count=len(manifest['program']['parts'])+len(manifest['resources']['parts'])
    return core.main(installer=install,package_note=f'请先把本版全部 {count} 个 ZIP 分包与本安装器放在同一文件夹，无需手动解压。资源 {manifest["resource_revision"]} 已包含全部本地模型和运行环境，安装及本地转写不联网。')


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:
        if sys.stderr:print(str(error),file=sys.stderr)
        if '--verify-parts' not in sys.argv:core.messagebox.showerror('内容中台完整离线安装',str(error))
        sys.exit(1)
