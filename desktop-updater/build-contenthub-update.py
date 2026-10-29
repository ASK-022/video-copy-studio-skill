"""Build a signed-manifest payload and small CDN-sized desktop delta parts."""
from pathlib import Path
import argparse,hashlib,json,zipfile
REPOSITORY='ASK-022/video-copy-studio-skill';CDNS=('https://fastly.jsdelivr.net','https://gcore.jsdelivr.net')
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def sha(path):
 value=hashlib.sha256()
 with Path(path).open('rb') as source:
  for block in iter(lambda:source.read(1024*1024),b''):value.update(block)
 return value.hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--app',type=Path,required=True);parser.add_argument('--base',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 meta=json.loads((args.app/'contenthub-version.json').read_text(encoding='utf-8'))
 before=json.loads((args.base/'contenthub-version.json').read_text(encoding='utf-8')) if args.base else None
 version=meta['version'];base=before['version'] if before else '*';out=args.output;out.mkdir(parents=True,exist_ok=True)
 name=f'ContentHub-delta-{base}-to-{version}-x64.zip' if before else f'ContentHub-App-v{version}-x64.zip'
 target=out/name;changed=[]
 with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
  archive.write(args.app/'contenthub-version.json','contenthub-version.json')
  for path,entry in meta['files'].items():
   if before and before['files'].get(path)==entry:continue
   source=args.app/path
   if source.is_symlink() or source.stat().st_size!=entry['bytes'] or sha(source)!=entry['sha256']:raise ValueError('Application files changed after packaging: '+path)
   archive.write(source,path);changed.append(path)
 parts=[]
 with target.open('rb') as source:
  index=1
  while block:=source.read(16*1024**2):
   part=name+f'.part{index:03d}';(out/part).write_bytes(block)
   urls=[f'{host}/gh/{REPOSITORY}@contenthub-v{version}/releases/contenthub/files/{part}' for host in CDNS]+[f'https://github.com/{REPOSITORY}/releases/download/contenthub-v{version}/{part}']
   parts.append({'name':part,'bytes':len(block),'sha256':hashlib.sha256(block).hexdigest(),'urls':urls});index+=1
 payload={'format':'contenthub-desktop-update/v1','repository':REPOSITORY,'version':version,'min_version':'1.0.1','resource_contract':1,
  'notes':'完整桌面版一键更新、启动失败回滚和中断恢复。保留资料与 Key，继续复用已有模型。',
  'packages':[{'base_version':base,'name':name,'bytes':target.stat().st_size,'sha256':sha(target),'parts':parts}]}
 (out/'payload.json').write_bytes(canonical(payload))
 (out/'delta-report.json').write_text(json.dumps({'version':version,'base':base,'changed_files':changed,'bytes':target.stat().st_size,'parts':len(parts)},ensure_ascii=False,indent=2),encoding='utf-8')
 print('DESKTOP_DELTA_READY '+str(target.stat().st_size)+' bytes, '+str(len(changed))+' changed files, '+str(len(parts))+' parts')
if __name__=='__main__':main()
