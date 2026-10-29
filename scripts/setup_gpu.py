"""Prepare an optional CUDA sidecar without replacing the working CPU environment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from bootstrap import home,patch_runtime

NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
PROBE="""import json,torch
assert torch.cuda.is_available(),'CUDA is unavailable; check the NVIDIA driver.'
x=torch.ones((32,32),device='cuda');y=x@x;torch.cuda.synchronize()
print(json.dumps({'available':True,'name':torch.cuda.get_device_name(0),'torch':torch.__version__,'cuda':torch.version.cuda,'tensor_device':str(y.device)}))
"""

def locations(config):
    config=json.loads(Path(config).read_text(encoding='utf-8-sig'))
    cpu=Path(config['python']).resolve();engine=Path(config['asr_root']).resolve()
    if not cpu.is_file() or not (engine/'webmain.py').is_file():raise ValueError('Registered CPU runtime is incomplete.')
    site=cpu.parents[1]/'Lib/site-packages' if cpu.parent.name.lower()=='scripts' else cpu.parent/'Lib/site-packages'
    if not (site/'funasr').is_dir():raise ValueError('Registered runtime is missing FunASR dependencies.')
    return cpu,engine,site

def probe(python):
    result=subprocess.run([str(python),'-c',PROBE],capture_output=True,text=True,encoding='utf-8',timeout=60,creationflags=NO_WINDOW)
    if result.returncode:raise ValueError('GPU check failed: '+result.stderr[-1200:])
    return json.loads(result.stdout.strip().splitlines()[-1])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-config',type=Path,default=home()/'runtime.json')
    parser.add_argument('--install',action='store_true',help='Explicitly download the optional CUDA PyTorch packages (several GB).')
    args=parser.parse_args();cpu,engine,site=locations(args.runtime_config)
    gpu=engine/'.venv-gpu';python=gpu/'Scripts/python.exe'
    if args.install:
        info=subprocess.check_output([str(cpu),'-c','import json,sys,struct;print(json.dumps([sys.version_info[:2],struct.calcsize("P")*8]))'],text=True)
        version,bits=json.loads(info)
        if os.name!='nt' or version!=[3,12] or bits!=64:raise ValueError('GPU setup supports Windows x64 Python 3.12. The CPU runtime remains available.')
        if not python.is_file():subprocess.run([str(cpu),'-m','venv','--without-pip',str(gpu)],check=True,creationflags=NO_WINDOW)
        # Process the original environment's compatibility hooks as well as its packages.
        (gpu/'Lib/site-packages/studio_cpu_dependencies.pth').write_text('import site; site.addsitedir('+repr(str(site))+')\n',encoding='utf-8')
        try:result=probe(python)
        except (ValueError,OSError):
            subprocess.run([str(python),'-m','pip','--isolated','install','--ignore-installed','--no-deps','--index-url',
                'https://download.pytorch.org/whl/cu128','torch==2.11.0+cu128','torchaudio==2.11.0+cu128'],check=True,creationflags=NO_WINDOW)
            result=probe(python)
        patch_runtime(engine)
    else:
        if not python.is_file():raise ValueError('No GPU sidecar is installed. Add --install to download it; CPU is unchanged.')
        result=probe(python)
    print(json.dumps(dict(result,python=str(python),scope='Local speech recognition, punctuation and timestamp alignment'),ensure_ascii=True))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=True));sys.exit(1)
