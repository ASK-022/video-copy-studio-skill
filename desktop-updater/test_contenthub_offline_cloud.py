import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
from contenthub_offline_cloud_setup import assemble,validate


class OfflineCloudTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
        self.data=b'complete-offline-resource'*200;self.item={'name':'resources-r1.zip','bytes':len(self.data),'sha256':hashlib.sha256(self.data).hexdigest(),'parts':[]}
        for index,start in enumerate(range(0,len(self.data),2000),1):
            data=self.data[start:start+2000];name=f'resources-r1-{index:02}.zip';entry=f'resource.part{index:03}'
            with zipfile.ZipFile(self.root/name,'w') as zipped:zipped.writestr(entry,data)
            self.item['parts'].append({'name':name,'entry':entry,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    def test_assemble_and_reuse_without_parts(self):
        target=assemble(self.root,self.item,lambda *a,**k:None);stamp=target.stat().st_mtime_ns
        self.assertEqual(target.read_bytes(),self.data)
        for part in self.item['parts']:(self.root/part['name']).unlink()
        events=[];self.assertEqual(assemble(self.root,self.item,lambda kind,**fields:events.append(kind)),target)
        self.assertEqual(stamp,target.stat().st_mtime_ns);self.assertEqual(events,['cached'])
    def test_missing_piece_is_named_and_partial_removed(self):
        part=self.item['parts'][-1];(self.root/part['name']).unlink()
        with self.assertRaisesRegex(ValueError,part['name']):assemble(self.root,self.item,lambda *a,**k:None)
        self.assertFalse(list(self.root.glob('*.partial')))
    def test_corrupt_piece_preserves_existing_file(self):
        target=self.root/self.item['name'];target.write_bytes(b'user-existing-file')
        part=self.item['parts'][0]
        with zipfile.ZipFile(self.root/part['name'],'w') as zipped:zipped.writestr(part['entry'],b'x'*part['bytes'])
        with self.assertRaisesRegex(ValueError,'校验失败'):assemble(self.root,self.item,lambda *a,**k:None)
        self.assertEqual(target.read_bytes(),b'user-existing-file');self.assertFalse(list(self.root.glob('*.partial')))
    def test_unsafe_and_duplicate_piece_names_rejected(self):
        item={**self.item,'name':'../outside.exe'}
        with self.assertRaises(ValueError):validate(item)
        self.item['parts'][-1]['name']=self.item['parts'][0]['name']
        with self.assertRaises(ValueError):validate(self.item)


if __name__=='__main__':unittest.main()
