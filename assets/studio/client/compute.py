"""Optional isolated CUDA ASR runtime; preferences apply to the next transcription."""
import copy
import json
import os
from pathlib import Path
import subprocess
import threading
import time

PROBE="import json,torch; ok=torch.cuda.is_available(); print(json.dumps({'available':ok,'torch':torch.__version__,'cuda':torch.version.cuda,'name':torch.cuda.get_device_name(0) if ok else ''}))"


class ComputeStore:
    def __init__(self,state,cpu_python,gpu_python=None,probe=None,asr_root=None):
        self.path=Path(state)/'compute.json';self.cpu=Path(cpu_python)
        engine=Path(asr_root) if asr_root else self.cpu.parents[2]
        self.gpu=Path(gpu_python or os.environ.get('COPY_STUDIO_GPU_PYTHON') or engine/'.venv-gpu/Scripts/python.exe')
        self._probe=probe or self._run_probe;self._lock=threading.RLock();self._cached=None;self._checked=0;self.last=None

    def _run_probe(self):
        if not self.gpu.is_file():return {'available':False,'reason':'尚未安装可用的 GPU 转写环境。'}
        try:
            run=subprocess.run([str(self.gpu),'-c',PROBE],capture_output=True,text=True,encoding='utf-8',timeout=30,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if run.returncode:raise ValueError('GPU 运行环境加载失败。')
            result=json.loads(run.stdout.strip().splitlines()[-1])
            if not result.get('available'):result['reason']='CUDA 当前不可用，请检查显卡驱动和 GPU 运行环境。'
            return result
        except Exception as exc:return {'available':False,'reason':str(exc)[:200]}

    def mode(self):
        try:
            value=json.loads(self.path.read_text(encoding='utf-8')).get('mode','auto')
            return value if value in ('auto','gpu','cpu') else 'auto'
        except (OSError,ValueError):return 'auto'

    def status(self,refresh=False):
        with self._lock:
            if refresh or self._cached is None or time.time()-self._checked>300:
                self._cached=self._probe();self._checked=time.time()
            return self.peek()

    def peek(self):
        with self._lock:
            gpu=copy.deepcopy(self._cached or {'available':False,'reason':'尚未检测 GPU。'})
            mode=self.mode();actual='gpu' if mode!='cpu' and gpu.get('available') else 'unavailable' if mode=='gpu' else 'cpu'
            return {'mode':mode,'selected_device':actual,'gpu':gpu,'cpu_available':self.cpu.is_file(),
                'last_run':copy.deepcopy(self.last),'scope':'本机语音转写；截图、OCR 与场景检测仍由各自工具处理。'}

    def save(self,mode):
        if mode not in ('auto','gpu','cpu'):raise ValueError('请选择自动、GPU 或 CPU。')
        with self._lock:
            if mode=='gpu' and not self.status(True)['gpu'].get('available'):raise ValueError(self.peek()['gpu']['reason'])
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps({'mode':mode}),encoding='utf-8');temp.replace(self.path)
            return self.status()

    def plan(self):
        state=self.status();mode=state['mode'];gpu=state['gpu']
        if mode=='gpu' and not gpu.get('available'):raise ValueError(gpu.get('reason','GPU 不可用，请选择 CPU 或自动。'))
        device='gpu' if mode!='cpu' and gpu.get('available') else 'cpu'
        return {'mode':mode,'device':device,'python':str(self.gpu if device=='gpu' else self.cpu),
            'name':gpu.get('name','') if device=='gpu' else 'CPU',
            'fallback_reason':gpu.get('reason','') if mode=='auto' and device=='cpu' else ''}

    def started(self,job_id,plan):
        with self._lock:self.last={k:v for k,v in dict(plan,job_id=job_id,started=time.time()).items() if k!='python'}


def process_environment(device):
    return {'ENABLE_GPU':'true' if device=='gpu' else 'false',
        'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES','0') if device=='gpu' else '-1',
        'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2'}


def cuda_failure(log):
    text=log.lower()
    return any(value in text for value in ('out of memory','cuda error','cublas','cudnn','not compiled with cuda','no kernel image'))
