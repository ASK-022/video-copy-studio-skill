"""Download and actually load the models used by the bundled local pipeline."""
import argparse
import asyncio
import gc
import json
import os
from pathlib import Path
import sys
import time

MODEL_CONTRACT = 1
REQUIRED = ('sensevoice', 'punctuation', 'alignment', 'ocr')


def model_status(manifest, cache=None):
    """A successful load receipt is valid only while its model files still exist."""
    try:
        data = json.loads(Path(manifest).read_text(encoding='utf-8'))
        if data.get('contract') != MODEL_CONTRACT or not all(data.get('loaded', {}).get(k) is True for k in REQUIRED):
            return False
        if cache is not None and Path(data['cache']).resolve() != Path(cache).resolve():
            return False
        files = data.get('files', [])
        return bool(files) and all(Path(f['path']).is_file() and Path(f['path']).stat().st_size == f['bytes'] for f in files)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def prepare(asr, cache, manifest):
    # ModelScope reads this variable during import; set it before importing FunASR.
    os.environ.update(MODELSCOPE_CACHE=str(cache), MODEL_CACHE_DIR=str(cache), ENABLE_GPU='false')
    cache.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(asr))
    os.chdir(asr)
    from core.sensevoice_transcriber import SenseVoiceTranscriber
    from utils.forced_aligner import ForcedAligner
    from rapidocr_onnxruntime import RapidOCR

    async def load():
        transcriber = SenseVoiceTranscriber(device='cpu', model_cache_dir=str(cache), timestamp_mode='sentence')
        print('[models 1/4] SenseVoice Small: download and CPU load', flush=True)
        await transcriber.load_model()
        if transcriber.model is None:
            raise RuntimeError('SenseVoice 模型未能加载。')
        # Run inference, rather than accepting a downloaded but unusable checkpoint.
        import numpy as np
        result = transcriber.model.generate(input=np.zeros(16000, dtype=np.float32), language='zh', use_itn=True)
        if not isinstance(result, list):
            raise RuntimeError('SenseVoice 本地推理自检失败。')
        print('[models 2/4] Chinese punctuation: download and CPU load', flush=True)
        await transcriber._load_punctuation_model()
        if transcriber.punctuation_model is None:
            raise RuntimeError('标点模型未能加载，安装未完成。')
        transcriber.punctuation_model.generate(input='你好这是本地模型安装测试')
        del transcriber
        gc.collect()

    asyncio.run(load())
    print('[models 3/4] Forced alignment: download and CPU load', flush=True)
    aligner = ForcedAligner(model_cache_dir=str(cache), device='cpu')
    if not aligner.load_model() or aligner.model is None:
        raise RuntimeError('时间对齐模型未能加载，安装未完成。')
    del aligner
    gc.collect()
    print('[models 4/4] OCR ONNX models: load and inference', flush=True)
    ocr = RapidOCR()
    import numpy as np
    ocr(np.full((80, 240, 3), 255, dtype=np.uint8))
    import rapidocr_onnxruntime
    ocr_root = Path(rapidocr_onnxruntime.__file__).parent
    files = [p for p in cache.rglob('*') if p.is_file() and p.suffix.lower() in ('.pt', '.pth', '.bin', '.onnx', '.yaml', '.json', '.mvn', '.model', '.txt')]
    files.extend(ocr_root.rglob('*.onnx'))
    if not any(p.suffix == '.pt' for p in files) or not any(p.suffix == '.onnx' for p in files):
        raise RuntimeError('模型文件清单不完整。')
    data = {'contract': MODEL_CONTRACT, 'cache': str(cache), 'verified_at': time.time(),
            'loaded': dict.fromkeys(REQUIRED, True),
            'files': [{'path': str(p.resolve()), 'bytes': p.stat().st_size} for p in sorted(set(files))]}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    pending = manifest.with_suffix('.tmp')
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    pending.replace(manifest)
    print(json.dumps({'ok': True, 'models_ready': True, 'manifest': str(manifest)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asr-root', required=True, type=Path)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.asr_root.resolve(), args.cache.resolve(), args.manifest.resolve())
    except Exception:
        # Never leave an old success receipt after a failed repair.
        args.manifest.unlink(missing_ok=True)
        raise
