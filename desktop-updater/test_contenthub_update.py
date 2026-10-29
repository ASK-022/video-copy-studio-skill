import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('desktop_update',Path(__file__).with_name('contenthub_update.py'));update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)
class UpdateTests(unittest.TestCase):
 def test_interrupted_boot_restores_pointer_and_metadata(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)/'app';data=Path(folder)/'profile';root.mkdir();data.mkdir();token='a'*48
   update.write(data/'director-data/providers.json',{'encrypted_key':'fixture-encrypted'})
   update.backup_metadata(data,token)
   update.write(data/'director-data/providers.json',{'encrypted_key':'broken-migration'})
   update.write(root/'current.json',{'version':'1.1.0','previous':'1.0.1'})
   update.write(root/'update-transaction.json',{'state':'launching','previous':'1.0.1','target':'1.1.0','worker_pid':123,'nonce':token,'ack':'boot-'+token+'.json','backup':token})
   with patch.object(update,'is_alive',return_value=False):update.recover(root,data)
   self.assertEqual(update.read(root/'current.json')['version'],'1.0.1')
   self.assertEqual(update.read(data/'director-data/providers.json')['encrypted_key'],'fixture-encrypted')
   self.assertEqual(update.read(data/'desktop-update-result.json')['status'],'rolled-back')
 def test_confirmed_boot_recovers_commit_after_worker_exit(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)/'app';data=Path(folder)/'profile';root.mkdir();data.mkdir();nonce='b'*48
   update.write(root/'update-transaction.json',{'state':'launching','previous':'1.0.1','target':'1.1.0','worker_pid':123,'nonce':nonce,'ack':'boot-'+nonce+'.json'})
   update.write(data/'updates'/('boot-'+nonce+'.json'),{'version':'1.1.0','nonce':nonce,'pid':456})
   with patch.object(update,'is_alive',side_effect=lambda pid,*_:pid==456):update.recover(root,data)
   self.assertEqual(update.read(root/'current.json'),{'version':'1.1.0','previous':'1.0.1'})
 def test_paths_cannot_escape_version_or_backup_directory(self):
  with tempfile.TemporaryDirectory() as folder:
   for path in ('../secret','/outside','x/../../key','x\\file','x:file','./key'):
    with self.subTest(path=path):
     with self.assertRaises(ValueError):update.safe(Path(folder),path)
 def test_uninstaller_removes_only_owned_versions_and_keeps_data_and_models(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)/'app';data=Path(folder)/'profile';models=root/'Models';software=root/'versions/1.1.0'
   software.mkdir(parents=True);data.mkdir();models.mkdir()
   update.write(root/'contenthub-install.json',{'format':'contenthub/install/v1','product':'contenthub-desktop'})
   update.write(software/'contenthub-version.json',{'format':'contenthub/version/v1'})
   (software/'ContentHub.exe').write_bytes(b'program fixture');(models/'model.bin').write_bytes(b'keep model');(data/'byok.key').write_bytes(b'keep key')
   with patch.object(update,'profile',return_value=data.resolve()):update.remove_program(root)
   self.assertFalse(software.exists());self.assertEqual((models/'model.bin').read_bytes(),b'keep model');self.assertEqual((data/'byok.key').read_bytes(),b'keep key')
 def test_uninstaller_refuses_a_profile_inside_a_version(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)/'app';software=root/'versions/1.1.0';data=software/'profile';data.mkdir(parents=True)
   update.write(root/'contenthub-install.json',{'format':'contenthub/install/v1','product':'contenthub-desktop'});update.write(software/'contenthub-version.json',{'format':'contenthub/version/v1'})
   (data/'key').write_bytes(b'preserve')
   with patch.object(update,'profile',return_value=data.resolve()):
    with self.assertRaises(ValueError):update.remove_program(root)
   self.assertEqual((data/'key').read_bytes(),b'preserve')
if __name__=='__main__':unittest.main()
