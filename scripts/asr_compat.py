"""Process-local SentencePiece path compatibility for Windows Chinese directories."""
import os
from pathlib import Path


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
