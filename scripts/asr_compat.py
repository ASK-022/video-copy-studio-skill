"""Process-local SentencePiece path compatibility for Windows Chinese directories."""
import os
from pathlib import Path


def offline_model_path(value):
    """Resolve only packaged local models when the offline launcher enables this mode."""
    root=os.environ.get('VIDEO_COPY_STUDIO_OFFLINE_MODELS')
    if not root:return value
    models={
        'iic/SenseVoiceSmall':'sensevoice',
        'damo/punc_ct-transformer_zh-cn-common-vocab272727-pytorch':'punctuation',
        'iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch':'punctuation',
        'fa-zh':'alignment',
        'iic/speech_timestamp_prediction-v1-16k-offline':'alignment',
    }
    if value not in models:raise ValueError('离线客户端未包含所需模型：'+str(value))
    path=Path(root)/models[value]
    if not (path/'model.pt').is_file() or not (path/'config.yaml').is_file():raise FileNotFoundError('离线模型文件缺失：'+str(path))
    return str(path.resolve())


def fix_sentencepiece_paths():
    if os.name != 'nt':
        return
    import sentencepiece as spm
    cls = spm.SentencePieceProcessor
    original = cls.LoadFromFile
    if getattr(original, '_studio_unicode_paths', False):
        return

    def load(self, filename):
        # Python opens Unicode paths correctly; some SentencePiece Windows wheels
        # use a narrow C++ file API. Loading serialized bytes avoids that API.
        if isinstance(filename, (str, os.PathLike)) and not str(filename).isascii():
            return self.LoadFromSerializedProto(Path(filename).read_bytes())
        return original(self, filename)

    load._studio_unicode_paths = True
    cls.LoadFromFile = load
