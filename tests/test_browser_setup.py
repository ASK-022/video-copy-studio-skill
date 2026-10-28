import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from browser_setup import PROBE, browser_status, prepare_browser, repair_browser
from studio_agent import main


class BrowserSetup(unittest.TestCase):
    def result(self, code=0):
        return subprocess.CompletedProcess([], code)

    def test_old_runtime_missing_package_is_repaired_with_its_python(self):
        with tempfile.TemporaryDirectory(prefix='浏览器 空格') as folder:
            with patch('browser_setup.subprocess.run', side_effect=[self.result(1),self.result(),self.result(),self.result()]) as run:
                path = prepare_browser(folder, sys.executable)
            calls = run.call_args_list
            self.assertEqual(calls[1].args[0][1:4], ['-m','pip','install'])
            self.assertEqual(calls[2].args[0][1:], ['-m','playwright','install','chromium'])
            self.assertEqual(calls[3].args[0][2], PROBE)
            for call in calls:
                self.assertEqual(call.args[0][0], str(Path(sys.executable).resolve()))
                self.assertEqual(call.kwargs['env']['PLAYWRIGHT_BROWSERS_PATH'], path)

    def test_existing_package_is_not_upgraded(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('browser_setup.subprocess.run', return_value=self.result()) as run:
                prepare_browser(folder, sys.executable)
            self.assertEqual(run.call_count, 3)

    def test_failure_never_rewrites_registered_runtime(self):
        for results in ([1,1], [0,1], [0,0,1]):
            with self.subTest(results=results), tempfile.TemporaryDirectory() as folder:
                config={'python':sys.executable,'data_dir':'private-data','port':8787}
                target=Path(folder)/'runtime.json'
                original=json.dumps(config).encode();target.write_bytes(original)
                with patch('browser_setup.subprocess.run', side_effect=[self.result(code) for code in results]):
                    with self.assertRaisesRegex(RuntimeError,'安装未完成'):
                        repair_browser(folder, config)
                self.assertEqual(target.read_bytes(),original)

    def test_success_preserves_data_port_and_model_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            config={'python':sys.executable,'data_dir':'private-data','port':8787,'model_cache':'existing-models'}
            with patch('browser_setup.subprocess.run', return_value=self.result()):
                result=repair_browser(folder,config)
            saved=json.loads((Path(folder)/'runtime.json').read_text(encoding='utf-8'))
            self.assertTrue(result['browser_ready'])
            for key,value in config.items():self.assertEqual(saved[key],value)
            self.assertEqual(saved['browser_path'],str(Path(folder).resolve()/'browsers'))

    def test_launch_timeout_does_not_report_ready(self):
        with patch('browser_setup.subprocess.run', side_effect=subprocess.TimeoutExpired('probe',45)):
            self.assertFalse(browser_status(sys.executable,Path('missing-browser')))

    def test_missing_interpreter_is_not_ready(self):
        self.assertFalse(browser_status(None,Path('missing-browser')))

    def test_cli_keeps_actionable_repair_error(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'runtime.json').write_text(json.dumps({'python':sys.executable}))
            with patch.object(sys,'argv',['studio_agent.py','--runtime-home',folder,'repair-browser']):
                with patch('studio_agent.repair_browser',side_effect=RuntimeError('Chromium 下载失败，请查看 bootstrap.log')):
                    with self.assertRaisesRegex(ValueError,'bootstrap.log'):main()

    def test_service_uses_the_registered_browser_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            config={'python':sys.executable,'asr_root':folder,'ffmpeg':str(Path(folder)/'ffmpeg.exe'),
                    'data_dir':str(Path(folder)/'data'),'browser_path':str(Path(folder)/'browsers')}
            (Path(folder)/'runtime.json').write_text(json.dumps(config))
            with patch.object(sys,'argv',['studio_agent.py','--runtime-home',folder,'start']):
                with patch('studio_agent.Studio') as studio, patch('studio_agent.subprocess.Popen') as launch:
                    studio.return_value.request.side_effect=[ConnectionError(),{'ok':True}]
                    launch.return_value.pid=123
                    self.assertTrue(main()['ready'])
            self.assertEqual(launch.call_args.kwargs['env']['PLAYWRIGHT_BROWSERS_PATH'],config['browser_path'])


if __name__ == '__main__':unittest.main()
