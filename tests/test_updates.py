import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/studio'));sys.path.insert(0,str(ROOT/'scripts'))
from client.updates import REPOSITORY,describe_release,local_version,check_update


def release(version='1.1.1'):
    tag='v'+version;prefix=f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
    names=[f'video-copy-studio-{tag}.zip',f'video-copy-studio-{tag}.zip.sha256']
    return {'tag_name':tag,'body':'版本说明','draft':False,'prerelease':False,
            'assets':[{'name':name,'browser_download_url':prefix+name} for name in names]}


class Updates(unittest.TestCase):
    def test_numeric_comparison_and_no_downgrade(self):
        self.assertTrue(describe_release(release('1.10.0'),'1.9.9')['update_available'])
        self.assertFalse(describe_release(release(),'1.1.1')['update_available'])
        self.assertFalse(describe_release(release(),'2.0.0')['update_available'])

    def test_untrusted_release_links_are_not_reflected(self):
        item=release();item['html_url']='https://evil.example/'
        self.assertEqual(describe_release(item,'1.0.0')['release_url'],f'https://github.com/{REPOSITORY}/releases/tag/v1.1.1')
        item['assets'][0]['browser_download_url']='https://evil.example/payload.zip'
        with self.assertRaises(ValueError):describe_release(item,'1.0.0')

    def test_prereleases_and_missing_checksums_are_rejected(self):
        for change in ({'draft':True},{'prerelease':True},{'tag_name':'v1.1.1-beta'},{'assets':[]}):
            item=release();item.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):describe_release(item,'1.0.0')

    def test_check_is_read_only_and_uses_fixed_public_endpoint(self):
        from io import BytesIO
        with patch('client.updates.urllib.request.urlopen',return_value=BytesIO(json.dumps(release()).encode())) as fetch:
            result=check_update('1.0.0')
        request=fetch.call_args.args[0]
        self.assertEqual(request.full_url,f'https://api.github.com/repos/{REPOSITORY}/releases/latest')
        self.assertIsNone(request.data)
        self.assertNotIn('Authorization',request.headers)
        self.assertTrue(result['update_available'])

    @unittest.skipUnless(sys.platform=='win32','Windows manager')
    def test_receipt_with_windows_bom_is_recognized(self):
        from windows_manager import installed_version
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'installation.json').write_text(json.dumps({'version':'1.1.1'}),encoding='utf-8-sig')
            self.assertEqual(installed_version(folder),'1.1.1')

    def test_local_version_is_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'VERSION').write_text('1.1.1')
            self.assertEqual(local_version(folder),'1.1.1')
            (Path(folder)/'VERSION').write_text('../evil')
            with self.assertRaises(ValueError):local_version(folder)

    @unittest.skipUnless(sys.platform=='win32','Windows installer')
    def test_gui_installer_uses_bom_hidden_process_and_checks_exit_code(self):
        import windows_manager as manager
        from io import StringIO
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);resources=root/'resources';resources.mkdir()
            (resources/'install.ps1').write_text('# 中文安装脚本',encoding='utf-8')
            config=root/'runtime';config.mkdir()
            (config/'installation.json').write_text(json.dumps({'version':manager.VERSION}))
            def launch(command,**kwargs):
                script=Path(command[command.index('-File')+1])
                self.assertTrue(script.read_bytes().startswith(b'\xef\xbb\xbf'))
                self.assertEqual(command[command.index('-RuntimeHome')+1],str(config.resolve()))
                self.assertIn('-PackagePath',command)
                process=Mock();process.stdout=StringIO('安装输出\n');process.wait.return_value=0
                return process
            with patch.object(manager,'RESOURCES',resources),patch.object(manager,'verify_payload',return_value=resources/'payload.zip'):
                with patch.object(manager.subprocess,'Popen',side_effect=launch):manager.run_installer(config,'v'+manager.VERSION,lambda _:None)
                process=Mock();process.stdout=StringIO('下载失败\n');process.wait.return_value=1
                with patch.object(manager.subprocess,'Popen',return_value=process):
                    with self.assertRaisesRegex(ValueError,'安装未完成'):manager.run_installer(config,'v'+manager.VERSION,lambda _:None)


if __name__=='__main__':unittest.main()
