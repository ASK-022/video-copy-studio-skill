import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from build_lanzou_package import wrap_archive
from offline_setup import VERSION,digest
from lanzou_setup import install,load_manifest


class LanzouSetup(unittest.TestCase):
    def prepare(self,root,unsafe=False):
        source=root/f'VideoCopyStudio-Offline-v{VERSION}-part01.zip';directory='VideoCopyStudio-Offline-v'+VERSION
        with zipfile.ZipFile(source,'w') as archive:
            archive.writestr(directory+'/VideoCopyStudio.exe',b'client')
            archive.writestr('../escape.txt' if unsafe else directory+'/Runtime/data.bin',b'unchanged-data'*30)
        pieces=wrap_archive(source,root,1,chunk_size=73)
        description={'format':'video-copy-studio-lanzou/v1','version':VERSION,'original':{
            'format':'video-copy-studio-offline-downloads/v1','version':VERSION,'client_dir':directory,'unpacked_bytes':500,
            'parts':[{'name':source.name,'bytes':source.stat().st_size,'sha256':digest(source)}]},'pieces':pieces}
        metadata=root/'manifest.json';metadata.write_text(json.dumps(description),encoding='utf-8')
        return description,metadata

    def test_real_reassembly_extracts_unchanged_bytes_and_cleans_scratch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);description,metadata=self.prepare(root)
            target=install(root,root/'output',manifest_path=metadata)
            self.assertEqual((target/'Runtime/data.bin').read_bytes(),b'unchanged-data'*30)
            self.assertFalse(list((root/'output').glob('.vcs-lanzou-*')))

    def test_missing_corrupt_and_misordered_pieces_fail_before_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);description,metadata=self.prepare(root)
            first=root/description['pieces'][0]['name'];original=first.read_bytes();first.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'校验失败'):install(root,root/'output',manifest_path=metadata)
            self.assertFalse((root/'output').exists());first.write_bytes(original)
            description['pieces'][0]['offset']=1;metadata.write_text(json.dumps(description),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'偏移'):load_manifest(metadata)

    def test_original_zip_path_checks_still_apply_after_reassembly(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);description,metadata=self.prepare(root,unsafe=True)
            with self.assertRaises(ValueError):install(root,root/'output',manifest_path=metadata)
            self.assertFalse((root/'escape.txt').exists());self.assertFalse(list((root/'output').glob('.vcs-lanzou-*')))


if __name__=='__main__':unittest.main()
