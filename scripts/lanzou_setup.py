"""Reassemble standard small ZIP resources, then use the verified offline extractor."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile
import offline_setup as base

VERSION=base.VERSION
SOURCE=Path(__file__).resolve().parents[1]
LIMIT=100_000_000


def load_manifest(path=None):
    path=Path(path) if path else Path(getattr(sys,'_MEIPASS',SOURCE))/f'lanzou-downloads-v{VERSION}.json'
    value=json.loads(path.read_text(encoding='utf-8'))
    if value.get('format')!='video-copy-studio-lanzou/v1' or value.get('version')!=VERSION:raise ValueError('蓝奏云分包版本或清单不匹配。')
    original=value.get('original',{})
    if original.get('format')!='video-copy-studio-offline-downloads/v1' or original.get('version')!=VERSION or original.get('client_dir')!='VideoCopyStudio-Offline-v'+VERSION:
        raise ValueError('原始资源清单无效。')
    archives={}
    for item in original.get('parts',[]):
        name=item.get('name','')
        if not re.fullmatch(r'VideoCopyStudio-Offline-v'+re.escape(VERSION)+r'-part[0-9]+\.zip',name) or name in archives:
            raise ValueError('原始分包路径无效或重复。')
        if not re.fullmatch(r'[a-f0-9]{64}',item.get('sha256','')) or not isinstance(item.get('bytes'),int) or item['bytes']<=0:
            raise ValueError('原始分包校验值无效。')
        archives[name]=item
    pieces=value.get('pieces',[]);names=set();offsets=dict.fromkeys(archives,0)
    if not archives or not pieces:raise ValueError('资源分包清单为空。')
    for item in pieces:
        name=item.get('name','');archive=item.get('archive','')
        if not re.fullmatch(r'VideoCopyStudio-Offline-v'+re.escape(VERSION)+r'-data[0-9]+\.zip',name) or name in names or archive not in archives:
            raise ValueError('小分包名称无效或重复。')
        if not re.fullmatch(r'[a-f0-9]{64}',item.get('sha256','')) or not isinstance(item.get('bytes'),int) or not 0<item['bytes']<LIMIT:
            raise ValueError('小分包大小或校验值无效。')
        if not isinstance(item.get('payload_bytes'),int) or not 0<item['payload_bytes']<LIMIT or item.get('offset')!=offsets[archive]:
            raise ValueError('小分包顺序、偏移或长度无效。')
        names.add(name);offsets[archive]+=item['payload_bytes']
    if any(offsets[name]!=item['bytes'] for name,item in archives.items()):raise ValueError('小分包未覆盖完整资源。')
    return value


def install(directory,parent,emit=lambda _:None,manifest_path=None):
    directory=Path(directory).resolve();parent=Path(parent).resolve();description=load_manifest(manifest_path)
    original=description['original'];destination=parent/original['client_dir']
    if destination.exists():raise ValueError('目标客户端目录已存在，请选择另一位置；不会覆盖现有资料。')
    for item in description['pieces']:
        source=directory/item['name'];emit('正在校验 '+item['name'])
        if not source.is_file() or source.stat().st_size!=item['bytes'] or base.digest(source)!=item['sha256']:
            raise ValueError('小分包缺失或校验失败，请重新下载：'+item['name'])
        with zipfile.ZipFile(source) as archive:
            entries=archive.infolist()
            if len(entries)!=2 or {entry.filename for entry in entries}!={'payload.bin','README.txt'} or archive.getinfo('payload.bin').file_size!=item['payload_bytes']:
                raise ValueError('小分包内部结构或长度无效：'+item['name'])
    parent.mkdir(parents=True,exist_ok=True)
    required=sum(item['bytes'] for item in original['parts'])+original.get('unpacked_bytes',0)+100*1024**2
    if shutil.disk_usage(parent).free<required:raise ValueError('安装位置剩余空间不足，请预留约 12 GB 后重试。')
    with tempfile.TemporaryDirectory(prefix='.vcs-lanzou-',dir=parent) as temporary:
        temporary=Path(temporary).resolve()
        if not temporary.is_relative_to(parent):raise ValueError('临时目录必须位于所选安装位置内。')
        for item in original['parts']:
            emit('正在合并 '+item['name']);target=temporary/item['name']
            with target.open('wb') as output:
                for piece in description['pieces']:
                    if piece['archive']!=item['name']:continue
                    with zipfile.ZipFile(directory/piece['name']) as archive,archive.open('payload.bin') as payload:
                        shutil.copyfileobj(payload,output,4*1024*1024)
            if target.stat().st_size!=item['bytes'] or base.digest(target)!=item['sha256']:raise ValueError('合并后的资源校验失败：'+item['name'])
        (temporary/f'offline-downloads-v{VERSION}.json').write_text(json.dumps(original,ensure_ascii=False),encoding='utf-8')
        return base.install(temporary,parent,emit)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package-dir',type=Path);parser.add_argument('--extract-to',type=Path)
    parser.add_argument('--manifest',type=Path);parser.add_argument('--self-test',type=Path);args=parser.parse_args()
    directory=args.package_dir or (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path.cwd())
    description=load_manifest(args.manifest)
    if args.extract_to:
        target=install(directory,args.extract_to,manifest_path=args.manifest)
        if args.self_test:args.self_test.write_text(json.dumps({'ok':True,'client':str(target),'pieces':len(description['pieces'])}),encoding='utf-8')
        return
    root=base.tk.Tk()
    if args.self_test:root.withdraw()
    def assemble(folder,parent,emit):return install(folder,parent,emit,args.manifest)
    base.Setup(root,directory,installer=assemble,resource_note='清单已内置。请将本版全部小 ZIP 分包放在安装器旁边，无需单独解压。')
    root.title('文案工坊 · 蓝奏云完整离线安装器')
    if args.self_test:
        root.update_idletasks();root.destroy();args.self_test.write_text(json.dumps({'ok':True,'version':VERSION,'pieces':len(description['pieces'])}),encoding='utf-8');return
    root.mainloop()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        if sys.stderr:print(str(exc),file=sys.stderr)
        if '--self-test' not in sys.argv:base.messagebox.showerror('蓝奏云离线安装器',str(exc))
        sys.exit(1)
