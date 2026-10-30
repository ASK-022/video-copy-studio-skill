"""Verify the actual bundled models with outbound sockets denied in this process."""
import argparse
import asyncio
import gc
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

PREFIX='@@CONTENTHUB_PROGRESS '


def event(message):
    print(PREFIX+json.dumps({'kind':'activity','message':message},ensure_ascii=False),flush=True)


def verify(root):
    root=Path(root).resolve();attempts=[]
    original_connect=socket.socket.connect;original_connect_ex=socket.socket.connect_ex;original_create=socket.create_connection
    def local(address):return isinstance(address,tuple) and (str(address[0]) in ('localhost','::1') or str(address[0]).startswith('127.'))
    def guard_connect(sock,address):
        if local(address):return original_connect(sock,address)
        attempts.append('external-connection');raise OSError('Offline verification: outbound network is disabled')
    def guard_connect_ex(sock,address):
        if local(address):return original_connect_ex(sock,address)
        attempts.append('external-connection');raise OSError('Offline verification: outbound network is disabled')
    def guard_create(address,*args,**kwargs):
        if local(address):return original_create(address,*args,**kwargs)
        attempts.append('external-connection');raise OSError('Offline verification: outbound network is disabled')
    socket.socket.connect=guard_connect;socket.socket.connect_ex=guard_connect_ex;socket.create_connection=guard_create
    os.environ.update(VIDEO_COPY_STUDIO_OFFLINE_MODELS=str(root/'Models'),MODEL_CACHE_DIR=str(root/'Models'),
        MODELSCOPE_CACHE=str(root/'Models'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',ENABLE_GPU='false')
    engine=root/'Engine';sys.path.insert(0,str(engine));os.chdir(engine)
    from core.sensevoice_transcriber import SenseVoiceTranscriber
    from utils.forced_aligner import ForcedAligner
    from rapidocr_onnxruntime import RapidOCR
    import numpy as np
    async def load():
        event('离线自检 1/4：加载 SenseVoice 并进行本机推理（不下载）')
        transcriber=SenseVoiceTranscriber(device='cpu',model_cache_dir=str(root/'Models'),timestamp_mode='sentence')
        await transcriber.load_model()
        assert transcriber.model is not None,'SenseVoice 未加载'
        assert isinstance(transcriber.model.generate(input=np.zeros(16000,dtype=np.float32),language='zh',use_itn=True),list)
        event('离线自检 2/4：加载标点模型并进行本机推理')
        await transcriber._load_punctuation_model();assert transcriber.punctuation_model is not None
        transcriber.punctuation_model.generate(input='你好这是离线安装资源检查')
        del transcriber;gc.collect()
    asyncio.run(load())
    event('离线自检 3/4：加载本机时间对齐模型')
    aligner=ForcedAligner(model_cache_dir=str(root/'Models'),device='cpu');assert aligner.load_model() and aligner.model is not None
    del aligner;gc.collect()
    event('离线自检 4/4：加载 OCR 并进行本机推理')
    ocr=RapidOCR();ocr(np.full((80,240,3),255,dtype=np.uint8))
    assert not attempts,'离线加载尝试了外部连接'
    for name in ('ffmpeg.exe','ffprobe.exe'):
        result=subprocess.run([str(root/'FFmpeg/bin'/name),'-version'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert result.returncode==0,name+' 无法启动'
    from playwright.sync_api import sync_playwright
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(root/'Browsers')
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch(headless=True);browser.close()
    assert not attempts,'离线自检尝试了外部连接'
    return {'ok':True,'root':str(root),'external_attempts':0,'loaded':dict.fromkeys(('sensevoice','punctuation','alignment','ocr'),True),'browser_ready':True,'ffmpeg_ready':True}


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--result',type=Path,required=True);args=parser.parse_args()
    args.result=args.result.resolve()
    try:result=verify(args.root)
    except Exception as error:
        import traceback
        traceback.print_exc();result={'ok':False,'error':type(error).__name__+': '+str(error)}
    args.result.parent.mkdir(parents=True,exist_ok=True);args.result.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    sys.exit(0 if result['ok'] else 1)
